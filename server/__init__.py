from flask import Flask
from flask_cors import CORS

from .utils.parcel_finder_utils import reset_temp_dir
from .config.env_config import UI_URL
from .endpoints.chat import chat_bp
from .endpoints.parcel_finder import parcel_finder_bp

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": UI_URL}})
    
    # Delete temp files
    reset_temp_dir()

    # Register Blueprints
    app.register_blueprint(chat_bp)
    app.register_blueprint(parcel_finder_bp)
    
    return app