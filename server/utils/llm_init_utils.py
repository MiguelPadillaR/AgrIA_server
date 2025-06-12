from ..config.constants import (
    CONTEXT_DOCUMENTS_FILE,
    PROMPT_LIST_FILE,
)
from .llm_utils import generate_initial_history  # No circular import here

def get_initial_history():
    return generate_initial_history(
        CONTEXT_DOCUMENTS_FILE,
        PROMPT_LIST_FILE
    )
