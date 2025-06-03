from ..config.llm_client import client
import pathlib
import os

def upload_context_document(pdf_file_path: str) -> str:
    """
    Uploads a context document to the specified base path and returns its relative path.
    
    Args:
        document_path (str): The path to the document to be uploaded.
        base_path (str): The base path where the document will be stored.
        
    Returns:
        str: The relative path of the uploaded document.
    """
    if pdf_file_path and pathlib.Path(pdf_file_path).exists():
        try:
            uploaded_pdf = client.files.upload(
                file=pathlib.Path(pdf_file_path),
                config=dict(mime_type='application/pdf', display_name= pathlib.Path(pdf_file_path).name)
            )
        except Exception as e:
            print(f"Error uploading PDF: {e}")
            uploaded_pdf = None
        finally:
            return uploaded_pdf