from pathlib import Path
import os

from flask import json

from ...config.constants import BASE_PROMPTS_PATH

BM_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

BM_PROMPT_LIST_FILE = BM_DIR / "prompt_list.json"
BM_SR_IMAGES_DIR = BM_DIR / "sr_images"
BM_JSON_DIR = BM_DIR / "LLM_output"

OG_ROLE_FILEPATH = BASE_PROMPTS_PATH / "LLM-role_prompt.txt"
OG_CLASSIFICATION_FILEPATH = BASE_PROMPTS_PATH / "classification.json"
BM_PROMPT_LIST_DATA = {
    "description": "Initial setup prompts for the Gemini model",
    "examples": {
        "name": "examples",
        "examples": "response_examples"
    }
}

# (Optional) write to file:
with BM_PROMPT_LIST_FILE.open("w") as f:
    json.dump(BM_PROMPT_LIST_DATA, f, indent=4)
