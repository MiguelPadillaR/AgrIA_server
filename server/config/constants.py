from pathlib import Path

MODEL_NAME = "gemini-2.0-flash-lite"
BASE_CONTEXT_PATH = Path("./assets/LLM_assets/context")
BASE_PROMPTS_PATH = Path("./assets/LLM_assets/prompts")

CONTEXT_DOCUMENTS_FILE = "context_document_links.json"
PROMPT_LIST_FILE = "prompt_list.json"

TEMP_UPLOADS_PATH = Path('temp/')

FULL_DESC_TRIGGER = '###DESCRIBE_LONG_IMAGE###'
SHORT_DESC_TRIGGER = '###DESCRIBE_SHORT_IMAGE###'

MIME_TYPES = {
    'txt': 'text/plain',
    'md': 'text/markdown',
    'pdf': 'application/pdf',
    'json': 'application/json',
    'csv': 'text/csv',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'jpg': 'image/jpeg',
    'png': 'image/png',
}

ANDALUSIA_TILES = ["29SPC", "29SQC", "30STH", "30SUH", "30SVH", "30SWH", "30SXH", "30SYH", "30SXG", 
        "30SWG", "30SVG", "30SUG", "30STG", "29SQB" ,"29SPB", "30STF", "30SUF", 
        "30SVF", "30SWF"]


SR_BANDS = ["B02", "B03", "B04", "B08"]
BANDS_DIR = TEMP_UPLOADS_PATH / "bands"
MERGED_BANDS_DIR = TEMP_UPLOADS_PATH / "merged_bands"
MASKS_DIR = TEMP_UPLOADS_PATH / "masks"
SR5M_DIR = TEMP_UPLOADS_PATH / "sr_5m"
RESOLUTION = 10

SEN2SR_SR_DIR = TEMP_UPLOADS_PATH / "sr_2.5m"
