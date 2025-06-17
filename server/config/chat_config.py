from google.genai import types
from ..utils.llm_utils import generate_system_instructions
from.llm_client import client
from .constants import CONTEXT_DOCUMENTS_FILE, MODEL_NAME, PROMPT_LIST_FILE

def create_chat():
    return client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction= generate_system_instructions(
                CONTEXT_DOCUMENTS_FILE,
                PROMPT_LIST_FILE)
        ),
    )
CHAT = create_chat()


