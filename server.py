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
        user_input = request.form.get('user_input')
        if not user_input:
            return jsonify({'error': 'No user input provided'}), 400

        response = model.generate_content(user_input)
        return jsonify({'response': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/send-image', methods=['POST'])
def send_image():
    try:
        file = request.files.get('image')
        print(f"Received file: {file}")
        if not file:
            return jsonify({'error': 'No image file provided'}), 400

        filepath = save_image_and_get_path(file)
        image_file = model.files.upload(file=filepath)
        
        prompt = (
            "Give a 50 word description of the satellite image. "
            "In description, mention the type of possible crops and soil. "
            "In description, mention what type of Eco-regime (from P1 to P7) can be applied here."
            "Ouside of description, ask a few follow up question for better eco-regime classification."
            "Context document: https://www.fega.gob.es/sites/default/files/inline-files/220930_nota_aclaratoria_aplicacion_eco_regimenes.pdf."
        )
        
        response = model.models.generate_content(
            model="gemini-2.0-flash",
            contents=[image_file, prompt],
        )
        return jsonify({'response': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
def save_image_and_get_path(file):
    upload_dir = 'temp/uploads'
    os.makedirs(upload_dir, exist_ok=True)
    print(f"Upload directory: {upload_dir}")
    filename = file.filename;
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    
    return filepath

if __name__ == '__main__':
    app.run(debug=True)
