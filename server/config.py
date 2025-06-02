import os
from google import genai
from dotenv import load_dotenv
from .utils.config_utils import load_system_instructions

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
UI_URL = os.getenv("UI_URL", "http://localhost:4200")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in .env")

# Set file paths for system instructions
base_prompts_path = "./assets/LLM_assets/prompts"
image_description_prompt_file ="image_description.json"
system_instruction_file = "LLM-role_prompt.txt"

# Initialize the Google Generative AI client and chat session
client = genai.Client(api_key=GEMINI_API_KEY)
model_name = "gemini-2.0-flash"


system_instructions = load_system_instructions(os.path.join(base_prompts_path
                                                            ,system_instruction_file)).replace("\\", "/")

chat = client.chats.create(model=model_name)

# If system instructions are loaded, send them as a hidden initial message
if system_instructions:
    # Send the system instruction as an initial message with a role that the user won't see directly.
    # Often 'system' or 'user' with a very specific intent is used for priming.
    # The key is to make it clear this is for the model's internal guidance.
    # For a persistent instruction, you'd typically send it as a user message
    # that the model is expected to internalize.
    
    # A common pattern is to send it as a "user" message that acts as the initial
    # setup for the AI.
    print(chat.send_message(system_instructions).text) # The model will process this first.

