from google.genai import types
from ..utils.llm_utils import generate_system_instructions, set_initial_history
from.llm_client import client
from .constants import MODEL_NAME

def create_chat():
    chat = client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction= generate_system_instructions()
        ),
        history=set_initial_history()
    )
    return chat

CHAT = create_chat()
# CHAT = None

with open("sys_ins.md", 'w') as f:
    f.write(generate_system_instructions())