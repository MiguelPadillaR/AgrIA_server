import os
import shutil
import time
from .constants import BM_SR_DIR, BM_DATA_DIR

def copy_file_to_dir(src, dest_dir = BM_SR_DIR, is_sr4s: bool = False):
    """
    Copy source file to destiny dir. Used mainly to copy SR TIFs into `BM_SR_DIR`
    Arguments:
        src (str): Source file to copy from.
        dest_dir (str): Dir to copy file to. De.fault is `BM_SR_DIR`.
    Returns:
        dest_path (str): Full destiny filepath.
    """
    # Extract the filename and extension
    __, ext = os.path.splitext(src)
    if type(is_sr4s) is not bool:
        dest_dir = BM_DATA_DIR
        name = f"original{ext}"
    else:
        name = "SR4S" if is_sr4s else "SEN2SR"
    timestamp = str(time.time())
    filename =  f"{timestamp}_{name}{ext}"

    # Construct the initial destination path
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    # Check for conflicts and rename if necessary
    #    counter = 1
    #    while os.path.exists(dest_path):
    #        dest_path = os.path.join(dest_dir, f"{filename}_{counter}{ext}")
    #        counter += 1
    # Copy the file to the resolved destination path
    shutil.copy2(src, dest_path)
    print(f"\nFile copied for benchmark to: {dest_path}\n")
    return dest_path
