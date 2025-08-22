import os
from flask import Flask, render_template, request, session, redirect, url_for
from flask import flash, jsonify
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

# import blueprints safely (package vs script execution)
try:
    from .games_api import games_bp
except Exception:
    from games_api import games_bp
try:
    from .auth import auth_bp, init_app as init_auth_db
except Exception:
    from auth import auth_bp, init_app as init_auth_db

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

@app.route('/video-games')
def video_games():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('video_games.html')

@app.route('/cafe')
def cafe():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('cafe.html')



def create_app(config=None):
    from flask import Flask
    app = Flask(__name__, instance_relative_config=True)
    app.secret_key = app.config.get('SECRET_KEY') or 'dev-secret-key-change-me'
    # ensure a secret key for session (override with env or config in production)

    # register blueprints
    app.register_blueprint(games_bp)
    app.register_blueprint(auth_bp)

    # initialize auth DB now that app exists
    init_auth_db(app)

    # enforce login for protected paths (books, video games, purchase/rent actions)
    RESTRICTED_PREFIXES = ('/books', '/video_games', '/purchase', '/rent', '/checkout', '/cart', '/api/purchase')

    @app.before_request
    def require_login_for_restricted():
        # allow static, public endpoints and API admin/seed
        path = request.path or '/'
        # ignore safe endpoints
        if any(path.startswith(p) for p in RESTRICTED_PREFIXES):
            if not session.get('user_id'):
                # redirect to login and include `next` so user returns after auth
                return redirect(url_for('login', next=path))

    return app

if __name__ == '__main__':
    app.run(debug=True)