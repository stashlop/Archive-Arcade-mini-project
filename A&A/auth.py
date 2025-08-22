from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3, os
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def get_db_path():
    inst = current_app.instance_path if hasattr(current_app, 'instance_path') else 'instance'
    Path(inst).mkdir(parents=True, exist_ok=True)
    return os.path.join(inst, 'users.db')

def get_conn():
    dbp = get_db_path()
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn=None):
    close_after = False
    if conn is None:
        conn = get_conn(); close_after = True
    cur = conn.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
    """)
    conn.commit()
    if close_after:
        conn.close()

# Replace the blueprint-level decorator with an explicit initializer:
def init_app(app):
    """
    Ensure users DB is initialized. Call from your create_app() after app is created:
        from auth import init_app as init_auth_db
        init_auth_db(app)
    """
    with app.app_context():
        init_db()

@auth_bp.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    username = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    if not username or not email or not password:
        flash('Username, email and password are required.', 'error')
        return redirect(url_for('auth.signup'))
    pw_hash = generate_password_hash(password)
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username,email,password_hash,created_at) VALUES (?,?,?,?)",
                    (username, email, pw_hash, datetime.utcnow().isoformat()))
        conn.commit()
        uid = cur.lastrowid
    except Exception as e:
        conn.rollback()
        # simple uniqueness hint
        flash('User exists or invalid data. Use a different username/email.', 'error')
        conn.close()
        return redirect(url_for('auth.signup'))
    conn.close()
    session.clear()
    session['user_id'] = uid
    session['username'] = username
    flash('Signup successful. You are logged in.', 'success')
    return redirect(url_for('home') if 'home' in current_app.view_functions else '/')

@auth_bp.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    ident = (request.form.get('ident') or '').strip()
    password = request.form.get('password') or ''
    if not ident or not password:
        flash('Provide username/email and password.', 'error')
        return redirect(url_for('auth.login'))
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ? OR email = ? LIMIT 1", (ident, ident.lower()))
    row = cur.fetchone()
    conn.close()
    if not row or not check_password_hash(row['password_hash'], password):
        flash('Invalid credentials.', 'error')
        return redirect(url_for('auth.login'))
    session.clear()
    session['user_id'] = row['id']
    session['username'] = row['username']
    flash('Logged in.', 'success')
    return redirect(url_for('home') if 'home' in current_app.view_functions else '/')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('home') if 'home' in current_app.view_functions else '/')

def login_required(view):
    """Decorator for route handlers that require an authenticated user."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            # preserve requested path in `next` so user can return after login
            return redirect(url_for('auth.login', next=request.path))
        return view(*args, **kwargs)
    return wrapped