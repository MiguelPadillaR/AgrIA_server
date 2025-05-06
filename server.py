from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from a .env file
load_dotenv()

# Retrieve environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
UI_URL = os.getenv("UI_URL", "http://localhost:4200")

if not GEMINI_API_KEY:
    raise ValueError("API_KEY is not set in the environment variables")
elif not UI_URL:
    raise ValueError("UI_URL is not set in the environment variables")

# Configure Google Generative AI client
genai.configure(api_key=GEMINI_API_KEY)

# Prepare the model
model = genai.GenerativeModel("models/gemini-2.0-flash")

# Initialize Flask app
app = Flask(__name__)

# Enable CORS to allow requests from the Angular frontend
CORS(app, resources={r"/*": {"origins": UI_URL}})

@app.route('/hello-world', methods=['GET'])
def hello_world():
    return jsonify("Hello world!")

@app.route('/send-user-input', methods=['POST'])
def send_user_input():
    try:
        user_input = request.json.get('user_input', '')
        if not user_input:
            return jsonify({'error': 'No user input provided'}), 400

        response = model.generate_content(user_input)
        return jsonify({'response': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
