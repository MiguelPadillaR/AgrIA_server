import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
UI_URL = os.getenv("UI_URL", "http://localhost:4200")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in .env")
