import os

def save_image_and_get_path(file) -> str:
    upload_dir = 'temp/uploads'
    os.makedirs(upload_dir, exist_ok=True)
    filename = file.filename
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    return filepath
