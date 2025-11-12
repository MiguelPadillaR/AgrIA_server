import structlog

from PIL import Image
from google.genai.types import Content

from ..benchmark.vlm.ecoscheme_classif_algorithm import calculate_ecoscheme_payment_exclusive
from ..config.chat_config import CHAT as chat
from ..config.constants import FULL_DESC_TRIGGER, SHORT_DESC_TRIGGER, TEMP_DIR
from ..config.llm_client import client
from ..utils.chat_utils import generate_image_context_data, save_image_and_get_path

logger = structlog.getLogger()

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

def get_parcel_description(image_date, land_uses, query, image_filename, is_detailed_description, lang):
    """
    Handles the parcel information reading and description.
    Args:
        image_date (str): Date of the image.
        land_uses (list[dict]): List of land uses present in the state.
        query (list[dict]): List all parcels' detailed info. present in the state.
        image_filename (str): Name of the image file.
        is_detailed_description (bool): If True, generates a detailed description; otherwise, a short one.
        lang (str): Current interface language (`es`/ `en`).
    Returns:
        response (dict:{text:str, imagedesc:str}): Contains the text response and image description.
    """
    try:
        logger.info("Retrieveing parcel data...")
        image_context_data = generate_image_context_data(image_date, land_uses, query)
        json_data = calculate_ecoscheme_payment_exclusive(image_context_data[lang], lang)
        logger.debug(f"JSON DATA:\n{json_data}")
        # Insert image context prompt and read image desc file
        desc_trigger =  FULL_DESC_TRIGGER if is_detailed_description else SHORT_DESC_TRIGGER
        image_desc_prompt = desc_trigger+"\n"+image_context_data[lang]

        image_indication_options ={
            'es': "Estas son las características de la parcela cuya imagen te paso. Tenlo en cuenta para tu descripción en español. Comprueba el siguiente prompt para ver si es necesario cambiar el idioma:",
            'en': "These are the parcel's features whose image I am sending you. Take them into account for your description in English. Check next prompt for language change if needed:"
        }
        image_indication_prompt  = str(f"{desc_trigger}\n{image_indication_options[lang]}\n\n{json_data}")
        # Open image from path
        image_path = TEMP_DIR / str(image_filename).split("?")[0]
        image = Image.open(image_path)

        response = {
            "text": chat.send_message([image, image_indication_prompt],).text,
            "imageDesc":image_context_data
        }

        return response
    except Exception as e:
        print(f"Error while getting parcel description:\t{e}")
        raise

def get_suggestion_for_chat(chat_history: list[Content], lang: str):
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
        language = "Spanish" if lang == "es" else "English"
        suggestion_prompt = f"Using the summary as context, provide an appropiate 300-character max response in {language} to this chat output. You are acting as a user. Do not use any data not mentioned. Questions are heavily encouraged. Limit the use of expressions such as 'Genial','Excelente', etc..:\n\n"
        suggestion = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[suggestion_prompt, summarised_chat, last_chat_output]
        )
        return suggestion.text
    except Exception as e:
        print(f"Error getting suggestion:\t{e}")

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
        print(f"Error while summarising chat:\t{e}")

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