from flask import Flask
from flask_cors import CORS
from .config.env_config import UI_URL
from .endpoints.hello import hello_bp
from .endpoints.chat import chat_bp
from .endpoints.parcel_finder import parcel_finder_bp
import shutil
import os

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": UI_URL}})
    
    # Delete temp files
    shutil.rmtree('temp') if os.path.exists('temp') else None

    # Register Blueprints
    app.register_blueprint(hello_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(parcel_finder_bp)
    
    return app