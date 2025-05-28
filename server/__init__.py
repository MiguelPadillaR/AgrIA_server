import shutil
from flask import Flask
from flask_cors import CORS
from .config import UI_URL
from .routes.hello import hello_bp
from .routes.user_input import user_input_bp
from .routes.image_upload import image_upload_bp
def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": UI_URL}})
    # Delete temp files
    shutil.rmtree('temp')

    # Register Blueprints
    app.register_blueprint(hello_bp)
    app.register_blueprint(user_input_bp)
    app.register_blueprint(image_upload_bp)

    return app
