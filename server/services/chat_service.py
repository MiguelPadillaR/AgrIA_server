from pathlib import Path
import os
from PIL import Image
from ..utils.llm_utils import load_prompt_from_json
from ..utils.chat_utils import save_image_and_get_path
from ..config.chat_init_config import CHAT as chat
from ..config.constants import PROMPT_LIST_FILE, TEMP_UPLOADS_PATH
from ..config.chat_init_config import CHAT as chat

def generate_user_response(user_input: str) -> str:
    response = chat.send_message(user_input,)
    return response.text

def get_image_description(file):
    """
    Handles the image upload and description generation.
    """
    filepath = save_image_and_get_path(file)
    filepath = filepath.replace("\\", "/")  # Ensure consistent path format
    image = Image.open(filepath)
    image_context_prompt = "FECHA: *Sin datos*\nCULTIVO: *Sin datos*"
    image_desc_prompt =  load_prompt_from_json(PROMPT_LIST_FILE, is_image_desc_prompt=True).replace("INSERT_DATE_AND_CROPS", image_context_prompt)
    response = chat.send_message([image, image_desc_prompt],)

    return response.text

def get_parcel_description(image_date, image_crops, image_filename):
    """
    Handles the parcel information reading and description.
    """
    # Build image context prompt
    image_context_prompt =f'FECHA DE IMAGEN: {image_date}\nCULTIVOS DETECTADOS: {len(image_crops)}'
    for crop in image_crops:
        image_context_prompt+= f'\nTipo: {crop["uso_sigpac"]}\nSuperficie (m2): {crop["dn_surface"]}'
    
    # Read image desc file and insert image context prompt
    image_desc_prompt =  load_prompt_from_json(PROMPT_LIST_FILE, is_image_desc_prompt=True).replace("INSERT_DATE_AND_CROPS", image_context_prompt)
    
    # Open image from path
    image_path = Path(os.path.join(TEMP_UPLOADS_PATH, image_filename))
    image = Image.open(image_path)

    response = {
        "text": chat.send_message([image, image_desc_prompt],).text,
        "imageDesc":image_context_prompt
    }

    return response


