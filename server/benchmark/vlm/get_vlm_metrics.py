# Setup VLM
import json
import os
import pandas as pd

from datetime import datetime, timedelta
from PIL import Image
from google import genai
from google.genai import types

from ...services.sigpac_tools_v2.find import find_from_cadastral_registry
import re

from ...utils.parcel_finder_utils import reset_dir

from ...config.constants import SEN2SR_SR_DIR, TEMP_DIR
from ...services.sen2sr.constants import GEOJSON_FILEPATH


from .constants import BM_DIR, BM_JSON_DIR, BM_SR_IMAGES_DIR
from ...services.parcel_finder_service import download_sen2sr_parcel_image
from ..sr.utils import copy_file_to_dir
from ...utils.chat_utils import generate_image_context_data
from ...config.llm_client import client

from .llm_setup import generate_system_instructions
from .utils import n_random_dates_between



# Setup input dataframe
input_col_names =  ['cadastral_ref', 'parcel_desc', 'sr_image_filepath']
out_col_names =  ['cadastral_ref', 'parcel_area', 'land_uses_amount', 'applicable_ecoschemes', 'predicted_ecoschemes', 'applicable_base_aid','predicted_base_aid', 'applicable_plur_aid','predicted_plur_aid', 'ecoschemes_F1', 'base_aid_diff', 'plur_aid_diff', 'base_aid_MAE', 'plur_aid_MAE', 'plur_aid_MAPE', 'base_aid_MAPE', 'exec_time']
input_df  = pd.DataFrame(columns = input_col_names)
out_df  = pd.DataFrame(columns = out_col_names)

print("[DEBUG]\tDataFrames initialized")

# Get all cadastral references
cadastral_ref_list = ["26002A001000010000EQ", "14048A001001990000RM","45054A067000090000QA", "43157A024000010000KE", "34039A005000020000YQ", "27020A319000010000QL", "43022A037000430000JO", "50074A045000370000KA", "50074A014000730000KS", "25015A501101860000RF", "25142A002000430000BP", "22121A007001610000UD", "22145A011000110000PI", "22061A018000530000GG", "26002A004009350000EI", "41079A057000020000JR", "41012A018000030000TX", "23086A02500051FA", "23060A065002370000EX", "29055A040000040000HL", "41062A012001000000UQ", "41062A012000960000UB", ""]  # TODO
# Get all parcel descriptions
to_date = datetime.today()
from_date = to_date - timedelta(days=4 * 365)
dates = n_random_dates_between(from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), len(cadastral_ref_list))

print(f"[DEBUG]\tGenerated random dates: {dates}")

i = 0
total_time = 0
def get_parcel_data_and_description(cadastral_ref, image_date):
    # Get parcel metadata and geometry
    geometry, metadata = find_from_cadastral_registry(cadastral_ref)
    os.makedirs(SEN2SR_SR_DIR, exist_ok=True)
    with open(GEOJSON_FILEPATH, "w") as file:
        file.write(str(geometry).replace("'", '"').replace("(","[").replace(")","]"))  # format GeoJSON correctly
    print(f"[DEBUG]\tMetadata keys: {list(metadata.keys())}")

    # Get parcel's description
    land_uses = metadata.get('usos', None)
    query = metadata.get('query', None)
    parcel_metadata = generate_image_context_data(image_date, land_uses, query)
    parcel_desc = parcel_metadata['en']
    print(f"[DEBUG]\tParcel description: {parcel_desc}")
    
    # Extract parcel area safely
    total_parcel_area = None
    if isinstance(parcel_metadata, dict) and 'TOTAL ELIGIBLE SURFACE (ha):' in parcel_metadata.get('en', ''):
        total_parcel_area = float(parcel_metadata['en'].split("TOTAL ELIGIBLE SURFACE (ha):")[-1])
    print(f"[DEBUG]\tParcel area: {total_parcel_area}, Image date: {image_date}")
 
    return geometry, parcel_desc

def get_parcel_image(cadastral_ref, geometry, image_date):    
    # Get and save SR parcel image
    sr_image_filepath = os.path.join(TEMP_DIR, download_sen2sr_parcel_image(geometry, image_date))
    print(f"[DEBUG]\tSR image downloaded: {sr_image_filepath}")
    image_filepath = copy_file_to_dir(str(sr_image_filepath), BM_SR_IMAGES_DIR)
    
    # Rename file
    filepath_no_ext, ext = os.path.splitext(os.path.basename(sr_image_filepath))
    new_image_filepath = BM_SR_IMAGES_DIR / (filepath_no_ext + f"_{cadastral_ref}{ext}")
    os.rename(image_filepath, new_image_filepath)
    image_filepath = new_image_filepath
    print(f"[DEBUG]\tSR image copied to: {new_image_filepath}")

    return image_filepath

def get_llm_response(image_filepath, parcel_desc): 
    prompt = f"Describe the parcels based on the following information and image:\n\n{parcel_desc}"
    print(f"[DEBUG]\tPrompt generated: {prompt[:100]}...")
    image = Image.open(image_filepath)
    print(f"[DEBUG]\tImage loaded for inference")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=generate_system_instructions()
            ),
        contents=[image, prompt]
    )
    print(f"[DEBUG]\tAgrIA's response:\n---BEGIN\n{response.text}\n---END")

    return response

def extract_and_save_json(raw_text, image_filepath):
    # Try to extract fenced JSON (```json ... ```)
    fenced_json = re.search(r"```json\s*(.*?)```", raw_text, re.DOTALL)
    if fenced_json:
        json_str = fenced_json.group(1).strip()
    else:
        # Fallback: find first '{...}' JSON block if no fences
        json_block = re.search(r"(\{[\s\S]*\})", raw_text)
        if json_block:
            json_str = json_block.group(1).strip()
        else:
            raise ValueError("[ERROR]\tNo JSON found in response text.")

    try:
        # Convert JSON-like string → Python dict
        json_data = json.loads(json_str)
        print(f"[DEBUG]\tExtracted JSON data:\n{str(json_data)[:500]}...")
    except json.JSONDecodeError as e:
        print("[ERROR]\tFailed to decode JSON:", e)
        print("Raw response:\n",  "...", raw_text[-800:])
        print("Exception", e)
        raise ValueError("The response did not contain valid JSON.") from e

    # Build file path
    os.makedirs(BM_JSON_DIR, exist_ok=True)
    json_filename = f"{os.path.splitext(os.path.basename(image_filepath))[0]}.json"
    json_filepath = BM_JSON_DIR / json_filename

    # Save to file
    with open(json_filepath, "w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
    print(f"[DEBUG]]\tJSON data saved to: {json_filepath}")

    return json_data, json_filepath

try:
    for cadastral_ref in cadastral_ref_list:
        if len(cadastral_ref) is not 20:
            continue
        init_time = datetime.now()
        out_row  = pd.DataFrame(columns = out_col_names)
        
        # Get parcel input data
        print("Dates length:", len(dates))
        print("Index:", i)
        image_date = dates[i]
        geometry, parcel_desc = get_parcel_data_and_description(cadastral_ref, image_date)
        image_filepath = get_parcel_image(cadastral_ref, geometry, image_date)
        
        # Add data to input df
        new_row = pd.DataFrame([{
            'cadastral_ref': cadastral_ref,
            'parcel_desc': parcel_desc,  # Assuming 'en' for English description
            'sr_image_filepath': image_filepath
        }])

        input_df = pd.concat([input_df, new_row], ignore_index=True)
        print(f"[DEBUG]\tInput DataFrame updated ({len(input_df)} entries)")
        
        reset_dir(TEMP_DIR)
        
        exec_time = str(timedelta(seconds=(datetime.now() - init_time).total_seconds()))

        # Run LLM and parse reply
        raw_text = get_llm_response(image_filepath, parcel_desc).text.strip()

        # Split into lines and remove first line (e.g., ```json or BEGIN)
        lines = raw_text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        # Walk backward to find last closing brace
        end_idx = len(lines)
        for j in range(len(lines) - 1, -1, -1):
            if "}" in lines[j]:
                end_idx = j + 1
                break

        # Keep only JSON portion
        cleaned_text = "\n".join(lines[:end_idx]).replace("```", "").strip()

        # Sanity check
        if not cleaned_text or "{" not in cleaned_text:
            print("[WARNING] No valid JSON found in LLM response, skipping...")
            continue  # safely skip this iteration

        # Write to temp file
        output_path = BM_DIR / "temp_file.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)

        # --- Read it back safely ---
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to decode JSON: {e}")
            print("[DEBUG] Cleaned text preview:\n", cleaned_text[:300])
            continue  # skip broken JSONs

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
        output_path1 = BM_DIR / "temp_lol.tsv"
        json_df.to_csv(BM_DIR / "lol.tsv", sep="\t", index=False)

        out_row = pd.DataFrame([{
            'cadastral_ref': cadastral_ref,
            'parcel_area': json_df.get('Total_Parcel_Area_ha', [None])[0],
            'land_uses_amount': len(parcel_desc.split("Land")) - 1,
            'predicted_ecoschemes': json_df.get('Ecoscheme_ID', [None])[0],
            'predicted_base_aid': json_df.get('Final_Results.Total_Aid_without_Pluriannuality_EUR', [None])[0],
            'predicted_plur_aid': json_df.get('Final_Results.Total_Aid_with_Pluriannuality_EUR', [None])[0],
            'exec_time': exec_time,
        }])
        
        out_df = pd.concat([out_df, out_row], ignore_index=True)
        print(f"[DEBUG]\tOutput DataFrame updated ({len(out_df)} entries)")

        i+=1
        time_taken = (datetime.now() - init_time).total_seconds()
        time_taken_formatted = str(timedelta(seconds=time_taken))
        print(f"[DEBUG]\tTime taken for parcel processing {time_taken_formatted}")
        total_time += time_taken
        if i == 5: break
        else: continue
finally:
    total_time_formatted = str(timedelta(seconds=total_time))
    print(f"[DEBUG]\tBENCHMARK EXEC. TIME {total_time_formatted}")
    # Save dataframes
    input_filepath = BM_DIR / "input_data.tsv"
    out_filepath = BM_DIR / "output_data.tsv"
    input_df.to_csv(input_filepath, sep="\t", index=False)
    out_df.to_csv(out_filepath, sep="\t", index=False)
    print(f"[DEBUG]\tInput & output dataframes saved to:\n{input_filepath}\n{out_filepath}")

