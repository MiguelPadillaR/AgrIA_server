from ..config.constants import MIME_TYPES
from ..config.llm_client import client
import pathlib

def upload_context_document(context_file_path: str) -> str:
    """
    Uploads a context document to the specified base path and returns its relative path.
    
    Args:
        document_path (str): The path to the document to be uploaded.
        base_path (str): The base path where the document will be stored.
        
    Returns:
        str: The relative path of the uploaded document.
    """
    if context_file_path and pathlib.Path(context_file_path).exists():
        try:
            mime_type = MIME_TYPES.get(context_file_path.split(".")[-1].lower(), 'application/octet-stream')
            uploaded_file = client.files.upload(
                file=pathlib.Path(context_file_path),
                config=dict(mime_type=mime_type, display_name= pathlib.Path(context_file_path).name)
            )
        except Exception as e:
            print(f"Error uploading file: {e}")
            uploaded_file = None
        finally:
            return uploaded_file