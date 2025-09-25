import json
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
        is_detailed_description: bool = "true" in str(request.form.get("isDetailedDescription")).lower()
        if not file:
            return jsonify({'error': 'No image file provided'}), 400
        
        response_text = get_image_description(file, is_detailed_description)

        return jsonify({'response': response_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@chat_bp.route('/load-parcel-data-to-chat', methods=['POST'])
def send_parcel_info_to_chat():
    try:
        image_date = request.form.get('imageDate')
        image_crops = json.loads(request.form.get('imageCrops'))
        image_filename = request.form.get('imageFilename')
        is_detailed_description: bool = "true" in str(request.form.get("isDetailedDescription")).lower()
        lang = request.form.get('lang')

        response = get_parcel_description(image_date, image_crops, image_filename, is_detailed_description, lang)

        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@chat_bp.route('/get-input-suggestion', methods=['POST'])
def get_input_suggestion():
    try:
        lang = request.form.get('lang')
        chat_history = chat.get_history()
        response = get_suggestion_for_chat(chat_history, lang)
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@chat_bp.route('/load-active-chat-history', methods=['GET'])
def load_active_chat_history():
    try:
        chat_history = chat.get_history()
        response = get_role_and_content(chat_history)
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500