from flask import Blueprint, request, jsonify
from server.services.user_input_service import generate_user_response

user_input_bp = Blueprint('user_input', __name__)

@user_input_bp.route('/send-user-input', methods=['POST'])
def send_user_input():
    try:
        user_input = request.form.get('user_input')
        if not user_input:
            return jsonify({'error': 'No user input provided'}), 400
        
        response_text = generate_user_response(user_input)
        
        return jsonify({'response': response_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
