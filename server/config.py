import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
UI_URL = os.getenv("UI_URL", "http://localhost:4200")

client = genai.Client(api_key=GEMINI_API_KEY)
model_name = "gemini-2.0-flash"
chat = client.chats.create(model=model_name)

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in .env")
