from pathlib import Path
import os

from flask import json

from ...config.constants import BASE_PROMPTS_PATH

BM_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

BM_PROMPT_LIST_FILE = BM_DIR / "prompt_list.json"
BM_SR_IMAGES_DIR = BM_DIR / "sr_images"
BM_LLM_DIR = BM_DIR / "llm_formatted_out"
BM_JSON_DIR = BM_DIR / "in_out"

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

# AgrIA Paper data
CADASTRAL_REF_LIST_PAPER = ["26002A001000010000EQ", "41004A033000290000IG","46113A023000420000RL", "06900A766000030000WA"]
DATES_PAPER = ["2025-6-6", "2025-4-5", "2024-3-22", "2024-10-21"]
IS_PAPER_DATA = False