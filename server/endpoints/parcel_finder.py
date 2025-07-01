import os

from ..config.constants import TEMP_UPLOADS_PATH
from ..services.parcel_finder_service import get_parcel_image
from ..utils.parcel_finder_utils import *
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

    try:
        cadastral_reference = request.form.get('cadastralReference')
        selected_date = request.form.get('selectedDate')
        if not cadastral_reference:
            return jsonify({'error': 'No cadastral reference provided'}), 400
        if not selected_date:
            return jsonify({'error': 'No date provided'}), 400
        

        # TODO: Pass geometry and date to S2DR3 and save super-resolved image
        #get_s2dr3_image()
        
        # Get super-resolved image and store it for analyzing and display
        url_image_address = get_s2dr3_image_url_demo()

        geometry, metadata, url_image_address = get_parcel_image(cadastral_reference)
        response = { 
            "cadastralReference": cadastral_reference,
            "geometry": geometry,
            "imagePath": url_image_address,
            "metadata": metadata,
        }
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@parcel_finder_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join(os.getcwd(), TEMP_UPLOADS_PATH), filename)
