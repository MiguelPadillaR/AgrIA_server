from flask import Blueprint, request, jsonify
from server.services.chat_service import *

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/send-user-input', methods=['POST'])
def send_user_input():
    try:
        user_input = request.form.get('userInput')
        if not user_input:
            return jsonify({'error': 'No user input provided'}), 400
        
        response_text = generate_user_response(user_input)
        
        return jsonify({'response': response_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/send-image', methods=['POST'])
def send_image():
    try:
        file = request.files.get('image')
        print("Image file", file)
        if not file:
            return jsonify({'error': 'No image file provided'}), 400
        
        response_text = get_image_description(file)

        return jsonify({'response': response_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@chat_bp.route('/send-parcel-info-to-chat', methods=['POST'])
def send_parcel_info_to_chat():
    image_date = request.form.get('imageDate')
    image_crops = request.form.get('imageCrops')
    image_filename = request.form.get('imageFilename')
    # TODO: Complete
    response = ''
    return