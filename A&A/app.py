import os
import sqlite3
from flask import Flask, render_template, request, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

# import blueprints safely (package vs script execution)
try:
    from .games_api import games_bp
except ImportError:
    from games_api import games_bp

try:
    from .books_api import books_bp, init_books_db
except ImportError:
    from books_api import books_bp, init_books_db

try:
    from .auth import auth_bp, init_app as init_auth_db
except ImportError:
    from auth import auth_bp, init_app as init_auth_db

try:
    from .cart_api import cart_bp
except ImportError:
    from cart_api import cart_bp


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    @app.before_request
    def create_tables():
        if not hasattr(app, 'db_initialized'):
            db.create_all()
            init_books_db()  # Initialize books database
            app.db_initialized = True

    @app.context_processor
    def inject_cart_count():
        items = session.get('cart', {}).get('items', [])
        return {'cart_count': sum(i.get('quantity', 1) for i in items)}

    # ---------------- Routes ----------------
    @app.route('/')
    def index():
        # Home page - accessible to all
        return render_template('index.html')

    @app.route('/home')
    def home():
        # Dashboard for logged in users
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        return redirect(url_for('index'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('ident')  # Changed from username to ident
            password = request.form.get('password')
            if not username or not password:
                flash("Please enter both username and password")
                return redirect(url_for('login'))

            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                session['user'] = username
                session['user_id'] = user.id  # Add user_id to match auth.py
                return redirect(url_for('home'))
            else:
                flash('Invalid username or password')
        return render_template('login.html')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if not username or not password:
                flash("Both fields are required")
                return redirect(url_for('signup'))

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
        
        try:
            # Get books from database
            dbp = os.path.join(app.instance_path, 'books.db')
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row

            # Get filter parameters
            category = request.args.get('category')
            search = request.args.get('search')
            
            query = "SELECT * FROM books WHERE 1=1"
            params = []
            
            if category:
                query += " AND category = ?"
                params.append(category)
                
            if search:
                query += " AND (title LIKE ? OR author LIKE ? OR description LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
                
            query += " ORDER BY title"

            cur = conn.cursor()
            cur.execute(query, params)
            books = [dict(row) for row in cur.fetchall()]
            
            # Get unique categories for filter dropdown
            cur.execute("SELECT DISTINCT category FROM books ORDER BY category")
            categories = [row[0] for row in cur.fetchall()]
            
            conn.close()

            # Resolve image path under /static for each book
            static_root = app.static_folder
            for b in books:
                img = (b.get('image') or '').strip()
                b['image_static'] = None
                if img:
                    candidates = [img] if '/' in img else [img, f'images/books/{img}', f'images/{img}']
                    for cand in candidates:
                        if os.path.exists(os.path.join(static_root, cand)):
                            b['image_static'] = cand
                            break
            
            return render_template('books.html', books=books, categories=categories, 
                                 selected_category=category, search_term=search)
            
        except Exception as e:
            return f"Database error: {str(e)}", 500

    @app.route('/video_games')  # Changed from /video-games to /video_games
    def video_games():
        if 'user' not in session:
            return redirect(url_for('login'))
        
        try:
            # Get games from database
            dbp = os.path.join(app.instance_path, 'games.db')
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row

            # Check if games table exists, if not create it
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='games'")
            if not cur.fetchone():
                # Table doesn't exist, create and seed it
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS games (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT,
                        category TEXT,
                        buy_price REAL DEFAULT 0,
                        rent_price REAL DEFAULT 0,
                        image TEXT
                    )
                """)
                
                # Seed with sample data
                sample_games = [
                    ("Baldur's Gate 3", "Epic CRPG adventure with deep choices and co-op.", "RPG,Co-op", 59.99, 9.99, "Baldurs_Gate_3.jpeg"),
                    ("Alan Wake 2", "Psychological horror thriller with cinematic storytelling.", "Horror,Narrative", 49.99, 7.99, "Alan_Wake_2.jpeg"),
                    ("Cyberpunk 2077", "Open-world RPG in a neon-soaked metropolis.", "RPG,Open-World", 29.99, 6.99, "cyberpunk.jpeg"),
                    ("Red Dead Redemption 2", "Open-world western with cinematic storytelling.", "Open-World,Action", 39.99, 8.99, "red.jpeg"),
                    ("The Witcher 3", "Open-world RPG full of monsters and choices.", "RPG,Open-World", 29.99, 6.49, "witcher.jpeg"),
                    ("Disco Elysium", "A groundbreaking RPG focused on choice and investigation.", "Indie,RPG", 19.99, 4.49, "Disco.jpeg"),
                    ("Silent Hill 2 (Remake)", "Reimagined survival-horror classic.", "Horror,Survival", 39.99, 8.49, "hill.jpeg"),
                    ("God of War", "A mythic reimagining: father, son, and monsters.", "Action,Adventure", 29.99, 6.99, "god.jpeg")
                ]
                
                cur.executemany("""
                    INSERT INTO games (title, description, category, buy_price, rent_price, image) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, sample_games)
                conn.commit()
                
            # Query games
            cur.execute("SELECT * FROM games ORDER BY id")
            games = [dict(row) for row in cur.fetchall()]
            conn.close()
            
            return render_template('video_games.html', games=games)
            
        except Exception as e:
            return f"Database error: {str(e)}", 500

    @app.route('/cafe')
    def cafe():
        if 'user' not in session:
            return redirect(url_for('login'))
        return render_template('cafe.html')

    @app.route('/cart')
    def cart():
        if 'user' not in session:
            return redirect(url_for('login'))
        items = session.get('cart', {}).get('items', [])
        subtotal = sum((i.get('unit_price', 0) * i.get('quantity', 1)) for i in items)
        return render_template('cart.html', items=items, subtotal=round(subtotal, 2))

    # ---------------- Blueprints ----------------
    app.register_blueprint(games_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)

    # init auth DB after app exists
    init_auth_db(app)

    # Enforce login for restricted paths
    RESTRICTED_PREFIXES = (
        '/books', '/video_games', '/purchase', '/rent', '/checkout',
        '/cart', '/api/purchase', '/api/books'
    )

    @app.before_request
    def require_login_for_restricted():
        path = request.path or '/'
        if any(path.startswith(p) for p in RESTRICTED_PREFIXES):
            if not session.get('user'):
                return redirect(url_for('login'))

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
