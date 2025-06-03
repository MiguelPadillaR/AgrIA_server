from flask import Flask
from flask_cors import CORS
from .config.env_config import UI_URL
from .endpoints.hello import hello_bp
from .endpoints.user_input import user_input_bp
from .endpoints.image_upload import image_upload_bp
import shutil
import os

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": UI_URL}})
    
    # Delete temp files
    shutil.rmtree('temp') if os.path.exists('temp') else None

    # Register Blueprints
    app.register_blueprint(hello_bp)
    app.register_blueprint(user_input_bp)
    app.register_blueprint(image_upload_bp)

    return app