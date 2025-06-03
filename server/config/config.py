import os
from google import genai
from dotenv import load_dotenv
from .utils.config_utils import load_system_instructions
from .utils.llm_utils import generate_initial_history

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
UI_URL = os.getenv("UI_URL", "http://localhost:4200")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in .env")

# Set file paths for system instructions
base_context_path = "./assets/LLM_assets/context"
base_prompts_path = "./assets/LLM_assets/prompts"
context_documents_file = "context_documents_links.json"
image_description_prompt_file ="image_description.json"
system_instruction_file = "LLM-role_prompt.txt"
# Set priming and load context documents for initial history
initial_history = generate_initial_history(context_documents_file, image_description_prompt_file, base_context_path, base_prompts_path)

# Initialize the Google Generative AI client and chat session
client = genai.Client(api_key=GEMINI_API_KEY)
model_name = "gemini-2.0-flash-lite"
if initial_history:
    chat = client.chats.create(
        model=model_name,
        history=initial_history
    )
else:
    chat = client.chats.create(
        model=model_name
    )
