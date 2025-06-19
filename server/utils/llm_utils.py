from ..config.constants import BASE_CONTEXT_PATH, BASE_PROMPTS_PATH, FULL_DESC_TRIGGER, SHORT_DESC_TRIGGER
from server.services.llm_services import upload_context_document
from google import genai
import json
import os

def generate_system_instructions(documents_json_path: str, prompt_json_path: str):
    """
    Sets up the initial model's system instructions and context documents for the chat.
    
    Args:
        documents_json_path (str): JSON filepath containing paths to the actual context documents.
        role_json_path (str): JSON filepath containing paths to the actual text file with the role prompt.
    
    Returns:
        list: A list containing the system instruction and context documents info as dictionaries.
    """
    # Upload files and read role and description files
    role_prompt = load_prompt_from_json(prompt_json_path)
    short_description_prompt = load_prompt_from_json(prompt_json_path,is_image_desc_prompt= True, is_detailed_description=False)
    full_description_prompt = load_prompt_from_json(prompt_json_path, is_image_desc_prompt= True, is_detailed_description=True)
    context_documents = load_documents_from_json(documents_json_path)
    documents_uris =[]

    for doc in context_documents:
        if doc:
            # Upload the document and get its relative uploaded path
            uploaded_doc = upload_context_document(doc)
            if uploaded_doc:
                documents_uris.append(uploaded_doc.uri)
            else:
                print(f"Failed to upload document: {doc}")
        else:
            print("No document content found.")

    # Compose system insrtuctions from files' URI and role text data
    documents_instructions = "\n\nUse these files as your context documents for the task. You may display the tables in the document to the user and quote or make a reference to any information taken directly from the text from the text:"
    short_description_instruction = "\n\nThis is the description instructions, format and example for the short image description. You will use these to describe it whenever you are prompted with an image and the tokens '" + SHORT_DESC_TRIGGER +"' and date and crop info:\n\n" + short_description_prompt
    long_description_instruction = "\n\nThis is the description instructions, format and example for the long image description. You will use these to describe it whenever you are prompted with an image and the tokens '" + FULL_DESC_TRIGGER +"' and date and crop info:\n\n" + full_description_prompt

    system_instructions = role_prompt + documents_instructions + str(documents_uris) + short_description_instruction + long_description_instruction

    return system_instructions

def load_prompt_from_json(json_path: str, base_path: str = BASE_PROMPTS_PATH, is_image_desc_prompt: bool = False, is_detailed_description: bool = False) -> dict:
    """
    Reads a JSON file to get the prompt description and returns the content of the specified prompt file.
    Args:
        json_path (str): Path to the JSON file containing prompt metadata.
        base_path (str): Base path where the JSON and prompt files are located.
        is_image_desc_prompt (bool): If True, retrieves reads filea as the image description prompt; otherwise, reads it as role prompt.
        get_short_description (bool): If True, retrieves the short description; otherwise, retrieves the long description.
    Returns:
        str: The content of the prompt file specified in the JSON.
    """
    full_json_path = os.path.join(base_path, json_path).replace("\\", "/")

    # Read JSON content
    with open(full_json_path, 'r', encoding='utf-8') as json_file:
        meta = json.load(json_file)
    if is_image_desc_prompt:
        prompt_type = 'short' if not is_detailed_description else 'long'
    else:
        prompt_type = 'role'

    print("PROMPT TYPE: ", prompt_type.capitalize())

    prompt_data = meta.get(prompt_type)
    content = get_description_prompt(base_path, prompt_data, is_image_desc_prompt)
    meta['content'] = content

    return content

def get_description_prompt(base_path, prompt_data, is_image_desc_prompt):
    """
    Get the full description prompt from both the instructions and example files.
    Args:
        base_path (str): Base path where all prompt related files are located.
        prompt_data (str): The type of description the prompt is (`long`, `short`, or `role`).
        is_image_desc_prompt (bool): Whether the prompt is for image description or not.
    Returns:
        content (str): The full constructed description prompt to pass to the LLM.
    """
    desc_filename = prompt_data["prompt_filepath"]
    prompt_path = os.path.join(base_path, desc_filename).replace("\\", "/")

    with open(prompt_path, 'r', encoding='utf-8') as pf:
        content = pf.read()

    if is_image_desc_prompt:
        prompt_example_path = os.path.join(base_path, prompt_data["example"]).replace("\\", "/")
        with open(prompt_example_path, 'r', encoding='utf-8') as ef:
            content += "\n" + ef.read()

    return content

def load_documents_from_json(json_path: str, base_path: str = BASE_CONTEXT_PATH) -> list:
    """
    Reads a JSON file to get the document metadata and returns a list of document contents.
    
    Args:
        json_path (str): Path to the JSON file containing document metadata.
        base_path (str): Base path where the JSON and document files are located.
    
    Returns:
        list: A list of document contents.
    """
    full_json_path = os.path.join(base_path, json_path).replace("\\", "/")

    # Read JSON and get documents
    with open(full_json_path, 'r', encoding='utf-8') as json_file:
        meta = json.load(json_file)
    # Retrieve documents' paths from metadata
    documents = []
    for doc in meta.get('context_document_links', []):
        doc_filepath = os.path.join(base_path, doc['path']).replace("\\", "/")
        documents.append(doc_filepath)
    return documents

def set_initial_messages():
    user_input = '*Presentación de AgrIA*'
    model_output = '¡Hola!\n\nSoy tu Asistente de Imágenes Agrícolas, ¡pero puedes llamarme **AgrIA**!\n\nMi propósito aquí es **analizar imágenes satelitales de campos de cultivo** para asistir a los agricultores en en análisis del su **uso del espacio y los recursos, así como las prácticas agrícolas**, con el fin de **asesorarles a reunir los requisitos para las subvenciones del Comité Europeo de Política Agrícola Común (CAP)**.\n\n¡Sólo tienes que subir una imagen satelital de tus campos de cultivo y nos pondremos manos a la obra!\n\nSi tiene alguna pregunta, también puede escribir en el cuadro de texto'
    user_content = genai.types.Content(
        role='user',
        parts=[
            genai.types.Part(text=user_input)
        ]
    )

    model_content = genai.types.Content(
        role='model',
        parts=[
            genai.types.Part(text=model_output)
        ]
    )
    return [user_content, model_content]
