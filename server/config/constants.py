from pathlib import Path

MODEL_NAME = "gemini-2.0-flash-lite"
BASE_CONTEXT_PATH = Path("./assets/LLM_assets/context")
BASE_PROMPTS_PATH = Path("./assets/LLM_assets/prompts")

CONTEXT_DOCUMENTS_FILE = "context_document_links.json"
PROMPT_LIST_FILE = "prompt_list.json"

TEMP_UPLOADS_PATH = Path('temp/uploads')

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
