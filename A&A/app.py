import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

@app.before_request
def create_tables():
    if not hasattr(app, 'db_initialized'):
        db.create_all()
        app.db_initialized = True

@app.route('/')
def index():
    return render_template('index.html', user=session.get('user'))

@app.route('/home')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('home.html', user=session['user'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user'] = username
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
        else:
            hashed_pw = generate_password_hash(password)
            new_user = User(username=username, password_hash=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            session['user'] = username
            return redirect(url_for('home'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/books')
def books():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('books.html')

@app.route('/api/get-story', methods=['POST'])
def get_story_from_api():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'error': 'API key is not configured on the server.'}), 500

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    prompt = "Tell me a short, enchanting story (around 150 words) that one might discover in a forgotten corner of a magical library. It should be mysterious and slightly whimsical."
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        result = response.json()

        if result.get('candidates'):
            story = result['candidates'][0]['content']['parts'][0]['text']
            return jsonify({'story': story})
        else:
            return jsonify({'error': "The library's magic is faint today. Please try again later."}), 500
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return jsonify({'error': 'A magical interference prevented the story from appearing.'}), 500


if __name__ == '__main__':
    app.run(debug=True)