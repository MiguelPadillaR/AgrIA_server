from flask import Flask
from flask_cors import CORS

from .benchmark.sr.constants import BM_DATA_DIR, BM_RES_DIR

from .config.constants import TEMP_DIR
from .config.env_config import UI_URL
from .endpoints.chat import chat_bp
from .endpoints.parcel_finder import parcel_finder_bp
from .utils.parcel_finder_utils import reset_dir

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": UI_URL}})
    
    # Reset temp and benchmark dirs
    reset_dir(TEMP_DIR)
    reset_dir(BM_DATA_DIR)
    reset_dir(BM_RES_DIR)

    # Register Blueprints
    app.register_blueprint(chat_bp)
    app.register_blueprint(parcel_finder_bp)
    
    return app