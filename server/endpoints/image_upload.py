from flask import Blueprint, request, jsonify
from ..services.image_upload_service import get_image_description

image_upload_bp = Blueprint('image_upload', __name__)

@image_upload_bp.route('/send-image', methods=['POST'])
def send_image():
    try:
        file = request.files.get('image')
        if not file:
            return jsonify({'error': 'No image file provided'}), 400
        
        response_text = get_image_description(file)

        return jsonify({'response': response_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

