import os
import shutil

from ..config.constants import TEMP_UPLOADS_PATH
from ..services.parcel_finder_service import get_parcel_image
from ..utils.parcel_finder_utils import *
from ..services.parcel_finder_service import get_parcel_image
from flask import Blueprint, request, jsonify, send_from_directory

parcel_finder_bp = Blueprint('find_parcel', __name__)

@parcel_finder_bp.route('/find-parcel', methods=['POST'])
def find_parcel():
    """
    Handles a request to find a parcel by its cadastral reference and date.
    This endpoint expects a POST request with form data containing:
        - 'cadastralReference': The cadastral reference of the parcel to search for.
        - 'selectedDate': The date for which the parcel data is requested.
    The function performs the following steps:
        1. Validates the presence of required form data.
        2. Retrieves the parcel's geometry and metadata using the cadastral reference.
        3. (TODO) Integrates with the super-resolution service to obtain a super-resolved image for the parcel and date.
        4. (Mock) Copies a sample super-resolved image to the upload directory.
        5. Constructs a response containing the cadastral reference, geometry, image URL, and metadata.
    Returns:
        Flask Response: A JSON response with the parcel data or an error message and appropriate HTTP status code.
    """
    # Clear uploaded files adn dirs
    if os.path.exists(TEMP_UPLOADS_PATH):
        for file in os.listdir(TEMP_UPLOADS_PATH):
            file_path = os.path.join(os.getcwd(), TEMP_UPLOADS_PATH, file)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

    init = datetime.now()
    try:
        cadastral_reference = request.form.get('cadastralReference')
        selected_date = request.form.get('selectedDate')
        if not cadastral_reference:
            return jsonify({'error': 'No cadastral reference provided'}), 400
        if not selected_date:
            return jsonify({'error': 'No date provided'}), 400
        
        # Get image and store it for display
        geometry, metadata, url_image_address = get_parcel_image(cadastral_reference, selected_date)
        
        # TODO: Pass image to super-resolution module and save super-resolved image
        #get_sr_image()

        response = { 
            "cadastralReference": cadastral_reference,
            "geometry": geometry,
            "imagePath": url_image_address,
            "metadata": metadata,
        }
        print("TIME TAKEN:", datetime.now() - init)
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@parcel_finder_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join(os.getcwd(), TEMP_UPLOADS_PATH), filename)
