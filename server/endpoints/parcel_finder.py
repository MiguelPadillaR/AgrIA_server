import os
from datetime import datetime
from ..config.constants import TEMP_DIR
from ..utils.parcel_finder_utils import check_cadastral_data, is_coord_in_zones, reset_dir
from ..services.parcel_finder_service import get_parcel_image
from flask import Blueprint, make_response, request, jsonify, send_from_directory

parcel_finder_bp = Blueprint('find_parcel', __name__)

@parcel_finder_bp.route('/load-parcel-description', methods=['POST'])
def load_parcel_descriptio():
    """
    Loads and returns dinamically the correct parcel description file.
    Returns:
        response (dict): Contains the image description of the text file.
    """
    try:
        lang = request.form.get('lang')
        parcel_desc_file = os.path.join(TEMP_DIR, f"parcel_desc-{lang}.txt")
        content = "..."
        
        if os.path.exists(parcel_desc_file):
            print("Loading parcel description file:", parcel_desc_file)
            with open(parcel_desc_file, 'r', encoding='utf-8') as file:
                content = file.read()
            print(content)
        return jsonify({'response': content}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        3. Integrates with the L1BSR super-resolution pre-trained model to obtain a super-resolved image for the parcel and date.
        4. Sends super-resolved image to the upload directory.
        5. Constructs a response containing the cadastral reference, geometry, image URL, and metadata.
    Returns:
        response: A JSON response with the parcel data or an error message and appropriate HTTP status code.
    """
    reset_dir(TEMP_DIR)
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
            get_sr_image=True
            )

        response = { 
            "cadastralReference": cadastral_reference,
            "geometry": geometry,
            "imagePath": url_image_address,
            "metadata": metadata,
        }
        print(f"\nTOTAL TIME TAKEN: {datetime.now() - init}\n")
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@parcel_finder_bp.route('/is-coord-in-zone', methods=['POST'])
def is_coord_in_zone():
    try:
        lat = float(request.form.get('lat'))
        lng = float(request.form.get('lng'))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing coordinates"}), 400

    return jsonify({"response": is_coord_in_zones(lng, lat)}), 200

@parcel_finder_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    response = make_response(
        send_from_directory(
            os.path.join(os.getcwd(), TEMP_DIR),
            filename
        )
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
