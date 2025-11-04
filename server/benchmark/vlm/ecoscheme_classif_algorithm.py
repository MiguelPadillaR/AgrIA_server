import re
import json
from decimal import Decimal, ROUND_HALF_UP

# Fixed constant for the pluriannuality bonus (€25.00/ha) as per instructions
PLURIANNUALITY_BONUS_PER_HA = Decimal('25.00')

# Define rounding constants
ROUNDING_RATE = Decimal('0.000001') # 6 decimals for applied rate
ROUNDING_AREA = Decimal('0.0001')   # 4 decimals for total area
ROUNDING_PAYMENT = Decimal('0.01')  # 2 decimals for total payments

# --- Main Calculation Function (Modified) ---

def calculate_ecoscheme_payment_exclusive(input_data_str: str, rules_json_str: str) -> dict:
    """
    Processes land use input data and calculates estimated Eco-scheme payments
    by applying the Critical Exclusivity Rule (choosing the highest payment/ha
    across all rate types) and including both Peninsular and Insular calculations.
    """

    # --- 1. PREPARE RULES AND CONSTANTS ---
    
    try:
        rules_data_list = json.loads(rules_json_str.strip())
    except json.JSONDecodeError:
        # Fallback for non-list JSON string (often means str(dict) was passed)
        rules_data_list = json.loads(f'[{rules_json_str.strip()}]')
    
    eligible_schemes_by_land_use, non_eligible_uses = get_ecoscheme_rules_data(rules_data_list)

    # --- 2. PARSE INPUT DATA AND CALCULATE TOTAL AREA ---
    
    land_use_regex = r'- Land Use: ([A-Z]{2})\s*- Eligible surface \(ha\): ([\d\.]+)\s*- Irrigation Coeficient: ([\d\.]+%)\s*(?:- Slope Coeficient: ([\d\.]+%))?'
    land_use_blocks = re.findall(land_use_regex, input_data_str, re.DOTALL)

    parsed_data = {}
    total_parcel_area = Decimal('0.0')

    for match in land_use_blocks:
        land_use_code, area_str, _, _ = match
        area = Decimal(area_str)
        total_parcel_area += area
        parsed_data[land_use_code] = {"area": area}
    
    # --- 3. APPLY EXCLUSIVITY RULE (Determine best ES/ha for each LU) ---
    
    land_use_assignments = get_exclusivity_land_uses(eligible_schemes_by_land_use, non_eligible_uses, parsed_data)
            
    # --- 4. GROUP RESULTS AND CALCULATE TOTAL PAYMENTS ---
    
    final_scheme_results = get_ecoschemes_rates_and_totals(parsed_data, land_use_assignments)
    
    estimated_payments = []
    total_aid_no_pluriannuality = Decimal('0.0')
    total_aid_with_pluriannuality = Decimal('0.0')
    pluri_area = Decimal('0.0')
    applicable_ecoschemes = []

    sorted_keys = sorted([k for k in final_scheme_results.keys() if k != 'Non-Eligible'])
    if 'Non-Eligible' in final_scheme_results: sorted_keys.append('Non-Eligible')
        
# Process final payments for each group
    for key in sorted_keys:
        res = final_scheme_results[key]
        area = res["Total_Area_ha"]
        
        if key == 'Non-Eligible':
            land_use_list = sorted(res["Land_Uses"])
            non_eligible_input_land_uses = [land_use for land_use in land_use_list if land_use in parsed_data]

            estimated_payments.append({
                "Ecoscheme_ID": res["Ecoscheme_ID"], "Ecoscheme_Name": res["Ecoscheme_Name"], "Ecoscheme_Subtype": res["Ecoscheme_Subtype"],
                "Land_Use_Class_Eligible": ", ".join(non_eligible_input_land_uses),
                "Total_Area_ha": float(area.quantize(ROUNDING_AREA, rounding=ROUND_HALF_UP)),
                # Peninsular and Insular data kept for completeness, but set to N/A for Non-Eligible
                "Peninsular": {"Applied_Base_Payment_EUR": "N/A", "Total_Base_Payment_EUR": "N/A", "Total_with_Pluriannuality_EUR": "N/A", "Applicable": "N/A"},
                "Insular": {"Applied_Base_Payment_EUR": "N/A", "Total_Base_Payment_EUR": "N/A", "Total_with_Pluriannuality_EUR": "N/A", "Applicable": "N/A"},
            })
        else:
            # Calculate BOTH Peninsular and Insular payments
            # Note: The chosen scheme was already determined using Peninsular rates in Section 3.
            peninsular_results = calculate_payments_for_rate_type(area, res['rates']['Peninsular'], res['pluriannuality_applicable'])
            insular_results = calculate_payments_for_rate_type(area, res['rates']['Insular'], res['pluriannuality_applicable'])
            
            # --- SUMMING FOR FINAL REPORT: USE PENINSULAR RATES ONLY ---
            applied_base_payment_for_summary = Decimal(peninsular_results['Total_Base_Payment_EUR'])
            applied_total_payment_for_summary = Decimal(peninsular_results['Total_with_Pluriannuality_EUR'])
            
            total_aid_no_pluriannuality += applied_base_payment_for_summary
            total_aid_with_pluriannuality += applied_total_payment_for_summary
            
            if res['pluriannuality_applicable']:
                 pluri_area += area
                 
            applicable_ecoschemes.append(res["Ecoscheme_ID"])

            # Format the eligible Land Use string
            land_use_list_only = ", ".join(sorted(res['Land_Uses']))
            land_use_area_total = area.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)
            land_use_eligible_str = f"{land_use_list_only} ({land_use_area_total} ha)"


            # Append to payments list with nested results
            estimated_payments.append({
                "Ecoscheme_ID": res["Ecoscheme_ID"], 
                "Ecoscheme_Name": res["Ecoscheme_Name"], 
                "Ecoscheme_Subtype": res["Ecoscheme_Subtype"],
                "Land_Use_Class_Eligible": land_use_eligible_str,
                "Total_Area_ha": float(area.quantize(ROUNDING_AREA, rounding=ROUND_HALF_UP)),
                "Peninsular": peninsular_results,
                "Insular": insular_results,
            })

    # -------------------------------------------------------------
    # --- 5. FINAL RESULTS SUMMARY (Reporting Peninsular Only) ---
    # -------------------------------------------------------------
    
    pluriannuality_bonus_total = total_aid_with_pluriannuality - total_aid_no_pluriannuality
    
    # Simple clarifications based on the new explicit requirement
    clarifications = [
         f"The Exclusive Eco-scheme choice for each Land Use (LU) was determined ONLY by the highest possible payment/ha using the **Peninsular** rates.",
         f"The final summary totals (Total_Aid) reflect the calculation using **Peninsular** rates, as this is the predominant national territory type.",
         f"The total pluriannuality bonus of {pluriannuality_bonus_total.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)} EUR is applied to the {pluri_area.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)} ha of eligible land (calculated using Peninsular rates).",
    ]

    final_results = {
        "Applicable_Ecoschemes": sorted(list(set(applicable_ecoschemes))),
        "Total_Aid_without_Pluriannuality_EUR": float(total_aid_no_pluriannuality.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Total_Aid_with_Pluriannuality_EUR": float(total_aid_with_pluriannuality.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Clarifications": clarifications
    }

    # Final Output Structure - Update Context
    output_dict = {
        "Report_Type": "EcoScheme_Payment_Estimate",
        "Total_Parcel_Area_ha": float(total_parcel_area.quantize(ROUNDING_AREA, rounding=ROUND_HALF_UP)),
        "Calculation_Context": {
            "Rate_Applied": "Peninsular_Rates_Used_For_Final_Summary_Total", # Updated context
            "Source": "Provisional base rates for Eco-schemes, 2025 CAP Campaign"
        },
        "Estimated_Total_Payment": estimated_payments,
        "Final_Results": final_results
    }
    
    return output_dict


# --- Helper Functions ---

def get_ecoscheme_rules_data(rules_data_list) -> dict:
    eligible_schemes_by_land_use = {}
    non_eligible_uses = set()
    
    for rule in rules_data_list:
        scheme_full_name = rule['Ecoscheme']
        
        if scheme_full_name == 'Non-Eligible':
            non_eligible_uses.update(rule['Land_Uses'].split(', '))
            continue

        scheme_parts = scheme_full_name.split(' - ')
        scheme_id = scheme_parts[0] 
        scheme_name = scheme_parts[1].split('(')[0].strip()
        scheme_subtype = scheme_full_name.split('(')[-1].strip(')')
        
        land_use_list = rule['Land_Uses'].split(', ')
        
        rates = rule['Rates']
        threshold_ha = str(rates['Threshold_ha'])
        threshold = Decimal(threshold_ha) if threshold_ha.replace('.', '', 1).isdigit() else None
        pluri_applicable = rates['Pluriannuality'] == 'Applicable'
        
        base_rate_details = get_base_rate_details(rates, threshold)

        for land_use in land_use_list:
            if land_use not in eligible_schemes_by_land_use:
                eligible_schemes_by_land_use[land_use] = []
            
            eligible_schemes_by_land_use[land_use].append({
                'id': scheme_id,
                'name': scheme_name,
                'subtype': scheme_subtype,
                'rates': base_rate_details, # Contains {'Peninsular': {...}, 'Insular': {...}}
                'pluriannuality_applicable': pluri_applicable,
            })
            
    return eligible_schemes_by_land_use, non_eligible_uses


def get_base_rate_details(rates: dict, threshold: Decimal, keys: list = ["Peninsular", "Insular"]) -> dict:
    """Extracts and formats Tier/Flat rate details for both Peninsular and Insular areas."""
    base_rate_details = {}
    for key in keys:
        key_rates = rates.get(key)
        if key_rates is None: continue # Skip if rate type is missing
        
        if isinstance(key_rates, dict):
            # Tiered rates (Tier_1, Tier_2, Threshold_ha)
            tier1 = Decimal(str(key_rates['Tier_1']))
            tier2 = Decimal(str(key_rates['Tier_2']))
            base_rate_details[key] = {'Tier_1': tier1, 'Tier_2': tier2, 'Threshold_ha': threshold}
        else:
            # Flat rate
            # Handle potential string/Decimal conversion
            flat_rate_value = key_rates if isinstance(key_rates, str) else Decimal(str(key_rates))
            base_rate_details[key] = {'Flat': flat_rate_value}
            
    return base_rate_details


def get_exclusivity_land_uses(eligible_schemes_by_land_use, non_eligible_uses, parsed_data) -> dict:
    land_use_assignments = {} 
    
    for land_use_code, data in parsed_data.items():
        area = data['area']
        
        if land_use_code in non_eligible_uses or land_use_code not in eligible_schemes_by_land_use:
            land_use_assignments[land_use_code] = {'id': 'N/A', 'name': 'Non-Eligible', 'subtype': None, 'payment_per_ha': Decimal('0')}
            continue
            
        best_payment_per_ha = Decimal('-1')
        best_scheme_assignment = None

        # Iterate over ALL rate types (Peninsular, Insular) and all schemes to find the absolute maximum
        for rate_type in ["Peninsular", "Insular"]:
            for scheme in eligible_schemes_by_land_use[land_use_code]:
                # Use rates specific to the current rate_type
                rate_details = scheme['rates'].get(rate_type)
                if not rate_details: continue # Skip if rates for this type are not defined
                
                # Determine the Base Rate using the Tiered Calculation Rule
                current_rate = Decimal('0.0')
                if 'Flat' in rate_details:
                    current_rate = rate_details['Flat']
                else:
                    L = rate_details['Threshold_ha']
                    current_rate = rate_details['Tier_1'] if (L is not None and area <= L) else rate_details['Tier_2']

                # Calculate Total Payment per Hectare (Base + Pluriannuality Bonus)
                payment_per_ha_total = current_rate
                if scheme['pluriannuality_applicable']:
                    payment_per_ha_total += PLURIANNUALITY_BONUS_PER_HA
                
                # Compare and assign the best scheme
                payment_per_ha_total = payment_per_ha_total if "/" not in str(payment_per_ha_total) else Decimal(str("0"))
                if payment_per_ha_total > best_payment_per_ha:
                    best_payment_per_ha = payment_per_ha_total
                    
                    # Store the scheme and the rate_type that yielded the best result
                    best_scheme_assignment = scheme.copy()
                    best_scheme_assignment['best_rate_type'] = rate_type
                    best_scheme_assignment['payment_per_ha_total'] = payment_per_ha_total
                    # Note: We don't store the applied_rate/tier here, we calculate both fully in step 4

        if best_scheme_assignment:
            land_use_assignments[land_use_code] = best_scheme_assignment
    return land_use_assignments


def get_ecoschemes_rates_and_totals(parsed_data, land_use_assignments) -> dict:
    final_scheme_results = {} 
    
    for land_use_code, assignment in land_use_assignments.items():
        scheme_id = assignment.get('id', 'N/A')
        area = parsed_data[land_use_code]['area']
        
        scheme_key = f"{scheme_id}_{assignment['subtype']}" if scheme_id != 'N/A' else 'Non-Eligible'
        
        if scheme_key not in final_scheme_results:
            if scheme_key == 'Non-Eligible':
                 final_scheme_results[scheme_key] = {
                    "Ecoscheme_ID": "N/A", "Ecoscheme_Name": "Non-Eligible", "Ecoscheme_Subtype": None,
                    "Total_Area_ha": Decimal('0.0'), "Land_Uses": [], 
                    "Total_Base_Payment_Peninsular": Decimal('0.0'), "Total_Base_Payment_Insular": Decimal('0.0'),
                }
            else:
                final_scheme_results[scheme_key] = {
                    "Ecoscheme_ID": assignment['id'],
                    "Ecoscheme_Name": assignment['name'],
                    "Ecoscheme_Subtype": assignment['subtype'],
                    "Total_Area_ha": Decimal('0.0'),
                    "Land_Uses": [], 
                    "rates": assignment['rates'], # Full rates dictionary
                    "pluriannuality_applicable": assignment['pluriannuality_applicable'],
                    "Total_Base_Payment_Peninsular": Decimal('0.0'),
                    "Total_Base_Payment_Insular": Decimal('0.0'),
                }
        
        final_scheme_results[scheme_key]["Total_Area_ha"] += area
        final_scheme_results[scheme_key]["Land_Uses"].append(land_use_code)
    return final_scheme_results


def calculate_payments_for_rate_type(area: Decimal, rate_details: dict, pluri_applicable: bool) -> dict:
    """Calculates Base and Pluriannuality payments for a single area type (Peninsular or Insular)."""
    
    current_rate = Decimal('0.0')
    applied_tier = "N/A"
    
    if 'Flat' in rate_details:
        # Flat Rate
        current_rate = rate_details['Flat']
        applied_tier = "Flat Rate"
    else:
        # Tiered Rate
        L = rate_details['Threshold_ha']
        if L is not None and area <= L:
            current_rate = rate_details['Tier_1']
            applied_tier = "Tier 1"
        else:
            current_rate = rate_details['Tier_2']
            applied_tier = "Tier 2"

    # Payments
    current_rate = current_rate if "/" not in str(current_rate) else Decimal(str("0"))
    base_payment = area * current_rate
    payment_with_pluri = base_payment
    
    if pluri_applicable:
        payment_with_pluri = area * (current_rate + PLURIANNUALITY_BONUS_PER_HA)
        
    return {
        "Applied_Base_Payment_EUR": float(current_rate.quantize(ROUNDING_RATE, rounding=ROUND_HALF_UP)),
        "Total_Base_Payment_EUR": float(base_payment.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Total_with_Pluriannuality_EUR": float(payment_with_pluri.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Applicable": f"Yes ({applied_tier} Applied)" if applied_tier != "Flat Rate" else "Yes (Flat Rate)"
    }


# Example usage
import json
import os

classificiation_filepath =  os.path.join(os.getcwd(), "AgrIA_server/assets/LLM_assets/prompts/classification.json")
out_path = "lol.json"
print("classificiation_filepath", classificiation_filepath)

with open(classificiation_filepath, 'r') as file:
    all_rules_list = json.load(file)["EN"]

# Convert the list of dictionaries back into a valid JSON string
rules_json_str = json.dumps(all_rules_list) 

print("rules_json_str", rules_json_str[:150], "...")
print("type", type(rules_json_str))
input = """IMAGE DATE: 2025-6-6
LAND USES DETECTED: 13

- Land Use: TA
- Eligible surface (ha): 22.7474
- Irrigation Coeficient: 83.0%

- Land Use: VI
- Eligible surface (ha): 9.3441
- Irrigation Coeficient: 89.88%
- Slope Coeficient: 1.01%

- Land Use: FO
- Eligible surface (ha): 3.4562
- Irrigation Coeficient: 80.0%

- Land Use: AG
- Eligible surface (ha): 0.4099
- Irrigation Coeficient: 0.0%

- Land Use: PA
- Eligible surface (ha): 0.1257
- Irrigation Coeficient: 100.0%

- Land Use: PS
- Eligible surface (ha): 0.2272
- Irrigation Coeficient: 100.0%

- Land Use: PR
- Eligible surface (ha): 4.0175
- Irrigation Coeficient: 100.0%

- Land Use: CA
- Eligible surface (ha): 0.4838
- Irrigation Coeficient: 0.0%

- Land Use: IM
- Eligible surface (ha): 1.9813
- Irrigation Coeficient: 0.0%

- Land Use: MT
- Eligible surface (ha): 2.6999
- Irrigation Coeficient: 20.0%

- Land Use: ED
- Eligible surface (ha): 0.0894
- Irrigation Coeficient: 0.0%

- Land Use: ZU
- Eligible surface (ha): 0.0086
- Irrigation Coeficient: 0.0%

- Land Use: FY
- Eligible surface (ha): 0.1422
- Irrigation Coeficient: 100.0%
- Slope Coeficient: 1.7%

TOTAL ELIGIBLE SURFACE (ha): 45.733
"""

dict = calculate_ecoscheme_payment_exclusive(input, str(rules_json_str))
print("dict",dict)

with open(out_path, 'w') as file:
    json.dump(dict, file, indent=4)

