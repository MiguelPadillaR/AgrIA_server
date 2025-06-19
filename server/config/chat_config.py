from google.genai import types
from ..utils.llm_utils import generate_system_instructions, set_initial_messages
from.llm_client import client
from .constants import CONTEXT_DOCUMENTS_FILE, MODEL_NAME, PROMPT_LIST_FILE

def create_chat():
    chat = client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction= generate_system_instructions(
                CONTEXT_DOCUMENTS_FILE,
                PROMPT_LIST_FILE)
        ),
        history=set_initial_messages()
    )
    return chat

CHAT = create_chat()


