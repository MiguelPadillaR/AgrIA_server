# Setup VLM
import json
import os
import pandas as pd
import structlog

from datetime import datetime, timedelta
from PIL import Image
from google import genai
from google.genai import types

from ...services.sigpac_tools_v2.find import find_from_cadastral_registry
from ...utils.parcel_finder_utils import reset_dir
from ...config.constants import SEN2SR_SR_DIR, TEMP_DIR
from ...services.sen2sr.constants import GEOJSON_FILEPATH


from .constants import BM_JSON_DIR, BM_LLM_DIR, BM_SR_IMAGES_DIR, CADASTRAL_REF_LIST_PAPER, DATES_PAPER, IS_PAPER_DATA
from ...services.parcel_finder_service import download_sen2sr_parcel_image
from ..sr.utils import copy_file_to_dir
from ...utils.chat_utils import generate_image_context_data
from ...config.llm_client import client

from .llm_setup import generate_system_instructions
from .utils import n_random_dates_between

# init dirs
os.makedirs(BM_LLM_DIR, exist_ok=True)
os.makedirs(BM_JSON_DIR, exist_ok=True)
os.makedirs(BM_SR_IMAGES_DIR, exist_ok=True)

# Setup input dataframe
input_col_names =  ['cadastral_ref', 'image_date', 'parcel_desc', 'sr_image_filepath']
out_col_names =  ['cadastral_ref', 'parcel_area', 'land_uses_amount', 'applicable_ecoschemes', 'predicted_ecoschemes', 'applicable_base_aid','predicted_base_aid', 'applicable_plur_aid','predicted_plur_aid', 'ecoschemes_F1', 'base_aid_diff', 'plur_aid_diff', 'base_aid_MAE', 'plur_aid_MAE', 'plur_aid_MAPE', 'base_aid_MAPE', 'exec_time']
input_df  = pd.DataFrame(columns = input_col_names)
out_df  = pd.DataFrame(columns = out_col_names)

logger = structlog.get_logger()

logger.debug(f"DataFrames initialized")

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def setup_ndates(n_dates:int, to_date: datetime=datetime.today(), delta_days: int=4 * 365):
    # Get all parcel descriptions
    from_date = to_date - timedelta(days=delta_days)
    dates = n_random_dates_between(from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), n_dates)
    logger.debug(f"Generated random dates: {dates}")
    
    return dates

def get_parcel_data_and_description(cadastral_ref, image_date):
    # Get parcel metadata and geometry
    geometry, metadata = find_from_cadastral_registry(cadastral_ref)
    os.makedirs(SEN2SR_SR_DIR, exist_ok=True)
    with open(GEOJSON_FILEPATH, "w") as file:
        file.write(str(geometry).replace("'", '"').replace("(","[").replace(")","]"))  # format GeoJSON correctly
    logger.debug(f"Metadata keys: {list(metadata.keys())}")

    # Get parcel's description
    land_uses = metadata.get('usos', None)
    query = metadata.get('query', None)
    parcel_metadata = generate_image_context_data(image_date, land_uses, query)
    parcel_desc = parcel_metadata['en']
    logger.debug(f"Parcel description: {parcel_desc}")
    
    # Extract parcel area safely
    total_parcel_area = None
    if isinstance(parcel_metadata, dict) and 'TOTAL ELIGIBLE SURFACE (ha):' in parcel_metadata.get('en', ''):
        total_parcel_area = float(parcel_metadata['en'].split("TOTAL ELIGIBLE SURFACE (ha):")[-1])
    logger.debug(f"Parcel area: {total_parcel_area}, Image date: {image_date}")
 
    return geometry, parcel_desc

def get_parcel_image(cadastral_ref, geometry, image_date):    
    # Get and save SR parcel image
    sr_image_filepath = os.path.join(TEMP_DIR, download_sen2sr_parcel_image(geometry, image_date))
    logger.debug(f"SR image downloaded: {sr_image_filepath}")
    image_filepath = copy_file_to_dir(str(sr_image_filepath), BM_SR_IMAGES_DIR)
    
    # Rename file
    filepath_no_ext, ext = os.path.splitext(os.path.basename(sr_image_filepath))
    new_image_filepath = BM_SR_IMAGES_DIR / (filepath_no_ext + f"_{cadastral_ref}{ext}")
    os.rename(image_filepath, new_image_filepath)
    image_filepath = new_image_filepath
    logger.debug(f"SR image copied to: {new_image_filepath}")

    return image_filepath

def get_llm_response(image_filepath, parcel_desc): 
    prompt = f"Describe the parcels based on the following information and image:\n\n{parcel_desc}"
    logger.debug(f'Prompt generated:\n"{prompt[:150]}..."')
    image = Image.open(image_filepath)
    logger.debug(f"Image loaded for inference")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=generate_system_instructions()
            ),
        contents=[image, prompt]
    )
    logger.debug(f"AgrIA's response:\n---BEGIN\n{response.text}\n---END")

    return response

def extract_json_from_reply(raw_text: str):
    # Split into lines and remove first line (e.g., ```json or BEGIN)
    lines = raw_text.splitlines()
    
    # Find opening and closing JSON braces
    i, j = 0, len(lines) - 1
    start_idx = end_idx = None
    found = False
    while j > 0 and not found:
        start_idx = i if "{" is lines[i] else start_idx
        end_idx = j + 1 if "}" is lines[j] else end_idx
        found = start_idx is not None  and end_idx is not None
        i += 1
        j -= 1
    logger.debug(f"JSON found between lines {start_idx} and {end_idx}.")

    # Keep only JSON portion
    cleaned_text = "\n".join(lines[start_idx:end_idx]).replace("```", "").strip()

    # Sanity check
    if not cleaned_text or "{" not in cleaned_text:
        print("[WARNING] No valid JSON found in LLM response, skipping...")

    # Write to temp file
    output_path = BM_LLM_DIR / f"{cadastral_ref}_out.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    # --- Read it back safely ---
    data = ''
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to decode JSON: {e}")
        print("[DEBUG] Cleaned text preview:\n", cleaned_text[:300])
    logger.debug(f"Data from JSON file:\n{data}")

    # --- Normalize JSON into dataframe ---
    json_df = pd.json_normalize(
        data,
        record_path=["Estimated_Total_Payment"],
        meta=[
            "Report_Type",
            "Total_Parcel_Area_ha",
            ["Calculation_Context", "Rate_Applied"],
            ["Calculation_Context", "Source"],
            ["Final_Results", "Total_Aid_without_Pluriannuality_EUR"],
            ["Final_Results", "Total_Aid_with_Pluriannuality_EUR"],
        ],
        errors="ignore"
    )
    return json_df

try:
    i = 0
    total_time = 0
    reset_dir(BM_SR_IMAGES_DIR)
    reset_dir(BM_LLM_DIR)

    # Get all cadastral references and date data
    cadastral_ref_list = CADASTRAL_REF_LIST_PAPER if IS_PAPER_DATA else ["26002A001000010000EQ", "14048A001001990000RM","45054A067000090000QA", "43157A024000010000KE", "34039A005000020000YQ", "27020A319000010000QL", "43022A037000430000JO", "50074A045000370000KA", "50074A014000730000KS", "25015A501101860000RF", "25142A002000430000BP", "22121A007001610000UD", "22145A011000110000PI", "22061A018000530000GG", "26002A004009350000EI", "41079A057000020000JR", "41012A018000030000TX", "23086A02500051FA", "23060A065002370000EX", "29055A040000040000HL", "41062A012001000000UQ", "41062A012000960000UB", ""]  # TODO
    dates = DATES_PAPER if IS_PAPER_DATA else setup_ndates(len(cadastral_ref_list))

    for cadastral_ref in cadastral_ref_list:
        if len(cadastral_ref) is not 20:
            continue
        init_time = datetime.now()
        # Set output row
        out_row  = pd.DataFrame(columns = out_col_names)
        
        # Get parcel input data
        image_date = dates[i]
        geometry, parcel_desc = get_parcel_data_and_description(cadastral_ref, image_date)
        image_filepath = get_parcel_image(cadastral_ref, geometry, image_date)
        
        # Add data to input df
        new_row = pd.DataFrame([{
            'cadastral_ref': cadastral_ref,
            'image_date': image_date,
            'parcel_desc':  parcel_desc ,  # Assuming 'en' for English description
            'sr_image_filepath': image_filepath
        }])

        input_df = pd.concat([input_df, new_row], ignore_index=True)
        logger.debug(f"Input DataFrame updated ({len(input_df)} entries)")
        
        reset_dir(TEMP_DIR)
        

        # Run LLM and get response
        raw_text = get_llm_response(image_filepath, parcel_desc).text.strip()
        exec_time = str(timedelta(seconds=(datetime.now() - init_time).total_seconds()))
        # Parse LLM reply
        json_df = extract_json_from_reply(raw_text)
        es_list = json_df["Ecoscheme_ID"].values.tolist().sort()
        # es_list = str(es_list).replace("'", "").replace('"', "").replace("[", "").replace("]", "") if IS_PAPER_DATA else es_list
        out_row = pd.DataFrame([{
            'cadastral_ref': cadastral_ref,
            'parcel_area': json_df.get('Total_Parcel_Area_ha', [None])[0],
            'land_uses_amount': len(parcel_desc.split("Land")) - 1,
            'predicted_ecoschemes': es_list,
            'predicted_base_aid': json_df.get('Final_Results.Total_Aid_without_Pluriannuality_EUR', [None])[0],
            'predicted_plur_aid': json_df.get('Final_Results.Total_Aid_with_Pluriannuality_EUR', [None])[0],
            'exec_time': exec_time,
        }])
        
        out_df = pd.concat([out_df, out_row], ignore_index=True)
        logger.debug(f"Output DataFrame updated ({len(out_df)} entries)")

        i+=1
        time_taken = (datetime.now() - init_time).total_seconds()
        time_taken_formatted = str(timedelta(seconds=time_taken))
        logger.debug(f"Time taken for parcel processing {time_taken_formatted}")
        total_time += time_taken
finally:
    total_time_formatted = str(timedelta(seconds=total_time))
    logger.debug(f"BENCHMARK EXEC. TIME {total_time_formatted}")
    input_df = input_df.fillna(0)
    out_df = out_df.fillna(0)

    # Save dataframes
    prefix = "PAPER_" if IS_PAPER_DATA else ""
    input_filepath = BM_JSON_DIR / f"{prefix}{timestamp}_in.tsv"
    out_filepath = BM_JSON_DIR / f"{prefix}{timestamp}_out.tsv"
    input_df.to_csv(input_filepath, sep="\t", index=False)
    out_df.to_csv(out_filepath, sep="\t", index=False)
    logger.debug(f"Input & output dataframes saved to:\n{input_filepath}\n{out_filepath}")

