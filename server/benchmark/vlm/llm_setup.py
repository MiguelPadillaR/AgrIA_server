from ...utils.llm_utils import load_prompt_from_json
from ...config.constants import PROMPT_LIST_FILE, CALCULATIONS_RULE, EXCLUSIVITY_RULE
from .constants import BM_DIR, BM_PROMPT_LIST_FILE


def generate_system_instructions(prompt_json_path: str=BM_PROMPT_LIST_FILE):
    """
    Sets up the initial model's system instructions and context documents for the chat.
    
    Args:
        prompt_json_path (str): JSON filepath containing paths to the actual prompts.
    
    Returns:
        system_instructions (str): All system instructions for AgrIA as raw text.
    """
    # Upload files and read role and description files
    role_prompt = load_prompt_from_json(PROMPT_LIST_FILE)
    classification_data = load_prompt_from_json(PROMPT_LIST_FILE, 'classification')
    examples_data = load_prompt_from_json(prompt_json_path, 'examples', True, base_path=BM_DIR)

    # Compose system instructions from files' URI and role text data
    classification_instruction = "\n\nThese is the Eco-schemes classification data for each possible land use. There is an English and Spanish version. Use these to fill out the table data whenever you are prompted to describe a parcel:\n\n" + classification_data
    examples_instructions = "\n\nThese are 3 examples of expected responses for parcel descriptions. Use them as a reference for formatting and content whenever you are prompted to describe a parcel. Use exactly the same keys and return nothing but the JSON as your reply:\n\n" + examples_data
    system_instructions = role_prompt + EXCLUSIVITY_RULE + CALCULATIONS_RULE + classification_instruction + examples_instructions

    return system_instructions
