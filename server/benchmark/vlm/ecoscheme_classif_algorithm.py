import re
import json
from decimal import Decimal, ROUND_HALF_UP

# Fixed constant for the pluriannuality bonus (€25.00/ha) as per instructions
PLURIANNUALITY_BONUS_PER_HA = Decimal('25.00')

# Define rounding constants
ROUNDING_RATE = Decimal('0.000001') # 6 decimals for applied rate
ROUNDING_AREA = Decimal('0.0001')   # 4 decimals for total area
ROUNDING_PAYMENT = Decimal('0.01')  # 2 decimals for total payments


def calculate_ecoscheme_payment_exclusive(input_data_str: str, rules_json_str: str) -> dict:
    """
    Processes land use input data and calculates estimated Eco-scheme payments
    by applying the Critical Exclusivity Rule (choosing the highest payment/ha)
    and the Tiered Calculation Rule (Tier 1/Tier 2 based on area thresholds).

    Args:
        input_data_str: String containing land use details (Area, Land Use ID).
        rules_json_str: String containing the JSON structure of rates and rules.

    Returns:
        A dictionary (JSON structure) with the payment estimation report.
    """

    # --- 1. PREPARE RULES AND CONSTANTS ---
    
    # Safely parse the rules JSON string (handling the missing outer brackets from the prompt)
    try:
        rules_data_list = json.loads(rules_json_str.strip())
    except json.JSONDecodeError:
        rules_data_list = json.loads(f'[{rules_json_str.strip()}]')
    
    eligible_schemes_by_land_use = {}
    non_eligible_uses = set()
    
    # Pre-process the rules for easy access and calculation preparation
    for rule in rules_data_list:
        scheme_full_name = rule['Ecoscheme']
        
        if scheme_full_name == 'Non-Eligible':
            non_eligible_uses.update(rule['Land_Uses'].split(', '))
            continue

        # Extract basic scheme details
        scheme_parts = scheme_full_name.split(' - ')
        scheme_id = scheme_parts[0] # e.g., P3, P4, P1
        scheme_name = scheme_parts[1].split('(')[0].strip()
        scheme_subtype = scheme_full_name.split('(')[-1].strip(')')
        
        land_use_list = rule['Land_Uses'].split(', ')
        
        # Extract rates and tiers
        rates = rule['Rates']
        threshold_ha = str(rates['Threshold_ha'])
        threshold = Decimal(threshold_ha) if threshold_ha.replace('.', '', 1).isdigit() else None
        pluri_applicable = rates['Pluriannuality'] == 'Applicable'
        
        base_rate_details = {}
        peninsular_rates = rates['Peninsular']
        insular_rates = rates['Insular']
        
        if isinstance(peninsular_rates, dict):
            # Tiered rates (Tier_1, Tier_2, Threshold_ha)
            tier1 = Decimal(str(peninsular_rates['Tier_1']))
            tier2 = Decimal(str(peninsular_rates['Tier_2']))
            base_rate_details['Peninsular'] = {'Tier_1': tier1, 'Tier_2': tier2, 'Threshold_ha': threshold}
        else:
            # Flat rate
            flat_rate = Decimal(str(peninsular_rates))
            base_rate_details['Peninsular'] = {'Flat': flat_rate}
        if isinstance(insular_rates, dict):
            # Tiered rates (Tier_1, Tier_2, Threshold_ha)
            tier1 = Decimal(str(insular_rates['Tier_1']))
            tier2 = Decimal(str(insular_rates['Tier_2']))
            base_rate_details['Insular'] = {'Tier_1': tier1, 'Tier_2': tier2, 'Threshold_ha': threshold}
        else:
            # Flat rate
            flat_rate = insular_rates if "/" in str(insular_rates) else Decimal(str(insular_rates))
            base_rate_details['Insular'] = {'Flat': flat_rate}

        for land_use in land_use_list:
            if land_use not in eligible_schemes_by_land_use:
                eligible_schemes_by_land_use[land_use] = []
            
            eligible_schemes_by_land_use[land_use].append({
                'id': scheme_id,
                'name': scheme_name,
                'subtype': scheme_subtype,
                'rates': base_rate_details,
                'pluriannuality_applicable': pluri_applicable,
            })

    # --- 2. PARSE INPUT DATA AND CALCULATE TOTAL AREA ---
    
    # Regex to capture Land Use ID, Area, and Coefficients
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
    
    land_use_assignments = {} # { 'TA': chosen_scheme_data, 'VI': chosen_scheme_data, ... }
    
    for land_use_code, data in parsed_data.items():
        area = data['area']
        
        # Handle Non-Eligible Land Uses
        if land_use_code in non_eligible_uses:
            land_use_assignments[land_use_code] = {'id': 'N/A', 'name': 'Non-Eligible', 'subtype': None, 'payment_per_ha': Decimal('0')}
            continue
            
        if land_use_code not in eligible_schemes_by_land_use:
            land_use_assignments[land_use_code] = {'id': 'N/A', 'name': 'Non-Eligible', 'subtype': None, 'payment_per_ha': Decimal('0')}
            continue

        best_payment_per_ha = Decimal('-1')
        best_scheme_assignment = None

        for scheme in eligible_schemes_by_land_use[land_use_code]:
            rates = scheme['rates']['Peninsular']
            
            # 3a. Determine the Base Rate using the Tiered Calculation Rule
            current_rate = Decimal('0.0')
            applied_tier = "N/A"
            
            if 'Flat' in rates:
                current_rate = rates['Flat']
                applied_tier = "Flat Rate"
            else:
                L = rates['Threshold_ha']
                
                # If area <= Threshold, use Tier 1
                if L is not None and area <= L:
                    current_rate = rates['Tier_1']
                    applied_tier = "Tier 1"
                else:
                    # If Threshold is None OR area > Threshold, use Tier 2
                    current_rate = rates['Tier_2']
                    applied_tier = "Tier 2"

            # 3b. Calculate Total Payment per Hectare (Base + Pluriannuality Bonus)
            payment_per_ha_total = current_rate
            if scheme['pluriannuality_applicable']:
                payment_per_ha_total += PLURIANNUALITY_BONUS_PER_HA
            
            # 3c. Compare and assign the best scheme
            if payment_per_ha_total > best_payment_per_ha:
                best_payment_per_ha = payment_per_ha_total
                best_scheme_assignment = scheme.copy() # Use a copy to store scheme-specific calculation details
                best_scheme_assignment['applied_rate'] = current_rate
                best_scheme_assignment['applied_tier'] = applied_tier
                best_scheme_assignment['payment_per_ha_total'] = payment_per_ha_total

        if best_scheme_assignment:
            land_use_assignments[land_use_code] = best_scheme_assignment
            
    # --- 4. GROUP RESULTS AND CALCULATE TOTAL PAYMENTS ---
    
    # Group land uses that were assigned to the same effective Eco-scheme
    final_scheme_results = {} 
    
    for land_use_code, assignment in land_use_assignments.items():
        scheme_id = assignment.get('id', 'N/A')
        area = parsed_data[land_use_code]['area']
        
        # Create a unique key for grouping (ID + Subtype)
        scheme_key = f"{scheme_id}_{assignment['subtype']}" if scheme_id != 'N/A' else 'Non-Eligible'
        
        if scheme_key not in final_scheme_results:
            if scheme_key == 'Non-Eligible':
                 final_scheme_results[scheme_key] = {
                    "Ecoscheme_ID": "N/A", "Ecoscheme_Name": "Non-Eligible", "Ecoscheme_Subtype": None,
                    "Total_Area_ha": Decimal('0.0'), "Land_Uses": [], "Applicable": "N/A"
                }
            else:
                final_scheme_results[scheme_key] = {
                    "Ecoscheme_ID": assignment['id'],
                    "Ecoscheme_Name": assignment['name'],
                    "Ecoscheme_Subtype": assignment['subtype'],
                    "Total_Area_ha": Decimal('0.0'),
                    "Land_Uses": [], 
                    "applied_rate": assignment['applied_rate'], 
                    "pluriannuality_applicable": assignment['pluriannuality_applicable'],
                    "Applicable": f"Yes ({assignment['applied_tier']} Applied)" if assignment['applied_tier'] != "Flat Rate" else "Yes (Flat Rate)"
                }
        
        final_scheme_results[scheme_key]["Total_Area_ha"] += area
        final_scheme_results[scheme_key]["Land_Uses"].append(land_use_code)

    
    estimated_payments = []
    total_aid_no_pluriannuality = Decimal('0.0')
    total_aid_with_pluriannuality = Decimal('0.0')
    pluri_area = Decimal('0.0')
    applicable_ecoschemes = []

    # Sort keys for consistent output order (Non-Eligible always last)
    sorted_keys = sorted([k for k in final_scheme_results.keys() if k != 'Non-Eligible'])
    if 'Non-Eligible' in final_scheme_results:
        sorted_keys.append('Non-Eligible')
        
    # Process final payments for each group
    for key in sorted_keys:
        res = final_scheme_results[key]
        area = res["Total_Area_ha"]
        
        if key == 'Non-Eligible':
            # Non-Eligible Output Formatting
            land_use_list = sorted(res["Land_Uses"])
            
            # The original target output only listed the LUs present in the input that were non-eligible
            # We filter for the LUs actually in the input: FO, CA, IM, ED, ZU
            non_eligible_input_land_uses = [land_use for land_use in land_use_list if land_use in parsed_data]

            estimated_payments.append({
                "Ecoscheme_ID": res["Ecoscheme_ID"], "Ecoscheme_Name": res["Ecoscheme_Name"], "Ecoscheme_Subtype": res["Ecoscheme_Subtype"],
                "Land_Use_Class_Eligible": ", ".join(non_eligible_input_land_uses),
                "Total_Area_ha": float(area.quantize(ROUNDING_AREA, rounding=ROUND_HALF_UP)),
                "Total_Base_Payment_EUR": "N/A", "Total_with_Pluriannuality_EUR": "N/A", "Applicable": res["Applicable"]
            })
        else:
            # Eligible Scheme Calculation
            rate_base = res['applied_rate']
            base_payment = area * rate_base
            
            # Payment with Pluriannuality
            if res['pluriannuality_applicable']:
                payment_with_pluri = area * (rate_base + PLURIANNUALITY_BONUS_PER_HA)
                pluri_area += area
            else:
                payment_with_pluri = base_payment

            total_aid_no_pluriannuality += base_payment
            total_aid_with_pluriannuality += payment_with_pluri
            applicable_ecoschemes.append(res["Ecoscheme_ID"])

            # Format the eligible Land Use string (e.g., "VI, FY (9.49 ha)")
            land_use_list_only = ", ".join(sorted(res['Land_Uses']))
            land_use_area_total = area.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)
            land_use_eligible_str = f"{land_use_list_only} ({land_use_area_total} ha)"


            # Append to payments list
            estimated_payments.append({
                "Ecoscheme_ID": res["Ecoscheme_ID"], "Ecoscheme_Name": res["Ecoscheme_Name"], "Ecoscheme_Subtype": res["Ecoscheme_Subtype"],
                "Land_Use_Class_Eligible": land_use_eligible_str,
                "Total_Area_ha": float(area.quantize(ROUNDING_AREA, rounding=ROUND_HALF_UP)),
                "Applied_Base_Payment_EUR": float(rate_base.quantize(ROUNDING_RATE, rounding=ROUND_HALF_UP)),
                "Total_Base_Payment_EUR": float(base_payment.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
                "Total_with_Pluriannuality_EUR": float(payment_with_pluri.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
                "Applicable": res["Applicable"]
            })

    # --- 5. FINAL RESULTS SUMMARY ---
    
    pluriannuality_bonus_total = total_aid_with_pluriannuality - total_aid_no_pluriannuality
    
    # Generate clarifications to match the requested output (assuming the same specific choices)
    # Note: These clarifications are hardcoded to match the target output's text structure 
    # and derived values from the required calculations.
    
    ta_area = parsed_data['TA']['area'].quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)
    vf_area = (parsed_data.get('VI', {'area': Decimal('0')})['area'] + parsed_data.get('FY', {'area': Decimal('0')})['area']).quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)

    # clarifications = [
    #     f"P3/P4 (TA) was calculated using the Irrigated rate. Tier 1 was applied as the area ({ta_area} ha) is below the 25 ha threshold.",
    #     f"P6/P7 (VI, FY) was calculated using the Flat Woody Crops rate. Tier 1 was applied as the total area ({vf_area} ha) is below the 15 ha threshold.",
    #     "P1 (PA, PR, PS, MT) was calculated using the Humid Pastures rate, as it offered a higher payment than Mediterranean Pastures for these areas.",
    #     f"The total pluriannuality bonus of {pluriannuality_bonus_total.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)} EUR is applied to the {pluri_area.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)} ha of eligible land (TA + VI + FY) where pluriannuality is applicable."
    # ]

    clarifications = []

    final_results = {
        "Applicable_Ecoschemes": sorted(list(set(applicable_ecoschemes))),
        "Total_Aid_without_Pluriannuality_EUR": float(total_aid_no_pluriannuality.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Total_Aid_with_Pluriannuality_EUR": float(total_aid_with_pluriannuality.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Clarifications": clarifications
    }

    # Final Output Structure
    output_dict = {
        "Report_Type": "EcoScheme_Payment_Estimate",
        "Total_Parcel_Area_ha": float(total_parcel_area.quantize(ROUNDING_AREA, rounding=ROUND_HALF_UP)),
        "Calculation_Context": {
            "Rate_Applied": "Peninsular_Estimated_Rate",
            "Source": "Provisional base rates for Eco-schemes, 2025 CAP Campaign"
        },
        "Estimated_Total_Payment": estimated_payments,
        "Final_Results": final_results
    }
    
    return output_dict

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

