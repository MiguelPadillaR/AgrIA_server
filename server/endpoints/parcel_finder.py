from flask import Blueprint, request, jsonify
from ..utils.parcel_finder_utils import *

parcel_finder_bp = Blueprint('find_parcel', __name__)

@parcel_finder_bp.route('/find-parcel', methods=['POST'])
def find_parcel():
    try:
        cadastral_reference = request.form.get('cadastralReference')
        selected_date = request.form.get('selectedDate')
        if not cadastral_reference:
            return jsonify({'error': 'No cadastral reference provided'}), 400
        if not selected_date:
            return jsonify({'error': 'No date provided'}), 400
        
        geometry, metadata = find_from_cadastral_registry(cadastral_reference)

        # TODO: Pass geometry and date to S2DR3 and get super-resolved image

        # TODO: Decide what needs to return to frontend!!
        response = { "geometry": geometry, "metadata": metadata }
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@parcel_finder_bp.route('/get-crop-classification', methods=['GET'])  
def get_crop_classification():
    try:
        classification_df = get_crop_classification()
        if classification_df.empty:
            return jsonify({'error': 'No crop classification data found'}), 404
        print(classification_df)
        return jsonify({"classification": classification_df.to_dict(orient='records')}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500  
