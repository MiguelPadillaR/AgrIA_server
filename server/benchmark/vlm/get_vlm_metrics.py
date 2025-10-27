# Setup VLM
import os
import pandas as pd

from datetime import datetime, timedelta
from PIL import Image
from google import genai
from google.genai import types
from sigpac_tools.find import find_from_cadastral_registry

from ...utils.parcel_finder_utils import reset_dir

from ...config.constants import SEN2SR_SR_DIR, TEMP_DIR
from ...services.sen2sr.constants import GEOJSON_FILEPATH


from .constants import BM_SR_IMAGES_DIR
from ...services.parcel_finder_service import download_sen2sr_parcel_image
from ..sr.utils import copy_file_to_dir
from ...utils.chat_utils import generate_image_context_data
from ...config.llm_client import client

from .llm_setup import generate_system_instructions
from .utils import n_random_dates_between



# Setup input dataframe
input_col_names =  ['cadastral_ref', 'parcel_desc', 'sr_image_filepath']
out_col_names =  ['cadastral_ref', 'parcel_area', 'applicable_ecoschemes', 'predicted_ecoschemes', 'applicable_aid','predicted_aid', 'ecoschemes_F1', 'aid_MAE', 'aid_MAPE', 'exec_time']
input_df  = pd.DataFrame(columns = input_col_names)
out_df  = pd.DataFrame(columns = out_col_names)

print("[DEBUG] DataFrames initialized")

# Get all cadastral references
cadastral_ref_list = ["26002A001000010000EQ", "26002A001000010000EQ"]  # TODO

# Get all parcel descriptions
to_date = datetime.today()
from_date = to_date - timedelta(days=4 * 365)
dates = n_random_dates_between(from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), len(cadastral_ref_list))

print(f"[DEBUG] Generated random dates: {dates}")

i = 0
for cadastral_ref in cadastral_ref_list:
    # Get parcel metadata and geometry
    geometry, metadata = find_from_cadastral_registry(cadastral_ref)
    os.makedirs(SEN2SR_SR_DIR, exist_ok=True)
    with open(GEOJSON_FILEPATH, "w") as file:
        file.write(str(geometry).replace("'", '"').replace("(","[").replace(")","]"))  # format GeoJSON correctly
    print(f"[DEBUG] Metadata keys: {list(metadata.keys())}")

    # Get parcel's description
    image_date = dates[i]
    land_uses = metadata.get('usos', None)
    query = metadata.get('query', None)
    parcel_metadata = generate_image_context_data(image_date, land_uses, query)
    parcel_desc = parcel_metadata['en']
    
    # Extract parcel area safely
    total_parcel_area = None
    if isinstance(parcel_metadata, dict) and 'TOTAL ELIGIBLE SURFACE (ha):' in parcel_metadata.get('en', ''):
        total_parcel_area = float(parcel_metadata['en'].split("TOTAL ELIGIBLE SURFACE (ha):")[-1])
    print(f"[DEBUG] Parcel area: {total_parcel_area}, Image date: {image_date}")

    # Get and save SR parcel image
    sr_image_filepath = os.path.join(TEMP_DIR, download_sen2sr_parcel_image(geometry, image_date))
    print(f"[DEBUG] SR image downloaded: {sr_image_filepath}")
    image_filepath = copy_file_to_dir(str(sr_image_filepath), BM_SR_IMAGES_DIR)
    
    # Rename file
    filepath_no_ext, ext = os.path.splitext(os.path.basename(sr_image_filepath))
    new_image_filepath = BM_SR_IMAGES_DIR / (filepath_no_ext + f"_{cadastral_ref}{ext}")
    os.rename(image_filepath, new_image_filepath)
    image_filepath = new_image_filepath
    print(f"[DEBUG] SR image copied to: {new_image_filepath}")
    
    # Save info to chat
    new_row = pd.DataFrame([{
        'cadastral_ref': cadastral_ref,
        'parcel_desc': parcel_desc,  # Assuming 'en' for English description
        'sr_image_filepath': image_filepath
    }])

    input_df = pd.concat([input_df, new_row], ignore_index=True)
    print(f"[DEBUG] Input DataFrame updated ({len(input_df)} entries)")
    
    reset_dir(SEN2SR_SR_DIR)
    
    # Run benchmark
    prompt = f"Describe the parcels based on the following information and image:\n\n{parcel_desc}"
    print(f"[DEBUG] Prompt generated: {prompt[:100]}...")

    image = Image.open(image_filepath)
    print(f"[DEBUG] Image loaded for inference")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=generate_system_instructions()
            ),
        contents=prompt
    )
    print(f"[DEBUG]AgrIA's response:\n---BEGIN\n{response.text}\n---END")
    
    # Get output dataframe

    i+=1
