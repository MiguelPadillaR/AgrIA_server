from ..config.chat_init_config import CHAT as chat

def generate_user_response(user_input: str) -> str:
    response = chat.send_message(user_input,)
    return response.text
