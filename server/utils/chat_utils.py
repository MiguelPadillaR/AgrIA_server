import os
from server.config.constants import TEMP_UPLOADS_PATH

def save_image_and_get_path(file) -> str:
    """
    Stores file in server's local temp dir
    Arguments:
        file (File): Image file to store.
    Returns:
        filepath (str): Path of the stored image.
    """
    upload_dir = TEMP_UPLOADS_PATH
    os.makedirs(upload_dir, exist_ok=True)
    filename = file.filename
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    return filepath
