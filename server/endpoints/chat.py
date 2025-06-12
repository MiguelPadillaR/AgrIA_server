import json
import os
from pathlib import Path
from flask import Blueprint, request, jsonify
from server.services.chat_service import *
from ..config.constants import TEMP_UPLOADS_PATH, PROMPT_LIST_FILE
from ..utils.llm_utils import load_prompt_from_json

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
    try:
        image_date = request.form.get('imageDate')
        image_crops = json.loads(request.form.get('imageCrops'))
        image_filename = request.form.get('imageFilename')
        
        # Build image context prompt
        image_context_prompt =f'FECHA DE IMAGEN: {image_date}\nCULTIVOS DETECTADOS: {len(image_crops)}'
        for crop in image_crops:
            image_context_prompt+= f'\nTipo: {crop["uso_sigpac"]}\nSuperficie (m2): {crop["dn_surface"]}'
        
        # Read image desc file and insert image context prompt
        image_desc_prompt =  load_prompt_from_json(PROMPT_LIST_FILE, is_image_desc_prompt=True).replace("INSERT_DATE_AND_CROPS", image_context_prompt)
        
        # Open image from path
        image_path = Path(os.path.join(TEMP_UPLOADS_PATH, image_filename))
        image = Image.open(image_path)

        response = {
            "text": chat.send_message([image, image_desc_prompt],).text,
            "imageDesc":image_context_prompt
            }

        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500