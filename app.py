from flask import Flask, request, jsonify, render_template
import openai
import json
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from googletrans import Translator
from utils.vision_utils import image_to_text

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Upload folder configuration
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Load OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Load knowledge base
with open("knowledge_base.json", "r", encoding="utf-8") as f:
    knowledge_base = json.load(f)

# Initialize Google Translator
translator = Translator()

def get_chatbot_response(user_input, image_info=""):
    try:
        full_prompt = f"""
        You are a hotel concierge AI. Use this knowledge base:
        {knowledge_base}

        {image_info}

        User: {user_input}
        """
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": full_prompt}],
            temperature=0.5
        )
        return response.choices[0].message['content']
    except Exception as e:
        return f"Error: {str(e)}"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    user_input = request.form["message"]
    image = request.files.get("image")

    # Step 1: Detect original language
    detected_lang = translator.detect(user_input).lang

    # Step 2: Translate user input to English
    translated_input = translator.translate(user_input, src=detected_lang, dest='en').text

    # Step 3: Handle image (optional)
    image_info = ""
    if image:
        filename = secure_filename(image.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(image_path)
        image_info = image_to_text(image_path)

    # Step 4: Get bot response in English
    bot_response_en = get_chatbot_response(translated_input, image_info)

    # Step 5: Translate response back to user's language
    bot_response = translator.translate(bot_response_en, src='en', dest=detected_lang).text

    return jsonify({"response": bot_response})

if __name__ == "__main__":
    app.run(debug=True)
