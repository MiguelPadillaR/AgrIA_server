from flask import Blueprint, jsonify

hello_bp = Blueprint('hello', __name__)

@hello_bp.route('/hello-world', methods=['GET'])
def hello_world():
    return jsonify("Hello world!")
