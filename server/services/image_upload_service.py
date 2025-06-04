from PIL import Image
from ..utils.llm_utils import load_prompt_from_json
from ..utils.image_utils import save_image_and_get_path
from ..config.chat_init_config import CHAT as chat
from ..config.constants import PROMPT_LIST_FILE

def get_image_description(file):
    """
    Handles the image upload and description generation.
    """
    filepath = save_image_and_get_path(file)
    filepath = filepath.replace("\\", "/")  # Ensure consistent path format
    image = Image.open(filepath)
    response = chat.send_message([image, load_prompt_from_json(PROMPT_LIST_FILE, is_image_desc_prompt=True)],)

    return response.text