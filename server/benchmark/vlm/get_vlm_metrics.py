# Setup VLM
from collections import defaultdict
import json
import os
import pandas as pd
import structlog

from datetime import datetime, timedelta
from PIL import Image
from google import genai
from google.genai import types

from ..sr.utils import copy_file_to_dir
from ...config.constants import SEN2SR_SR_DIR, TEMP_DIR
from ...config.llm_client import client
from ...services.parcel_finder_service import download_sen2sr_parcel_image
from ...services.sen2sr.constants import GEOJSON_FILEPATH
from ...services.sigpac_tools_v2.find import find_from_cadastral_registry
from ...utils.chat_utils import generate_image_context_data
from ...utils.parcel_finder_utils import reset_dir


from .constants import BM_JSON_DIR, BM_LLM_DIR, BM_SR_IMAGES_DIR, CADASTRAL_REF_LIST_PAPER, DATES_PAPER, FULL_DESC_SYS_INSTR_EN, FULL_DESC_SYS_INSTR_ES, USE_PAPER_DATA, LANG, OG_CLASSIFICATION_FILEPATH
from .ecoscheme_classif_algorithm import calculate_ecoscheme_payment_exclusive
from .llm_setup import generate_system_instructions
from .utils import n_random_dates_between

logger = structlog.get_logger()

def init():
    # init dirs
    os.makedirs(BM_LLM_DIR, exist_ok=True)
    os.makedirs(BM_JSON_DIR, exist_ok=True)
    os.makedirs(BM_SR_IMAGES_DIR, exist_ok=True)

    # Setup input dataframe
    input_col_names =  ['cadastral_ref', 'image_date', 'parcel_desc', 'sr_image_filepath']
    out_col_names =  ['cadastral_ref', 'parcel_area', 'land_uses_amount', 'applicable_ecoschemes', 'predicted_ecoschemes', 'applicable_base_aid','predicted_base_aid', 'applicable_plur_aid','predicted_plur_aid', 'ecoschemes_F1', 'base_aid_diff', 'plur_aid_diff', 'base_aid_MAE', 'plur_aid_MAE', 'plur_aid_MAPE', 'base_aid_MAPE', 'exec_time']
    input_df  = pd.DataFrame(columns = input_col_names)
    out_df  = pd.DataFrame(columns = out_col_names)

    logger.debug(f"DataFrames initialized")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return input_df, out_df, timestamp

def setup_ndates(n_dates:int, to_date: datetime=datetime.today(), delta_days: int=4 * 365):
    # Get all parcel descriptions
    from_date = to_date - timedelta(days=delta_days)
    dates = n_random_dates_between(from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d"), n_dates)
    logger.debug(f"Generated random dates: {dates}")
    
    return dates

def get_parcel_data_and_description(cadastral_ref: str, image_date: str, lang: str=LANG):
    if not lang:
        lang = LANG
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
    parcel_desc = parcel_metadata[lang]
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

def get_llm_full_desc(image_filepath: str, parcel_desc: str, lang: str=LANG, classification_filepath: str=OG_CLASSIFICATION_FILEPATH, is_vlm_only: bool=False):
    if not lang:
        lang = LANG

    json_data = calculate_ecoscheme_payment_exclusive(parcel_desc, lang)
    
    prompt_en = f"Produce a full English parcel description with the following information. Combine it with the image for a 700-character max description:\n\n{json_data}"
    desc_en = "The satellite image displays a **31.18-hectare** agricultural parcel dominated by **dry, reddish-brown tones**, indicative of **low vegetation cover** or recently worked soil, typical of Mediterranean woody crops or extensive grazing lands. This visual assessment directly correlates with the digital land use analysis. The largest area, **Olive Groves (OV)**, accounts for **30.72 ha** and has been assigned to the Eco-scheme **P6/P7 (Plant Cover)**, based on the highest payment/ha. A smaller portion of **Shrub Pastures (PR)**, **0.36 ha**, is assigned to **P1 (Extensive Grazing)**.The overall low vegetation signal in the image is consistent with the extensive farming practices suggested by the two applicable Eco-schemes, particularly the large area of OV allocated to the P6/P7 scheme using the Tier 2 rate."
    prompt_en += f'\n\nThis is an example of the 700-char max parcel descriptiom:\n"{desc_en}"'
    prompt_es = f"Genera una descripción completa de la parcela en Español con la siguiente información. Combínala con la imagen para la descripción de 700 caracteres máximo:\n\n{json_data}"
    desc_es = "La imagen satélite muestra una parcela agrícola de **31.18 ha**, dominada por **tonos rojizos, marrones y secos**, indicativo de **poca cobertura vegetal** o terreno trabajado recientemente, típico de cultivos leñosos mediterráneos o de tierras de pastoreo extensivo. La evaluación visual se correlaciona direcatmente con el análisi digital del uso de la tierra. El área más grande, **Olivares (OV)**, abarca **30.72 ha** y ha sido asignaco al Ecorrégimen **P6/P7 (Cobertura Vegetal)**, debido a tener el importe pago/ha más alto. Un pequeña porción de **Pasto Arbustivo (PA)**, **0.36 ha**, ha sido asignada a **P1 (Pastoreo Extensivo)**. La baja señal de vegetación en general en la imagen is consistente con las prácticas agrícolas extensivas sugeridas en estos dos Ecorregímenes aplicables, particularmente, el área más grande de OV que se ha asignado a P6/P7 usando importes del Tramo 2."
    prompt_es += f'\n\Este es un ejemplo de la la descripción de 700 caracteres máximo:\n"{desc_es}"'
    prompt = f"Describe the parcels based on the following information and image:\n\n{parcel_desc}"

    prompt = prompt_en if lang == "en" else prompt_es if lang == "es" else prompt
    logger.debug(f'Prompt generated:\n"{prompt[:150]}..."')

    image = Image.open(image_filepath)
    logger.debug(f"Image loaded for inference")

    sys_ins = (
        FULL_DESC_SYS_INSTR_EN if lang == "en"
        else FULL_DESC_SYS_INSTR_ES if lang == "es"
        else generate_system_instructions()
    )

    # logger.debug(f"LLM instructions: {sys_ins}")

    llm_response = client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=sys_ins
            ),
        contents=[image, prompt]
    )
    logger.debug(f"AgrIA's response:\n---BEGIN\n{llm_response.text}\n---END")

    return llm_response, json_data

def extract_json_from_reply(raw_text: str, cadastral_ref: str):
    # Split into lines and remove first line (e.g., ```json or BEGIN)
    lines = raw_text.splitlines()
    
    # Find opening and closing JSON braces
    i, j = 0, len(lines) - 1
    start_idx = end_idx = None
    found = False
    while j > 0 and not found:
        start_idx = i if "{" == lines[i] else start_idx
        end_idx = j + 1 if "}" == lines[j] else end_idx
        found = start_idx is not None  and end_idx is not None
        i += 1
        j -= 1
    logger.debug(f"JSON found between lines {start_idx} and {end_idx}.")

    # Keep only JSON portion
    cleaned_text = "\n".join(lines[start_idx:end_idx]).replace("```", "").strip()

    # Sanity check
    if not cleaned_text or "{" not in cleaned_text:
        logger.warning("No valid JSON found in LLM response, skipping...")

    # Save ecoschemes JSON classification
    output_path = BM_LLM_DIR / f"{cadastral_ref}_out.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    # --- Read it back safely ---
    data = ''
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR] Failed to decode JSON: {e}")
        logger.debug("[DEBUG] Cleaned text preview:\n", cleaned_text[:300])
    logger.debug(f"Data from JSON file:\n{data}")

    # --- Normalize JSON into dataframe ---
    json_df = pd.json_normalize(
        data,
        sep=".",
        errors="ignore"
    )
    return json_df

def run_vlm_benchmark(use_vlm_only: bool=False, lang: str=LANG, use_paper_data: bool=USE_PAPER_DATA):
    input_df, out_df, timestamp = init()
    try:
        i = 0
        total_time = 0
        reset_dir(BM_SR_IMAGES_DIR)
        reset_dir(BM_LLM_DIR)

        # Get all cadastral references and date data
        cadastral_ref_list = CADASTRAL_REF_LIST_PAPER if use_paper_data else ["26002A001000010000EQ", "14048A001001990000RM","45054A067000090000QA", "43157A024000010000KE", "34039A005000020000YQ", "27020A319000010000QL", "43022A037000430000JO", "50074A045000370000KA", "50074A014000730000KS", "25015A501101860000RF", "25142A002000430000BP", "22121A007001610000UD", "22145A011000110000PI", "22061A018000530000GG", "26002A004009350000EI", "41079A057000020000JR", "41012A018000030000TX", "23086A02500051FA", "23060A065002370000EX", "29055A040000040000HL", "41062A012001000000UQ", "41062A012000960000UB", ""]  # TODO
        dates = DATES_PAPER if use_paper_data else setup_ndates(len(cadastral_ref_list))
    
        for cadastral_ref in cadastral_ref_list:
            if len(cadastral_ref) != 20:
                continue
            init_time = datetime.now()
        
        # Get parcel input data
            image_date = dates[i]
            geometry, parcel_desc = get_parcel_data_and_description(cadastral_ref, image_date, lang)
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
            raw_text, json_data = get_llm_full_desc(image_filepath, parcel_desc, lang)
        # Save full desc to file
            full_desc_filepath = BM_LLM_DIR / f"{cadastral_ref}_full_desc_{lang}.md"
            if json_data:
                with open(full_desc_filepath, "w") as f: 
                    f.write(raw_text.text.strip())
            output_path = BM_LLM_DIR / f"{cadastral_ref}_out.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=4)
            exec_time = str(timedelta(seconds=(datetime.now() - init_time).total_seconds()))
        # Parse LLM reply
            json_df = extract_json_from_reply(raw_text.text.strip(), cadastral_ref) if not json_data else json_data
            if json_data:
                es_list = sorted({
                item["Ecoscheme_ID"]
                for item in json_df["Estimated_Total_Payment"]
                if item.get("Ecoscheme_ID") and item["Ecoscheme_ID"] != "N/A"
            })
                parcel_area = json_df.get('Total_Parcel_Area_ha', [None])
                predicted_base_aid = json_df.get('Final_Results').get('Total_Aid_without_Pluriannuality_EUR', [None])
                predicted_plur_aid = json_df.get('Final_Results').get('Total_Aid_with_Pluriannuality_EUR', [None]),
            else:
                es_list =sorted([
                item["Ecoscheme_ID"]
                for sublist in json_df["Estimated_Total_Payment"]
                for item in sublist
                if isinstance(item, dict) and "Ecoscheme_ID" in item
            ])
                parcel_area = json_df.get('Total_Parcel_Area_ha', [None])[0]
                predicted_base_aid = json_df.get('Final_Results.Total_Aid_without_Pluriannuality_EUR', [None])[0]
                predicted_plur_aid = float(json_df.get('Final_Results.Total_Aid_with_Pluriannuality_EUR', [None])[0]),
        
            predicted_plur_aid = predicted_plur_aid[0]

        # es_list = str(es_list).replace("'", "").replace('"', "").replace("[", "").replace("]", "") if IS_PAPER_DATA else es_list
            out_row = pd.DataFrame([{
            'cadastral_ref': cadastral_ref,
            'parcel_area': parcel_area,
            'land_uses_amount': len(parcel_desc.split("Land")) - 1,
            'predicted_ecoschemes': es_list,
            'predicted_base_aid': predicted_base_aid,
            'predicted_plur_aid': predicted_plur_aid,
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
        lang = lang.upper()
        prefix = "PAPER_" if use_paper_data else ""
        prefix += f"VLM_{lang}_" if use_vlm_only else f"ALG_{lang}_"
        input_filepath = BM_JSON_DIR / f"{prefix}{timestamp}_in.tsv"
        out_filepath = BM_JSON_DIR / f"{prefix}{timestamp}_out.tsv"
        input_df.to_csv(input_filepath, sep="\t", index=False)
        out_df.to_csv(out_filepath, sep="\t", index=False)
        logger.debug(f"Input & output dataframes saved to:\n{input_filepath}\n{out_filepath}")
        logger.info(f"PARAMS. PERMUTATION:\t{prefix[:-1]}")

# Example usage
def demo():
    try:
        times = defaultdict(lambda: defaultdict(dict))
        for lang in ["en", "es"]:
            for flag in [True, False]:
                id= "vlm" if flag else "hybrid"
                init_time = datetime.now()
                time_taken = (datetime.now() - init_time).total_seconds()

                run_vlm_benchmark(flag, lang)

                total_time_formatted = str(timedelta(seconds=time_taken))
                logger.debug(f"BENCHMARK EXEC. TIME {total_time_formatted}")
                
                times[id][lang]["time"] = total_time_formatted

        run_vlm_benchmark(use_paper_data=True)
    
    except Exception as e:
        logger.exception(f"Error during VLM metrics collection:\nEXCEPTION:\t{e}")
    finally:
        logger.info(f"TIMES:\n{dict(times)}")
        times_filepath = BM_JSON_DIR / "times.json"
        with open(times_filepath, 'w') as f:
            json.depath = BM_JSON_DIR / "times1.json"
        with open(times_filepath, 'w') as f:
            f.write(str(times))

# demo()