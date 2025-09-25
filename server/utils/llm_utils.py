from ..config.constants import BASE_CONTEXT_PATH, BASE_PROMPTS_PATH, FULL_DESC_TRIGGER, MIME_TYPES, SHORT_DESC_TRIGGER
from server.services.llm_services import upload_context_document
from google.genai.types import Content, Part
import json
import os

def generate_system_instructions(prompt_json_path: str):
    """
    Sets up the initial model's system instructions and context documents for the chat.
    
    Args:
        prompt_json_path (str): JSON filepath containing paths to the actual prompts.
    
    Returns:
        system_instructions (str): All system instructions for AgrIA as raw text.
    """
    # Upload files and read role and description files
    role_prompt = load_prompt_from_json(prompt_json_path)
    short_description_prompt = load_prompt_from_json(prompt_json_path,is_image_desc_prompt= True, is_detailed_description=False)
    full_description_prompt = load_prompt_from_json(prompt_json_path, is_image_desc_prompt= True, is_detailed_description=True)

    # Compose system insrtuctions from files' URI and role text data
    short_description_instruction = "\n\nThis is the description instructions, format and example for the short image description. You will use these to describe it whenever you are prompted with an image and the tokens '" + SHORT_DESC_TRIGGER +"' and date and crop info:\n\n" + short_description_prompt
    long_description_instruction = "\n\nThis is the description instructions, format and example for the long image description. You will use these to describe it whenever you are prompted with an image and the tokens '" + FULL_DESC_TRIGGER +"' and date and crop info:\n\n" + full_description_prompt

    system_instructions = role_prompt + short_description_instruction + long_description_instruction

    return system_instructions

def load_prompt_from_json(json_path: str, base_path: str = BASE_PROMPTS_PATH, is_image_desc_prompt: bool = False, is_detailed_description: bool = False) -> dict:
    """
    Reads a JSON file to get the prompt description and returns the content of the specified prompt file.
    Args:
        json_path (str): Path to the JSON file containing prompt metadata.
        base_path (str): Base path where the JSON and prompt files are located. Default: `BASE_PROMPTS_PATH`.
        is_image_desc_prompt (bool): If True, reads files as the image description prompt; otherwise, it reads them as role prompts. Default: `False`.
        is_detailed_description (bool): If True, sends trigger for long description, other wise sends short desc. trigger. Default: `False`.
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
        prompt_example_dir = os.path.join(base_path, prompt_data["examples"]).replace("\\", "/")
        for prompt_example_path in os.listdir(prompt_example_dir):
            prompt_example_path = os.path.join(prompt_example_dir, prompt_example_path)
            with open(prompt_example_path, 'r', encoding='utf-8') as f:
                content += "\n" + f.read()

    return content

def load_documents_from_json(json_path: str, base_path: str = BASE_CONTEXT_PATH) -> list:
    """
    Reads a JSON file to get the document metadata and returns a list of document contents.
    
    Args:
        json_path (`str`): Path to the JSON file containing document metadata.
        base_path (`str`): Base path where the JSON and document files are located. Default: `BASE_CONTEXT_PATH`.
    
    Returns:
        documents (list of `str`): A list of document contents.
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

def set_initial_history(documents_json_path: str):
    """
    Constructs the initial history for a chat session, including context documents.

    Args:
        documents_json_path: The path to the JSON file containing paths to context documents.

    Returns:
        A list representing the conversation history, ready to be used with a chat instance.
    """
    initial_history = []
    document_parts = []
    upload_success = 0

    try:
        doc_paths_list = load_documents_from_json(documents_json_path)
    except FileNotFoundError:
        print(f"Error: Document JSON file not found at {documents_json_path}")
        doc_paths_list = []
    except Exception as e:
        print(f"Error loading documents from JSON: {e}")
        doc_paths_list = []

    if doc_paths_list:
        document_parts.append(Part(text="Use the following files as context documents for the task. You may display tables and quote or reference information directly from the documents:"))

        for doc_path in doc_paths_list:
            if not doc_path:
                continue

            file_extension = doc_path.split('.')[-1].lower()
            mime_type = MIME_TYPES.get(file_extension, 'application/octet-stream')

            try:
                uploaded_doc = upload_context_document(doc_path)
                if uploaded_doc and uploaded_doc.uri:
                    print(f"Successfully uploaded document. URI: {uploaded_doc.uri}")
                    document_parts.append(Part(text=f"Document: {os.path.basename(doc_path)}"))
                    # Add the document URI part
                    document_parts.append(Part.from_uri(file_uri=uploaded_doc.uri, mime_type=mime_type))
                    upload_success += 1
                else:
                    print(f"Warning: Failed to get URI for uploaded document: {doc_path}")
            except Exception as e:
                print(f"Error uploading document {doc_path}: {e}")
        
        llm_answer = "Apologies, it appears there has been an error during the document upload process and I have not got access to the files. I will do my best to answer any queries though."
        if upload_success > 0:
            print(f"Successfully uploaded and prepared {upload_success} documents for context.")
            # Append all document parts as a single 'user' turn
            initial_history.append(Content(role='user', parts=document_parts))
            # Model's optional "OK" response to the context
            llm_answer = "Okay, I have received the context documents and I will use them for our conversation."
        else:
            print("No documents were successfully uploaded to include in the initial history.")

        initial_history.append(Content(role='model', parts=[Part(text=llm_answer)]))

    user_input_intro = 'Recuerda que debes hablar en el mismo idioma que el usuario, ya esa español, inglés u otro. Ahora preséntate.'
    model_output_intro = (
        '¡Hola!\n\nSoy tu Asistente de Imágenes Agrícolas, ¡pero puedes llamarme **AgrIA**!\n\n'
        'Mi propósito aquí es **analizar imágenes satelitales de campos de cultivo** para '
        'asistir a los agricultores en el análisis del su **uso del espacio y los recursos, '
        'así como las prácticas agrícolas**, con el fin de **asesorarles a reunir los requisitos '
        'para las subvenciones del Comité Europeo de Política Agrícola Común (CAP)**.\n\n'
        '¡Sólo tienes que subir una imagen satelital de tus campos de cultivo y nos pondremos manos a la obra!\n\n'
        'Si tiene alguna pregunta, también puede escribir en el cuadro de texto.'
    )

    initial_history.append(Content(role='user', parts=[Part(text=user_input_intro)]))
    initial_history.append(Content(role='model', parts=[Part(text=model_output_intro)]))

    print(f"Initial history prepared with {len(initial_history)} turns.")
    return initial_history