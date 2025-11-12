import re
import json
import structlog
from decimal import Decimal, ROUND_HALF_UP

from .constants import CLASSIFICATION_OUT_DIR, LANG, OG_CLASSIFICATION_FILEPATH
from ...utils.parcel_finder_utils import reset_dir

# Fixed constant for the pluriannuality bonus (€25.00/ha) as per instructions
PLURIANNUALITY_BONUS_PER_HA = Decimal('25.00')

# Define rounding constants
ROUNDING_RATE = Decimal('0.000001') # 6 decimals for applied rate
ROUNDING_AREA = Decimal('0.0001')   # 4 decimals for total area
ROUNDING_PAYMENT = Decimal('0.01')  # 2 decimals for total payments

logger = structlog.get_logger()

# --- Main Calculation Function (Modified) ---

def calculate_ecoscheme_payment_exclusive(input_data_str: str, lang: str=LANG, rules_json_filepath: str=OG_CLASSIFICATION_FILEPATH) -> dict:
    """
    Processes land use input data and calculates estimated Eco-scheme payments
    by applying the Critical Exclusivity Rule (choosing the highest payment/ha
    across all rate types) and including both Peninsular and Insular calculations.
    """

    # --- 1. PREPARE RULES AND CONSTANTS ---
    with open(rules_json_filepath, 'r') as file:
        all_rules_list = json.load(file)
    rules_json_str = json.dumps(all_rules_list[lang.upper()]) 

    try:
        rules_data_list = json.loads(rules_json_str.strip())
    except json.JSONDecodeError:
        # Fallback for non-list JSON string (often means str(dict) was passed)
        rules_data_list = json.loads(f'[{rules_json_str.strip()}]')
    
    eligible_schemes_by_land_use, non_eligible_uses = get_ecoscheme_rules_data(rules_data_list)

    # --- 2. PARSE INPUT DATA AND CALCULATE TOTAL AREA ---
    
    land_use_regex = {
        "en": r'- Land Use: ([A-Z]{2})\s*- Eligible surface \(ha\): ([\d\.]+)\s*- Irrigation Coeficient: ([\d\.]+%)\s*(?:- Slope Coeficient: ([\d\.]+%))?',
        "es": r'- Tipo de Uso:\s*([A-Z]{2})\s*- Superficie admisible \(ha\):\s*([\d\.]+)\s*- Coef\. de Regadío:\s*([\d\.]+%)\s*(?:- Pendiente media:\s*([\d\.]+%))?'
        }
    land_use_blocks = re.findall(land_use_regex[lang.lower()], input_data_str, re.DOTALL)

    parsed_data = {}
    total_parcel_area = Decimal('0.0')

    for match in land_use_blocks:
        land_use_code, area_str, irrigation_coef, slope_coef = match
        area = Decimal(area_str)
        total_parcel_area += area
        parsed_data[land_use_code] = {"area": area, "irrigation_coef": irrigation_coef, "slope_coef": slope_coef}
    
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
    # logger.debug(f"eligible_schemes_by_land_use\t{eligible_schemes_by_land_use}")
    logger.debug(f"land_use_blocks\t{land_use_blocks}")
    logger.debug(f"land_use_assignments\t{land_use_assignments}")
    logger.debug(f"final_scheme_results\t{final_scheme_results}")
    logger.debug(f"sorted_keys\t{sorted_keys}")
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

    # clarifications = []

    final_results = {
        "Applicable_Ecoschemes": sorted(list(set(applicable_ecoschemes))),
        "Total_Aid_without_Pluriannuality_EUR": float(total_aid_no_pluriannuality.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Total_Aid_with_Pluriannuality_EUR": float(total_aid_with_pluriannuality.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP))
        # "Clarifications": clarifications
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
        

        scheme_parts = scheme_full_name.split(' - ')
        if len(scheme_parts) < 2:
            non_eligible_uses.update(rule['Land_Uses'].split(', '))
            continue
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
            tier1 = 0 if '/' in str(key_rates['Tier_1']) else Decimal(str(key_rates['Tier_1']))
            tier2 = 0 if '/' in str(key_rates['Tier_2']) else Decimal(str(key_rates['Tier_2']))
            base_rate_details[key] = {'Tier_1': tier1, 'Tier_2': tier2, 'Threshold_ha': threshold}
        else:
            # Flat rate
            # Handle potential string/Decimal conversion
            flat_rate_value = key_rates if isinstance(key_rates, str) else Decimal(str(key_rates))
            base_rate_details[key] = {'Flat': flat_rate_value}
            
    return base_rate_details


def get_exclusivity_land_uses(eligible_schemes_by_land_use, non_eligible_uses, parsed_data, lang="EN") -> dict:
    land_use_assignments = {}
    
    for land_use_code, data in parsed_data.items():
        area = data.get('area', 0.0)
        irrigation = float(data.get('irrigation_coef', 0.0)[:-1])  # Input format '00.00%'
        slope = float(data.get('slope_coef')[:-1]) if len(data.get('slope_coef')) > 0 else 0.0  # Input format '00.00%'

        # Skip non-eligible uses
        if land_use_code in non_eligible_uses or land_use_code not in eligible_schemes_by_land_use:
            land_use_assignments[land_use_code] = {
                'id': 'N/A',
                'name': 'Non-Eligible',
                'subtype': None,
                'payment_per_ha': Decimal('0')
            }
            continue

        best_payment_per_ha = Decimal('-1')
        best_scheme_assignment = None

        for rate_type in ["Peninsular", "Insular"]:
            for scheme in eligible_schemes_by_land_use[land_use_code]:
                scheme_id = scheme["id"]
                scheme_subtype = scheme["subtype"]
                
                # Check irrigation and slope coefficient for better assignment accuracy
                if not is_valid_rate_for_coefficients(scheme_id, scheme_subtype, slope, irrigation):
                    continue

                # Get rate details
                rate_details = scheme['rates'].get(rate_type)
                if not rate_details:
                    continue

                # Determine base rate
                if 'Flat' in rate_details:
                    current_rate = Decimal(rate_details['Flat']) if rate_details['Flat'] != "N/A" else Decimal("0")
                else:
                    threshold = rate_details.get('Threshold_ha')
                    tier1 = Decimal(rate_details.get('Tier_1', 0))
                    tier2 = Decimal(rate_details.get('Tier_2', 0))
                    current_rate = tier1 if (threshold and area <= threshold) else tier2

                # Add pluriannuality if applicable
                payment_per_ha_total = current_rate
                if scheme.get('pluriannuality_applicable'):
                    payment_per_ha_total += PLURIANNUALITY_BONUS_PER_HA

                # Validate value and assign if better
                if payment_per_ha_total > best_payment_per_ha:
                    best_payment_per_ha = payment_per_ha_total
                    best_scheme_assignment = scheme.copy()
                    best_scheme_assignment['best_rate_type'] = rate_type
                    best_scheme_assignment['payment_per_ha_total'] = payment_per_ha_total

        # Store final best result
        if best_scheme_assignment:
            land_use_assignments[land_use_code] = best_scheme_assignment
        else:
            land_use_assignments[land_use_code] = {
                'id': 'N/A',
                'name': 'Non-Eligible',
                'subtype': None,
                'payment_per_ha': Decimal('0')
            }

    return land_use_assignments


def is_valid_rate_for_coefficients(scheme_id, subtype, slope, irrigation):
    """
    Validate if an ecoscheme is compatible with the slope or irrigation coefficients.
    Returns True if valid, False otherwise.
    """
    slope_kw = {
        "flat": ["Flat Woody Crops", "Terrenos Llanos"],
        "medium": ["Medium Slope", "Pendiente Media"],
        "steep": ["Steep Slope", "Pendiente Elevada", "Terraces", "Balcanes"],
    }
    irrig_kw = {
        "irrigated": ["Irrigated", "Regadío"],
        "humid": ["Rainfed Humid", "Húmedo"],
        "rainfed": ["Rainfed", "Secano"],
    }

    # --- P6 / P7 schemes: depend on slope ---
    if any(k in scheme_id for k in ("P6", "P7")):
        if slope > 12:
            return any(k in subtype for k in slope_kw["steep"])
        elif 6 < slope <= 12:
            return any(k in subtype for k in slope_kw["medium"])
        else:  # slope <= 6
            return any(k in subtype for k in slope_kw["flat"])

    # --- P3 / P4 schemes: depend on irrigation ---
    elif any(k in scheme_id for k in ("P3", "P4")):
        if irrigation > 50:
            return any(k in subtype for k in irrig_kw["irrigated"])
        elif 25 < irrigation <= 50:
            return any(k in subtype for k in irrig_kw["humid"])
        else:  # irrigation <= 20
            return any(k in subtype for k in irrig_kw["rainfed"])

    # Other schemes: no restriction
    return True


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
    
    payment_with_pluri = Decimal(str(payment_with_pluri))
    current_rate = Decimal(str(current_rate))
    base_payment = Decimal(str(base_payment))
    
    return {
        "Applied_Base_Payment_EUR": float(current_rate.quantize(ROUNDING_RATE, rounding=ROUND_HALF_UP)),
        "Total_Base_Payment_EUR": float(base_payment.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Total_with_Pluriannuality_EUR": float(payment_with_pluri.quantize(ROUNDING_PAYMENT, rounding=ROUND_HALF_UP)),
        "Applicable": f"Yes ({applied_tier} Applied)" if applied_tier != "Flat Rate" else "Yes (Flat Rate)"
    }


# Example usage
def demo():
    import json
    import os

    cad_ref_dict = {
        "en": {
            "26002A001000010000EQ": """IMAGE DATE: 2025-6-6
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
        """,
            "14048A001001990000RM": """IMAGE DATE: 2024-10-19
        LAND USES DETECTED: 2

        - Land Use: OV
        - Eligible surface (ha): 7.4659
        - Irrigation Coeficient: 0.0%
        - Slope Coeficient: 12.4%

        - Land Use: CA
        - Eligible surface (ha): 0.0352
        - Irrigation Coeficient: 0.0%

        TOTAL ELIGIBLE SURFACE (ha): 7.501

        """,
            "45054A067000090000QA": """IMAGE DATE: 2025-03-30
        LAND USES DETECTED: 2

        - Land Use: IM
        - Eligible surface (ha): 0.0065
        - Irrigation Coeficient: 0.0%

        - Land Use: TA
        - Eligible surface (ha): 42.8326
        - Irrigation Coeficient: 0.0%

        TOTAL ELIGIBLE SURFACE (ha): 42.839

        """,
            "43157A024000010000KE": """IMAGE DATE: 2024-03-15
        LAND USES DETECTED: 4

        - Land Use: OV
        - Eligible surface (ha): 30.7162
        - Irrigation Coeficient: 0.0%
        - Slope Coeficient: 4.7%

        - Land Use: PR
        - Eligible surface (ha): 0.3574
        - Irrigation Coeficient: 0.0%

        - Land Use: IM
        - Eligible surface (ha): 0.0966
        - Irrigation Coeficient: 0.0%

        - Land Use: ED
        - Eligible surface (ha): 0.0065
        - Irrigation Coeficient: 0.0%

        TOTAL ELIGIBLE SURFACE (ha): 31.177

        """
        },
        "es": {
            "26002A001000010000EQ": """FECHA DE IMAGEN: 2025-6-6
        TIPOS DE USO DETECTADAS: 13

        - Tipo de Uso: TA
        - Superficie admisible (ha): 22.7474
        - Coef. de Regadío: 83.0%

        - Tipo de Uso: VI
        - Superficie admisible (ha): 9.3441
        - Coef. de Regadío: 89.88%
        - Pendiente media: 1.01%

        - Tipo de Uso: FO
        - Superficie admisible (ha): 3.4562
        - Coef. de Regadío: 80.0%

        - Tipo de Uso: AG
        - Superficie admisible (ha): 0.4099
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: PA
        - Superficie admisible (ha): 0.1257
        - Coef. de Regadío: 100.0%

        - Tipo de Uso: PS
        - Superficie admisible (ha): 0.2272
        - Coef. de Regadío: 100.0%

        - Tipo de Uso: PR
        - Superficie admisible (ha): 4.0175
        - Coef. de Regadío: 100.0%

        - Tipo de Uso: CA
        - Superficie admisible (ha): 0.4838
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: IM
        - Superficie admisible (ha): 1.9813
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: MT
        - Superficie admisible (ha): 2.6999
        - Coef. de Regadío: 20.0%

        - Tipo de Uso: ED
        - Superficie admisible (ha): 0.0894
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: ZU
        - Superficie admisible (ha): 0.0086
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: FY
        - Superficie admisible (ha): 0.1422
        - Coef. de Regadío: 100.0%
        - Pendiente media: 1.7%

        SUPERFICIE ADMISIBLE TOTAL (ha): 45.733
        """,
            "14048A001001990000RM": """FECHA DE IMAGEN: 2024-10-19
        TIPOS DE USO DETECTADAS: 2

        - Tipo de Uso: OV
        - Superficie admisible (ha): 7.4659
        - Coef. de Regadío: 0.0%
        - Pendiente media: 12.4%

        - Tipo de Uso: CA
        - Superficie admisible (ha): 0.0352
        - Coef. de Regadío: 0.0%

        SUPERFICIE ADMISIBLE TOTAL (ha): 7.501
        """,
            "45054A067000090000QA": """FECHA DE IMAGEN: 2025-03-30
        TIPOS DE USO DETECTADAS: 2

        - Tipo de Uso: IM
        - Superficie admisible (ha): 0.0065
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: TA
        - Superficie admisible (ha): 42.8326
        - Coef. de Regadío: 0.0%

        SUPERFICIE ADMISIBLE TOTAL (ha): 42.839
        """,
            "43157A024000010000KE": """FECHA DE IMAGEN: 2024-03-15
        TIPOS DE USO DETECTADAS: 4

        - Tipo de Uso: OV
        - Superficie admisible (ha): 30.7162
        - Coef. de Regadío: 0.0%
        - Pendiente media: 4.7%

        - Tipo de Uso: PR
        - Superficie admisible (ha): 0.3574
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: IM
        - Superficie admisible (ha): 0.0966
        - Coef. de Regadío: 0.0%

        - Tipo de Uso: ED
        - Superficie admisible (ha): 0.0065
        - Coef. de Regadío: 0.0%

        SUPERFICIE ADMISIBLE TOTAL (ha): 31.177
        """
        }
    }

    languages = ["EN", "ES"]

    os.makedirs(CLASSIFICATION_OUT_DIR, exist_ok=True)
    reset_dir(CLASSIFICATION_OUT_DIR)

    for lang in languages:
        # Get ecoschemes classification
        data_dict = cad_ref_dict[lang.lower()]
        for key in data_dict.keys():
            output_dict = calculate_ecoscheme_payment_exclusive(data_dict[key], lang)
            out_path = CLASSIFICATION_OUT_DIR / f"{key}_example_{lang}.json"
            with open(out_path, 'w') as file:
                json.dump(output_dict, file, indent=4)
            logger.info(f"Ecoscheme classification saved to {out_path}")
        print(lang)

# demo()