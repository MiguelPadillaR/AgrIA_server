import google.generativeai as genai

def generate_user_response(user_input: str) -> str:
    model = genai.GenerativeModel("models/gemini-2.0-flash")
    response = model.generate_content(user_input)
    return response.text
