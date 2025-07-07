from pathlib import Path
from PIL import Image
import os
from google.genai.types import Content
from ..config.llm_client import client
from ..utils.chat_utils import save_image_and_get_path
from ..config.constants import FULL_DESC_TRIGGER, SHORT_DESC_TRIGGER, TEMP_UPLOADS_PATH
from ..config.chat_config import CHAT as chat

def generate_user_response(user_input: str) -> str:
    """
    Sends user input to chat and retrieves output.
    Args:
        user_input (str): User input fron frontend.
    Returns:
        response.text (str): Response from model.
    """
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
    image_desc_prompt =  FULL_DESC_TRIGGER +"\n" if is_detailed_description else SHORT_DESC_TRIGGER
    image_desc_prompt += image_context_prompt

    response = chat.send_message([image, image_desc_prompt],)

    return response.text

def get_parcel_description(image_date, image_crops, image_filename, is_detailed_description):
    """
    Handles the parcel information reading and description.
    Args:
        image_date (str): Date of the image.
        image_crops (list[dict]): List of crops detected in the image.
        image_filename (str): Name of the image file.
        is_detailed_description (bool): If True, generates a detailed description; otherwise, a short one.
    Returns:
        response (dict:{text:str, imagedesc:str}): Contains the text response and image description.
    """
    try:
        # Build image context prompt
        image_context_data =f'FECHA DE IMAGEN: {image_date}\nPARCELAS DETECTADAS: {len(image_crops)}\n'
        total_surface = 0.0
        for crop in image_crops:
            parcel_id = crop["recinto"]
            type = crop["uso_sigpac"]
            surface = round(float(crop["superficie_admisible"] or crop["dn_surface"]),3)
            irrigation = crop["coef_regadio"] if int(crop["coef_regadio"]) > 0 else None
            total_surface += surface
            image_context_data+= f'\n- Recinto: {parcel_id}\n- Tipo: {type}\n- Superficie admisible (m2): {surface}\n'
            if irrigation:  image_context_data+=f'Coef. regadío: {irrigation}%\n'

        # Insert image context prompt and read image desc file
        image_context_data += f'\nSUPERFICIE ADMISIBLE TOTAL (m2): {round(total_surface,3)}'
        image_desc_prompt =  FULL_DESC_TRIGGER if is_detailed_description else SHORT_DESC_TRIGGER
        image_desc_prompt += image_context_data
        
        # Open image from path
        image_path = Path(os.path.join(TEMP_UPLOADS_PATH, image_filename))
        image = Image.open(image_path)

        response = {
            "text": chat.send_message([image, "Estas son las características de la parcela cuya imagen te paso. Tenlo en cuenta para tu descripción:\n\n" + image_desc_prompt],).text,
            "imageDesc":image_context_data
        }

        return response
    except Exception as e:
        print(e)
        return ''

def get_suggestion_for_chat(chat_history: list[Content]):
    """
    Provides a suggested input for the model's last chat output.
    Args:
        last_chat_output (str): Model's last chat output.
    Returns:
        suggestion (str): Suggestion for the user to input.
    """
    try:
        last_user_content_entry = chat_history[-1]
        last_message = ""
        for part in last_user_content_entry.parts:
            if part.text is not None:
                last_message = part.text
                break
        summarised_chat = "### CHAT_SUMMARY_START ###\n" + get_summarised_chat(chat_history) + "\n### CHAT_SUMMARY_END ###"
        last_chat_output = "### LAST_OUTPUT_START ###\n" + str(last_message) + "### LAST_OUTPUT_END ###"
        suggestion_prompt = "Using the summary as context, provide an appropiate 300-character max response in Spanish to this chat output. You are acting as a user. Do not use any data not mentioned. Questions are heavily encouraged. Limit the use of expressions such as 'Genial','Excelente', etc..:\n\n"
        suggestion = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[suggestion_prompt, summarised_chat, last_chat_output]
        )
        return suggestion.text
    except Exception as e:
        print("Error getting suggestion:\t", e)
        return ''

def get_summarised_chat(chat_history):
    """
    Provides a summary of the chat history.
    Args:
        chat_history (list[genai.types.Content]): Chat history.
    Returns:
        summarised_chat.text (str): The summary of the history.
    """
    try:
        chat_message_history = get_role_and_content(chat_history)
        summarised_chat = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                "Summarise this chat history in 100 words aprox. If too long, make emphasis on the last 5 items of the chat:",
                str(chat_message_history)
            ]
        )
        return summarised_chat.text
    except Exception as e:
        print("Error while summarising chat:\t",e)

def get_role_and_content(chat_history):
    """
    Extracts role and text content of chat history.
    Args:
        chat_history (list[genai.types.Content]): Chat history.
    Returns:
        chat_message_history (list[dict:{role:str, content:str}]): Chat history formatted.
    """
    # Get only role and text content from chat_history
    chat_message_history = []
    for content in chat_history:
        role = content.role if content.role is not None else "unknown"
        for part in content.parts:
            if part.text is not None:
                chat_message_history.append({"role": role, "content": part.text})
    return chat_message_history