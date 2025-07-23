from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
import openai
import json
import os
import csv
import sqlite3
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from googletrans import Translator
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps  # ✅ Added

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or 'dev-secret-key'

# Configure upload folders
UPLOAD_FOLDER = "static/uploads"
BOOKING_FOLDER = "static/bookings"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BOOKING_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["BOOKING_FOLDER"] = BOOKING_FOLDER

# Load OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Load knowledge base
with open("knowledge_base.json", "r", encoding="utf-8") as f:
    knowledge_base = json.load(f)

# Initialize Translator
translator = Translator()

# Database Setup
def init_db():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Bookings table
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  guest_name TEXT,
                  room_type TEXT,
                  check_in DATE,
                  check_out DATE,
                  special_requests TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT)''')
    
    # Add default admin user if not exists
    admin_exists = c.execute("SELECT 1 FROM users WHERE username = 'admin'").fetchone()
    if not admin_exists:
        hashed_pw = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                 ('admin', hashed_pw))
    
    conn.commit()
    conn.close()

init_db()

# ✅ Fixed login_required decorator with @wraps
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_chatbot_response(user_input, context=""):
    try:
        full_prompt = f"""
        You are a hotel concierge AI. Use this knowledge base:
        {knowledge_base}

        Current Context: {context}

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

def process_booking_csv(file_path):
    bookings = []
    try:
        with open(file_path, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if all(key in row for key in ['guest_name', 'room_type', 'check_in', 'check_out']):
                    bookings.append({
                        'guest_name': row['guest_name'],
                        'room_type': row['room_type'],
                        'check_in': row['check_in'],
                        'check_out': row['check_out'],
                        'special_requests': row.get('special_requests', '')
                    })
        return bookings
    except Exception as e:
        print(f"Error processing CSV: {str(e)}")
        return []

def save_booking_to_db(booking_data):
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO bookings 
                    (guest_name, room_type, check_in, check_out, special_requests)
                    VALUES (?, ?, ?, ?, ?)''',
                 (booking_data['guest_name'], 
                  booking_data['room_type'],
                  booking_data['check_in'],
                  booking_data['check_out'],
                  booking_data['special_requests']))
        conn.commit()
        return c.lastrowid
    except Exception as e:
        print(f"Error saving to DB: {str(e)}")
        return None
    finally:
        conn.close()

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('login'))
        
        conn = sqlite3.connect('hotel.db')
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop('username', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
@login_required
def ask():
    user_input = request.form["message"]
    image = request.files.get("image")
    booking_csv = request.files.get("booking_csv")

    # Language detection and translation
    detected_lang = translator.detect(user_input).lang
    translated_input = translator.translate(user_input, src=detected_lang, dest='en').text

    # Process image if uploaded
    image_info = ""
    if image:
        filename = secure_filename(image.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(image_path)
        image_info = f"User uploaded an image: {filename}"

    # Process bookings if CSV uploaded
    booking_info = ""
    if booking_csv:
        filename = secure_filename(booking_csv.filename)
        csv_path = os.path.join(app.config["BOOKING_FOLDER"], filename)
        booking_csv.save(csv_path)
        
        bookings = process_booking_csv(csv_path)
        if bookings:
            for booking in bookings:
                booking_id = save_booking_to_db(booking)
                if booking_id:
                    booking_info += f"\nBooking #{booking_id} for {booking['guest_name']} processed."
            booking_info += "\nAll CSV bookings processed."
        else:
            booking_info = "\nNo valid bookings in CSV."

    # Generate response
    context = f"{image_info}\n{booking_info}"
    bot_response_en = get_chatbot_response(translated_input, context)
    bot_response = translator.translate(bot_response_en, src='en', dest=detected_lang).text

    return jsonify({"response": bot_response})

@app.route("/bookings")
@login_required
def view_bookings():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    c.execute("SELECT * FROM bookings ORDER BY check_in")
    bookings = c.fetchall()
    conn.close()
    
    booking_list = []
    for booking in bookings:
        booking_list.append({
            'id': booking[0],
            'guest_name': booking[1],
            'room_type': booking[2],
            'check_in': booking[3],
            'check_out': booking[4],
            'special_requests': booking[5],
            'created_at': booking[6]
        })
    
    return render_template("bookings.html", bookings=booking_list)

if __name__ == "__main__":
    app.run(debug=True)
