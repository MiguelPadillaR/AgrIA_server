import os
import shutil
from ..config.constants import TEMP_UPLOADS_PATH

def get_s2dr3_image(date: str, geometry: dict):
    """    Retrieves the S2DR3 image for a given date and geometry.
    Args:
        date (str): The date for which to retrieve the S2DR3 image.
        geometry (dict): The geometry of the area for which to retrieve the image.
    Returns:
        TODO
    """
    return "This function is not implemented yet. Please implement the logic to retrieve the S2DR3 image based on the geometry and date."

def get_s2dr3_image_url_demo():
        os.makedirs(TEMP_UPLOADS_PATH, exist_ok=True)
        sr_images_dir = TEMP_UPLOADS_PATH # Must be this dir for LLM to read it
        sr_image_name = "image_name.jpg"

        ###############
        #  TODO: Mock example. Remove when feature has been implemented.
        sr_images_dir = get_sr_dir()
        sr_image_name = "GoogleMaps_Munovela-P1.jpg"
        sr_image_path = os.path.join(sr_images_dir, sr_image_name)
        
        # Move image to upload folder if not there already!
        destination_dir =  os.path.join(os.getcwd(), TEMP_UPLOADS_PATH, sr_image_name)
        print(destination_dir)
        print(sr_image_path)

        shutil.copy(sr_image_path, destination_dir)
        print(os.path.exists(destination_dir))

        ###############
        return f"{os.getenv('API_URL')}/uploads/{sr_image_name}"

def get_image_url():
        # TODO: Get SIGPAC image (Service)
        
        # Save image
        os.makedirs(TEMP_UPLOADS_PATH, exist_ok=True)
        sr_images_dir = TEMP_UPLOADS_PATH # Must be this dir for LLM to read it
        sr_image_name = "image_name.jpg"

        return f"{os.getenv('API_URL')}/uploads/{sr_image_name}"

def get_sr_dir(): # DELETE THIS, IT'S A MOCK METHOD
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    common_parent_dir = os.path.abspath(os.path.join(current_script_dir, '..', '..', '..'))
    data_dir = os.path.join(common_parent_dir, 'data')
    return  os.path.join(os.getcwd(), data_dir, "SR-images", "crop-fields")




