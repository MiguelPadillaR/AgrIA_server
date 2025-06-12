# config/llm_client.pyfrom google import genai
from.llm_client import client
from .constants import MODEL_NAME
from ..utils.llm_init_utils import get_initial_history

def create_chat():
    history = get_initial_history()
    return client.chats.create(
        model=MODEL_NAME,
        history=history if history else None
    )
CHAT = create_chat()