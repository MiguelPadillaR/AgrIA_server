from PIL import Image
from ..utils.llm_utils import load_prompt_from_json
from ..utils.image_utils import save_image_and_get_path
from ..config import chat, image_description_prompt_file
import os
def get_image_description(file):
    """
    Handles the image upload and description generation.
    """
    filepath = save_image_and_get_path(file)
    filepath = filepath.replace("\\", "/")  # Ensure consistent path format
    image = Image.open(filepath)
    response = chat.send_message([image, load_prompt_from_json(image_description_prompt_file)],)

    return response.text