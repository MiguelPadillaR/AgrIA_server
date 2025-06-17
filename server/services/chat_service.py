from pathlib import Path
from PIL import Image
import os
from google.genai.types import Content
from ..config.llm_client import client
from ..utils.llm_utils import load_prompt_from_json
from ..utils.chat_utils import save_image_and_get_path
from ..config.chat_init_config import CHAT as chat
from ..config.constants import PROMPT_LIST_FILE, TEMP_UPLOADS_PATH
from ..config.chat_init_config import CHAT as chat

def generate_user_response(user_input: str) -> str:
    response = chat.send_message(user_input,)
    return response.text

def get_image_description(file, is_detailed_description):
    """
    Handles the image upload and description generation.
    """
    filepath = save_image_and_get_path(file)
    filepath = filepath.replace("\\", "/")  # Ensure consistent path format
    image = Image.open(filepath)
    image_context_prompt = "FECHA: *Sin datos*\nCULTIVO: *Sin datos*"
    image_desc_prompt =  load_prompt_from_json(PROMPT_LIST_FILE, is_image_desc_prompt=True, is_detailed_description = is_detailed_description).replace("INSERT_DATE_AND_CROPS", image_context_prompt)
    response = chat.send_message([image, image_desc_prompt],)

    return response.text

def get_parcel_description(image_date, image_crops, image_filename, is_detailed_description):
    """
    Handles the parcel information reading and description.
    """
    # Build image context prompt
    image_context_prompt =f'FECHA DE IMAGEN: {image_date}\nCULTIVOS DETECTADOS: {len(image_crops)}'
    for crop in image_crops:
        image_context_prompt+= f'\nTipo: {crop["uso_sigpac"]}\nSuperficie (m2): {crop["dn_surface"]}'
    
    # Read image desc file and insert image context prompt
    image_desc_prompt =  load_prompt_from_json(PROMPT_LIST_FILE, is_image_desc_prompt=True, is_detailed_description = is_detailed_description).replace("INSERT_DATE_AND_CROPS", image_context_prompt)
    
    # Open image from path
    image_path = Path(os.path.join(TEMP_UPLOADS_PATH, image_filename))
    image = Image.open(image_path)

    response = {
        "text": chat.send_message([image, image_desc_prompt],).text,
        "imageDesc":image_context_prompt
    }

    return response

def get_suggestion_for_chat(chat_history: list[Content]):
    """
    Provides a suggested input for the model's last chat output.
    Args:
        last_chat_output (str): Model's last chat output.
    Returns:
        suggestion (str): Suggestion for the user to input.
    """
    last_message = chat_history[-1].parts[0].text
    summarised_chat = "### CHAT_SUMMARY_START ###\n" + get_summarised_chat(chat_history) + "\n### CHAT_SUMMARY_END ###"
    print(summarised_chat)
    last_chat_output = "### LAST_OUTPUT_START ###\n" + last_message + "\n### LAST_OUTPUT_END ###"
    suggestion_prompt = "Using the summarisation as context, provide an appropiate 300-character max response in Spanish to this chat output. You are acting as a user. Do not use any data not mentioned. Questions are heavily encouraged:\n\n"
    suggestion = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[suggestion_prompt, summarised_chat, last_chat_output]
    )
    print(suggestion.text)
    return suggestion.text

def get_summarised_chat(chat_history):
    """
    Provides a summary of the chat history.
    Args:
        chat_history (str): Chat history.
    Returns:
        summarised_chat.text (str): The summary of the history.
    """
    try:
        chat_message_history = []
        for el in chat_history:
            for part in el.parts:
                chat_message_history.append(part.text)
        print(chat_message_history)
        summarised_chat = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                "Summarise this chat history in 100 words aprox:",
                chat_message_history
            ]
        )
        return summarised_chat.text
    except Exception as e:
        print(e)


