from ..config.constants import BASE_CONTEXT_PATH, BASE_PROMPTS_PATH
from server.services.llm_services import upload_context_document
from google.genai import types
import json
import os

def generate_system_instructions(documents_json_path: str, role_json_path: str):
    """
    Sets up the initial model's system instructions and context documents for the chat.
    
    Args:
        documents_json_path (str): JSO filepath containing paths to the actual context documents.
        role_json_path (str): JSON filepath containing paths to the actual text file with the role prompt.
    
    Returns:
        list: A list containing the system instruction and context documents info as dictionaries.
    """
    # Upload files and read role file
    role_instructions = load_prompt_from_json(role_json_path)
    context_documents = load_documents_from_json(documents_json_path)
    documents_uris =[]

    for doc in context_documents:
        if doc:
            # Upload the document and get its relative path
            uploaded_doc = upload_context_document(doc)
            if uploaded_doc:
                documents_uris.append(uploaded_doc.uri)
            else:
                print(f"Failed to upload document: {doc}")
        else:
            print("No document content found.")

    # Compose system insrtuctions from files' URI and role text data
    documents_instructions = "\n\nUse these files as your context documents for the task:"
    system_instructions = role_instructions + documents_instructions + str(documents_uris)

    return system_instructions


def load_prompt_from_json(json_path: str, base_path: str = BASE_PROMPTS_PATH, is_image_desc_prompt: bool = False, is_detailed_description: bool = True) -> dict:
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