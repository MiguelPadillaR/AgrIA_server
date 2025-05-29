from flask import Blueprint, request, jsonify
from PIL import Image
from server.utils.image_utils import save_image_and_get_path
import google.generativeai as genai
from google.generativeai import types
from ..config import chat

image_upload_bp = Blueprint('image_upload', __name__)

@image_upload_bp.route('/send-image', methods=['POST'])
# def send_image():
#     try:
#         file = request.files.get('image')
#         if not file:
#             return jsonify({'error': 'No image file provided'}), 400

#         filepath = save_image_and_get_path(file)
#         model = genai.GenerativeModel("models/gemini-2.0-flash")

#         image = Image.open(file.stream)
        
#         prompt = (
#             "Give a 50 word description of the satellite image. "
#             "In description, mention the type of possible crops and soil. "
#             "In description, mention what type of Eco-regime (from P1 to P7) can be applied here. "
#             "Outside of description, ask a few follow up question for better eco-regime classification. "
#             "Context document: https://www.fega.gob.es/sites/default/files/inline-files/220930_nota_aclaratoria_aplicacion_eco_regimenes.pdf."
#         )
        
#         response = model.generate_content([
#             types.Part.from_bytes(data=image.tobytes(), mime_type='image/jpeg'),
#             prompt,
#         ])

#         return jsonify({'response': response.text})
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

def send_image():
    try:
        file = request.files.get('image')
        if not file:
            return jsonify({'error': 'No image file provided'}), 400
        filepath = save_image_and_get_path(file)

        image = Image.open(filepath)
        response = chat.send_message([image, "Give me a 50 word description of the satellite image."])

        return jsonify({'response': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

