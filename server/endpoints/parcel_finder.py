import os
from ..config.constants import TEMP_UPLOADS_PATH
from ..services.parcel_finder_service import get_parcel_image
from ..utils.parcel_finder_utils import *
from ..services.parcel_finder_service import get_parcel_image
from flask import Blueprint, make_response, request, jsonify, send_from_directory

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
        response: A JSON response with the parcel data or an error message and appropriate HTTP status code.
    """
    reset_temp_dir()
    init = datetime.now()
    try:
        cadastral_reference = request.form.get('cadastralReference')
        selected_date = request.form.get('selectedDate')
        is_from_cadastral_reference = "True" in request.form.get('isFromCadastralReference')
        parcel_geometry = None if request.form.get('parcelGeometry') == 'None' else request.form.get('parcelGeometry')
        parcel_metadata = request.form.get('parcelMetadata')
        coordinates = None if request.form.get('coordinates') is None else list(map(float, request.form.get('coordinates').split(',')))
        province = request.form.get('province')
        municipality = request.form.get('municipality')
        polygon = request.form.get('polygon')
        parcel_id = request.form.get('parcelId')
        
        if is_from_cadastral_reference:
            cadastral_reference = check_cadastral_data(cadastral_reference, province, municipality, polygon, parcel_id)

        if not selected_date:
            return jsonify({'error': 'No date provided'}), 400
        
        # Get image and store it for display
        geometry, metadata, url_image_address = get_parcel_image(
            cadastral_reference,
            selected_date,
            is_from_cadastral_reference,
            parcel_geometry,
            parcel_metadata,
            coordinates,
            get_sr_image=False
            )

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

@parcel_finder_bp.route('/find-parcel-from-location', methods=['POST'])
def find_parcel_from_location():
    reset_temp_dir()
    init = datetime.now()
    try:
        province = request.form.get('province')
        municipality = request.form.get('municipality')
        polygon = request.form.get('polygon')
        parcel_id = request.form.get('parcelId')
        selected_date = request.form.get('selectedDate')
        
        # Get image and store it for display
        cadastral_reference, geometry, metadata, url_image_address = get_parcel_image_from_location(
            province,
            municipality,
            polygon,
            parcel_id,
            selected_date
        )

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

    return
    

@parcel_finder_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    response = make_response(
        send_from_directory(
            os.path.join(os.getcwd(), TEMP_UPLOADS_PATH),
            filename
        )
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
