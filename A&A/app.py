import os
import sqlite3
import io
import csv
import json
import random
import urllib.request
import urllib.error
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, ConstellationChat, ConstellationMessage, IdeaMessage, ConstellationNode, IdeaNode, ConstellationEdge, IdeaEdge

from sqlalchemy import text, func

try:
    from flask_cors import CORS
except ImportError:
    CORS = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING
    from pymongo.errors import PyMongoError
except ImportError:
    MongoClient = None
    ASCENDING = 1
    DESCENDING = -1
    PyMongoError = Exception

try:
    import cloudinary
    import cloudinary.uploader
    _CLOUDINARY_AVAILABLE = True
except ImportError:
    _CLOUDINARY_AVAILABLE = False

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
    # Allow overriding the instance path (useful when mounting a persistent
    # volume on PaaS providers like Render). Set the env var INSTANCE_PATH to
    # a writable persistent mount (e.g. /mnt/instance) so SQLite files survive
    # across deploys.
    inst_override = os.environ.get('INSTANCE_PATH')
    
    # Vercel Serverless Functions have a Read-Only filesystem except for /tmp
    if os.environ.get('VERCEL') == '1':
        inst_override = '/tmp'
        
    if inst_override:
        # normalize and ensure directory exists
        inst_override = os.path.abspath(inst_override)
        os.makedirs(inst_override, exist_ok=True)
        app.instance_path = inst_override
    else:
        try:
            os.makedirs(app.instance_path, exist_ok=True)
        except OSError:
            pass

    app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    
    database_url = (os.getenv('DATABASE_URL') or '').strip()
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database_url.startswith('postgresql://') and '+psycopg' not in database_url.split('://', 1)[0]:
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

    if database_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Safely construct absolute URI for SQLAlchemy
        db_path = os.path.join(app.instance_path, 'users.db').replace('\\', '/')
        # If absolute path starts with / (like /tmp), we need an extra slash
        uri_prefix = 'sqlite:////' if db_path.startswith('/') else 'sqlite:///'
        app.config['SQLALCHEMY_DATABASE_URI'] = uri_prefix + db_path.lstrip('/')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Initialize CORS for cross-device WiFi support
    if CORS is not None:
        CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ---- Currency helpers ----
    @app.template_filter('inr')
    def inr_filter(value):
        """Convert a numeric USD value to INR using USD_TO_INR env (default 83)."""
        try:
            rate = float(os.getenv('USD_TO_INR', '83'))
            amt = float(value or 0) * rate
            return f"₹{amt:,.2f}"
        except Exception:
            try:
                return f"₹{float(value):,.2f}"
            except Exception:
                return "₹0.00"

    @app.context_processor
    def inject_currency():
        return {
            'currency_symbol': '₹',
            'usd_to_inr_rate': float(os.getenv('USD_TO_INR', '83'))
        }

    def _generate_user_tag():
        for _ in range(10000):
            tag = f"{random.randint(0, 9999):04d}"
            if not User.query.filter_by(user_tag=tag).first():
                return tag
        raise RuntimeError('No user tags available')

    def _ensure_user_tag(user):
        if user and not getattr(user, 'user_tag', None):
            user.user_tag = _generate_user_tag()
            db.session.commit()
        return getattr(user, 'user_tag', None) if user else None

    def _mongo_configured():
        return bool((os.getenv('MONGODB_URI') or '').strip()) and MongoClient is not None

    def _mongo_enabled():
        return _mongo_configured()

    def _mongo_available():
        if os.environ.get('VERCEL') == '1' and _mongo_configured():
            return True
        return _mongo_db() is not None

    def _mongo_db():
        if not _mongo_enabled():
            return None
        if not hasattr(app, 'mongo_client'):
            try:
                app.mongo_client = MongoClient((os.getenv('MONGODB_URI') or '').strip(), serverSelectionTimeoutMS=5000)
                app.mongo_client.admin.command('ping')
                app.mongo_db = app.mongo_client[(os.getenv('MONGODB_DB') or 'arcade').strip() or 'arcade']
                _ensure_mongo_indexes(app.mongo_db)
            except Exception as exc:
                if hasattr(app, 'mongo_client'):
                    delattr(app, 'mongo_client')
                if hasattr(app, 'mongo_db'):
                    delattr(app, 'mongo_db')
                app.logger.warning("MongoDB connection unavailable; falling back to local storage: %s", exc)
                return None
        return app.mongo_db

    def _ensure_mongo_indexes(mdb):
        mdb.users.create_index([('handle_lc', ASCENDING)], unique=True)
        mdb.users.create_index([('username_lc', ASCENDING)], unique=True)
        mdb.friend_requests.create_index([('pair_key', ASCENDING)], unique=True)
        mdb.friend_requests.create_index([('receiver_key', ASCENDING), ('status', ASCENDING)])
        mdb.chats.create_index([('chat_id', ASCENDING)], unique=True)
        mdb.chats.create_index([('participants', ASCENDING)])
        mdb.messages.create_index([('chat_id', ASCENDING), ('created_at', ASCENDING)])
        mdb.idea_messages.create_index([('chat_id', ASCENDING), ('created_at', ASCENDING)])
        mdb.graph_nodes.create_index([('chat_id', ASCENDING), ('label_lc', ASCENDING), ('mode', ASCENDING)], unique=True)
        mdb.graph_edges.create_index([('chat_id', ASCENDING), ('source_label_lc', ASCENDING), ('target_label_lc', ASCENDING), ('mode', ASCENDING)], unique=True)

    def _cloudinary_configured():
        """Return True if Cloudinary credentials are available (via CLOUDINARY_URL or individual vars)."""
        if not _CLOUDINARY_AVAILABLE:
            return False
        cloud_url = (os.getenv('CLOUDINARY_URL') or '').strip()
        if cloud_url:
            return True
        # Individual vars
        return bool(os.getenv('CLOUDINARY_CLOUD_NAME') and os.getenv('CLOUDINARY_API_KEY') and os.getenv('CLOUDINARY_API_SECRET'))

    def _cloudinary_upload(file_obj, folder='constellation', resource_type='auto'):
        """Upload a file-like object to Cloudinary and return (secure_url, error)."""
        if not _CLOUDINARY_AVAILABLE:
            return None, 'Cloudinary package not installed'
        cloud_url = (os.getenv('CLOUDINARY_URL') or '').strip()
        if cloud_url:
            cloudinary.config(cloudinary_url=cloud_url)
        else:
            cloudinary.config(
                cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', ''),
                api_key=os.getenv('CLOUDINARY_API_KEY', ''),
                api_secret=os.getenv('CLOUDINARY_API_SECRET', ''),
                secure=True
            )
        try:
            # Read bytes from the file object so Cloudinary receives a bytes buffer
            import io
            file_bytes = file_obj.read()
            result = cloudinary.uploader.upload(
                io.BytesIO(file_bytes),
                folder=folder,
                resource_type=resource_type,
                use_filename=True,
                unique_filename=True
            )
            return result.get('secure_url'), None
        except Exception as exc:
            return None, str(exc)

    def _mongo_key(username):
        return (username or '').strip().lower()

    def _mongo_pair_key(a, b):
        return '|'.join(sorted([_mongo_key(a), _mongo_key(b)]))

    def _mongo_chat_id(a, b):
        return _mongo_pair_key(a, b)

    def _mongo_current_user():
        if not _mongo_enabled():
            return None
        username = (session.get('user') or session.get('username') or '').strip()
        if not username:
            return None
        user = db.session.get(User, int(session.get('user_id') or 0)) if session.get('user_id') else None
        tag = session.get('user_tag') or (getattr(user, 'user_tag', None) if user else None)
        if user and not tag:
            tag = _ensure_user_tag(user)
        if not tag:
            tag = f"{random.randint(0, 9999):04d}"
            session['user_tag'] = tag
        handle = f"{username}#{tag}"
        doc = {
            '_id': _mongo_key(username),
            'username': username,
            'username_lc': _mongo_key(username),
            'user_tag': tag,
            'handle': handle,
            'handle_lc': handle.lower(),
            'display_name': getattr(user, 'display_name', None) or username,
            'photo_path': getattr(user, 'photo_path', None),
        }
        mdb = _mongo_db()
        if mdb is None:
            return None
        mdb.users.update_one({'_id': doc['_id']}, {'$set': doc}, upsert=True)
        return doc

    def _mongo_public_user(doc):
        if not doc:
            return None
        return {
            'id': doc['_id'],
            'username': doc.get('username'),
            'user_tag': doc.get('user_tag'),
            'handle': doc.get('handle'),
            'display_name': doc.get('display_name') or doc.get('username'),
            'photo_path': doc.get('photo_path')
        }

    def _mongo_find_user_by_handle(handle):
        handle = (handle or '').strip()
        if handle.startswith('@'):
            handle = handle[1:].strip()
        mdb = _mongo_db()
        if mdb is None:
            return None
        return mdb.users.find_one({'handle_lc': handle.lower()})

    def _mongo_are_friends(a, b):
        mdb = _mongo_db()
        if mdb is None:
            return False
        req = mdb.friend_requests.find_one({'pair_key': _mongo_pair_key(a, b), 'status': 'accepted'})
        return bool(req)

    def _mongo_upsert_graph(mode, chat_id, labels, edges):
        mdb = _mongo_db()
        for label in _dedupe_labels(labels, max_items=10):
            mdb.graph_nodes.update_one(
                {'chat_id': chat_id, 'mode': mode, 'label_lc': label.lower()},
                {'$setOnInsert': {'chat_id': chat_id, 'mode': mode, 'label': label, 'node_type': 'idea' if mode == 'ideas' else 'topic'},
                 '$inc': {'mention_count': 1}},
                upsert=True
            )
        for src, tgt in edges:
            src, tgt = _clean_graph_label(src), _clean_graph_label(tgt)
            if not src or not tgt or src.lower() == tgt.lower():
                continue
            a, b = sorted([src, tgt], key=str.lower)
            mdb.graph_edges.update_one(
                {'chat_id': chat_id, 'mode': mode, 'source_label_lc': a.lower(), 'target_label_lc': b.lower()},
                {'$setOnInsert': {'chat_id': chat_id, 'mode': mode, 'source_label': a, 'target_label': b},
                 '$inc': {'weight': 1}},
                upsert=True
            )

    def _mongo_graph(mode, chat_id):
        mdb = _mongo_db()
        nodes = list(mdb.graph_nodes.find({'chat_id': chat_id, 'mode': mode}).sort('mention_count', DESCENDING))
        label_to_id = {}
        out_nodes = []
        for i, n in enumerate(nodes, start=1):
            node_id = n.get('label_lc')
            label_to_id[node_id] = node_id
            out_nodes.append({
                'id': node_id,
                'label': n.get('label'),
                'node_type': n.get('node_type', 'idea' if mode == 'ideas' else 'topic'),
                'mention_count': n.get('mention_count', 1)
            })
        out_edges = []
        for e in mdb.graph_edges.find({'chat_id': chat_id, 'mode': mode}):
            src = e.get('source_label_lc')
            tgt = e.get('target_label_lc')
            if src in label_to_id and tgt in label_to_id:
                out_edges.append({'source_node_id': src, 'target_node_id': tgt, 'weight': e.get('weight', 1)})
        return {'nodes': out_nodes, 'edges': out_edges}

    @app.before_request
    def create_tables():
        if not hasattr(app, 'db_initialized'):
            db.create_all()
            init_books_db()  # Initialize books database
            # Self-heal User table to ensure profile columns exist
            try:
                with db.engine.begin() as conn:
                    user_table = User.__tablename__
                    quoted_user_table = '"' + user_table.replace('"', '""') + '"'
                    cols = [row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info({quoted_user_table})').fetchall()]
                    if 'display_name' not in cols:
                        conn.exec_driver_sql(f'ALTER TABLE {quoted_user_table} ADD COLUMN display_name VARCHAR(120)')
                    if 'photo_path' not in cols:
                        conn.exec_driver_sql(f'ALTER TABLE {quoted_user_table} ADD COLUMN photo_path VARCHAR(255)')
                    if 'user_tag' not in cols:
                        conn.exec_driver_sql(f'ALTER TABLE {quoted_user_table} ADD COLUMN user_tag VARCHAR(4)')
                    if 'email' not in cols:
                        conn.exec_driver_sql(f'ALTER TABLE {quoted_user_table} ADD COLUMN email VARCHAR(255)')
            except Exception:
                pass
            try:
                for user in User.query.filter((User.user_tag == None) | (User.user_tag == '')).all():
                    user.user_tag = _generate_user_tag()
                db.session.commit()
            except Exception:
                db.session.rollback()
            # Ensure a default admin user exists for demo access
            try:
                from sqlalchemy.exc import SQLAlchemyError
                if not User.query.filter_by(username='admin').first():
                    admin_pw = os.getenv('ADMIN_DEFAULT_PASSWORD', 'admin123')
                    admin_user = User(username='admin', password_hash=generate_password_hash(admin_pw), user_tag=_generate_user_tag())
                    db.session.add(admin_user)
                    db.session.commit()
            except Exception:
                # Do not block app startup if seeding fails
                pass
            app.db_initialized = True

    @app.context_processor
    def inject_cart_count():
        items = session.get('cart', {}).get('items', [])
        return {'cart_count': sum(i.get('quantity', 1) for i in items)}

    # ---------- Community (simple subscriber + updates) ----------
    def _community_db_path():
        os.makedirs(app.instance_path, exist_ok=True)
        return os.path.join(app.instance_path, 'community.db')

    def _ensure_community_tables(conn):
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS community_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT UNIQUE NOT NULL,
                joined_at TEXT NOT NULL,
                display_name TEXT,
                photo_path TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS community_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                author TEXT,
                content TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        # add missing columns safely
        try:
            cur.execute("PRAGMA table_info(community_subscribers)")
            cols = {r[1] for r in cur.fetchall()}
            if 'user_id' not in cols:
                cur.execute("ALTER TABLE community_subscribers ADD COLUMN user_id INTEGER")
            if 'display_name' not in cols:
                cur.execute("ALTER TABLE community_subscribers ADD COLUMN display_name TEXT")
            if 'photo_path' not in cols:
                cur.execute("ALTER TABLE community_subscribers ADD COLUMN photo_path TEXT")
            conn.commit()
        except Exception:
            pass

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

    @app.route('/api/network-status')
    def network_status():
        """Network diagnostics endpoint for cross-device connectivity testing"""
        import socket
        try:
            hostname = socket.gethostname()
            ip_addr = socket.gethostbyname(hostname)
            client_ip = request.remote_addr
            return jsonify({
                'status': 'online',
                'server': {
                    'hostname': hostname,
                    'ip': ip_addr,
                    'port': 5000,
                    'urls': {
                        'local': 'http://127.0.0.1:5000',
                        'network': f'http://{ip_addr}:5000'
                    }
                },
                'client': {
                    'ip': client_ip,
                    'user_agent': request.headers.get('User-Agent', 'Unknown')
                },
                'same_network': client_ip.startswith(ip_addr.rsplit('.', 1)[0]) if '.' in ip_addr and '.' in client_ip else False,
                'timestamp': str(__import__('datetime').datetime.now().isoformat())
            })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e),
                'client_ip': request.remote_addr
            }), 500

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = (request.form.get('ident') or '').strip()
            password = request.form.get('password')
            if not username or not password:
                flash("Please enter both username and password")
                return redirect(url_for('login'))

            user = User.query.filter((User.username == username) | (User.email == username.lower())).first()
            if user and check_password_hash(user.password_hash, password):
                _ensure_user_tag(user)
                session['user'] = user.username
                session['user_id'] = user.id  # Add user_id to match auth.py
                session['user_tag'] = user.user_tag
                if _mongo_available():
                    _mongo_current_user()
                # If a community email is present from a prior join, link it to this account
                try:
                    cem = (session.get('community_email') or '').strip().lower()
                    if cem:
                        dbp = _community_db_path()
                        conn = sqlite3.connect(dbp)
                        _ensure_community_tables(conn)
                        cur = conn.cursor()
                        cur.execute("UPDATE community_subscribers SET user_id=? WHERE email=?", (int(user.id), cem))
                        conn.commit(); conn.close()
                except Exception:
                    pass
                return redirect(url_for('home'))
            else:
                flash('Invalid username or password')
        return render_template('login.html')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            username = (request.form.get('username') or '').strip()
            email = (request.form.get('email') or '').strip().lower()
            password = request.form.get('password')
            if not username or not email or not password:
                flash("Username, email and password are required")
                return redirect(url_for('signup'))

            if User.query.filter_by(username=username).first():
                flash('Username already exists')
            elif User.query.filter_by(email=email).first():
                flash('Email already exists')
            else:
                hashed_pw = generate_password_hash(password)
                new_user = User(username=username, email=email, password_hash=hashed_pw, user_tag=_generate_user_tag())
                db.session.add(new_user)
                db.session.commit()
                # Reset and set session identity to the new user
                session.pop('user', None)
                session.pop('user_id', None)
                session['user'] = username
                session['user_id'] = new_user.id
                session['user_tag'] = new_user.user_tag
                if _mongo_available():
                    _mongo_current_user()
                # Link existing community email (if any in session) to new account
                try:
                    cem = (session.get('community_email') or '').strip().lower()
                    if cem:
                        dbp = _community_db_path()
                        conn = sqlite3.connect(dbp)
                        _ensure_community_tables(conn)
                        cur = conn.cursor()
                        cur.execute("UPDATE community_subscribers SET user_id=? WHERE email=?", (int(new_user.id), cem))
                        conn.commit(); conn.close()
                except Exception:
                    pass
                return redirect(url_for('home'))
        return render_template('signup.html')

    @app.route('/logout')
    def logout():
        # Clear all identity and cart data to avoid cross-user leakage
        session.pop('user', None)
        session.pop('username', None)
        session.pop('user_id', None)
        session.pop('user_tag', None)
        session.pop('cart', None)
        session.pop('community_email', None)
        return redirect(url_for('index'))

    @app.route('/books')
    def books():
        if 'user' not in session and 'user_id' not in session:
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
                    # Try a few common locations inside static
                    candidates = [img] if '/' in img else [
                        img,
                        f'images/books/{img}',
                        f'images/{img}'
                    ]
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
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        
        try:
            # Get games from database
            dbp = os.path.join(app.instance_path, 'games.db')
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row

            # Check if games table exists, if not create it
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='games'")
            # Shared seed data
            sample_games = [
                ("Baldur's Gate 3", "Epic CRPG adventure with deep choices and co-op.", "RPG,Co-op", 59.99, 9.99, "images/games/Baldurs_Gate_3.jpeg"),
                ("Alan Wake 2", "Psychological horror thriller with cinematic storytelling.", "Horror,Narrative", 49.99, 7.99, "images/games/Alan_Wake_2.jpeg"),
                ("Cyberpunk 2077", "Open-world RPG in a neon-soaked metropolis.", "RPG,Open-World", 29.99, 6.99, "images/games/cyberpunk.jpeg"),
                ("Red Dead Redemption 2", "Open-world western with cinematic storytelling.", "Open-World,Action", 39.99, 8.99, "images/games/red.jpeg"),
                ("The Witcher 3", "Open-world RPG full of monsters and choices.", "RPG,Open-World", 29.99, 6.49, "images/games/witcher.jpeg"),
                ("Disco Elysium", "A groundbreaking RPG focused on choice and investigation.", "Indie,RPG", 19.99, 4.49, "images/games/Disco.jpeg"),
                ("Silent Hill 2 (Remake)", "Reimagined survival-horror classic.", "Horror,Survival", 39.99, 8.49, "images/games/hill.jpeg"),
                ("God of War", "A mythic reimagining: father, son, and monsters.", "Action,Adventure", 29.99, 6.99, "images/games/god.jpeg")
            ]
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
                cur.executemany("""
                    INSERT INTO games (title, description, category, buy_price, rent_price, image) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, sample_games)
                conn.commit()
            else:
                # Table exists but may be empty (e.g., after a reset) -> seed if empty
                cur.execute("SELECT COUNT(*) FROM games")
                if int(cur.fetchone()[0] or 0) == 0:
                    cur.executemany("""
                        INSERT INTO games (title, description, category, buy_price, rent_price, image)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, sample_games)
                    conn.commit()
                
            # Optional filters
            category = request.args.get('category', '').strip()
            search = request.args.get('search', '').strip()

            # Build filtered query
            query = "SELECT * FROM games WHERE 1=1"
            params = []
            if category:
                query += " AND category LIKE ?"
                params.append(f"%{category}%")
            if search:
                query += " AND (title LIKE ? OR description LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"]) 
            query += " ORDER BY id"

            cur.execute(query, params)
            games = [dict(row) for row in cur.fetchall()]

            # Build distinct category list (split comma-separated tags)
            cur.execute("SELECT category FROM games")
            cats = set()
            for (cat_str,) in cur.fetchall():
                if not cat_str:
                    continue
                for token in str(cat_str).split(','):
                    token = token.strip()
                    if token:
                        cats.add(token)
            categories = sorted(cats)

            # Resolve image path under /static for each game
            static_root = app.static_folder
            for g in games:
                img = (g.get('image') or '').strip()
                g['image_static'] = None
                if img:
                    candidates = [img] if '/' in img else [
                        img,
                        f'images/games/{img}',
                        f'images/{img}'
                    ]
                    for cand in candidates:
                        if os.path.exists(os.path.join(static_root, cand)):
                            g['image_static'] = cand
                            break
            conn.close()
            return render_template('video_games.html', games=games, categories=categories)
            
        except Exception as e:
            return f"Database error: {str(e)}", 500

    # Convenience redirect for old URL style
    @app.route('/video-games')
    def video_games_legacy_redirect():
        return redirect(url_for('video_games'))

    @app.route('/admin/seed/games')
    def admin_seed_games():
        # Admin-only helper to (re)seed the games catalog on demand
        if not (session.get('user') or session.get('user_id')):
            return redirect(url_for('login'))
        if not _is_admin():
            return "Forbidden: Admins only", 403
        force = (request.args.get('force') or '').strip().lower() in ('1', 'true', 'yes')
        try:
            dbp = os.path.join(app.instance_path, 'games.db')
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Ensure table exists
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
            # Check current count
            cur.execute("SELECT COUNT(*) FROM games")
            count = int(cur.fetchone()[0] or 0)
            if count == 0 or force:
                # Clear existing if forcing
                if force:
                    cur.execute("DELETE FROM games")
                sample_games = [
                    ("Baldur's Gate 3", "Epic CRPG adventure with deep choices and co-op.", "RPG,Co-op", 59.99, 9.99, "images/games/Baldurs_Gate_3.jpeg"),
                    ("Alan Wake 2", "Psychological horror thriller with cinematic storytelling.", "Horror,Narrative", 49.99, 7.99, "images/games/Alan_Wake_2.jpeg"),
                    ("Cyberpunk 2077", "Open-world RPG in a neon-soaked metropolis.", "RPG,Open-World", 29.99, 6.99, "images/games/cyberpunk.jpeg"),
                    ("Red Dead Redemption 2", "Open-world western with cinematic storytelling.", "Open-World,Action", 39.99, 8.99, "images/games/red.jpeg"),
                    ("The Witcher 3", "Open-world RPG full of monsters and choices.", "RPG,Open-World", 29.99, 6.49, "images/games/witcher.jpeg"),
                    ("Disco Elysium", "A groundbreaking RPG focused on choice and investigation.", "Indie,RPG", 19.99, 4.49, "images/games/Disco.jpeg"),
                    ("Silent Hill 2 (Remake)", "Reimagined survival-horror classic.", "Horror,Survival", 39.99, 8.49, "images/games/hill.jpeg"),
                    ("God of War", "A mythic reimagining: father, son, and monsters.", "Action,Adventure", 29.99, 6.99, "images/games/god.jpeg")
                ]
                cur.executemany(
                    """
                    INSERT INTO games (title, description, category, buy_price, rent_price, image)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    sample_games
                )
                conn.commit()
                msg = f"Seeded {len(sample_games)} games (force={force})."
            else:
                msg = f"Games table already has {count} entries. Use ?force=1 to replace."
            conn.close()
            return msg
        except Exception as e:
            return f"Seeding error: {e}", 500

    @app.route('/cafe')
    def cafe():
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        return render_template('cafe.html')

    @app.route('/api/cafe/availability')
    def cafe_availability():
        """
        Demo availability API for the Cafe.
        Rules (demo):
          - Sundays (weekday=6): Fully sold out (no access).
          - Saturdays (weekday=5): Members-only esports event day (sold out for general, members allowed).
          - Other days: Available.
        Request: /api/cafe/availability?date=YYYY-MM-DD
        """
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        dstr = (request.args.get('date') or '').strip()
        from datetime import datetime as _dt
        try:
            day = _dt.strptime(dstr, '%Y-%m-%d').date()
        except Exception:
            return jsonify({'error': 'Invalid or missing date (use YYYY-MM-DD)'}), 400

        wd = day.weekday()  # Monday=0 ... Sunday=6
        if wd == 6:
            return jsonify({
                'date': dstr,
                'status': 'sold_out',
                'sold_out_general': True,
                'members_allowed': False,
                'note': 'Fully booked (closed to all reservations)'
            })
        if wd == 5:
            return jsonify({
                'date': dstr,
                'status': 'members_only',
                'sold_out_general': True,
                'members_allowed': True,
                'note': 'Members-only esports event day'
            })
        return jsonify({
            'date': dstr,
            'status': 'available',
            'sold_out_general': False,
            'members_allowed': True,
            'note': 'Available for bookings'
        })

    # ---- Cafe Booking (individual) ----
    def _cafe_db_path():
        os.makedirs(app.instance_path, exist_ok=True)
        return os.path.join(app.instance_path, 'cafe.db')

    def _ensure_cafe_tables(conn):
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cafe_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                party_size INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 60,
                canceled_at TEXT
            )
            """
        )
        # Add missing columns safely
        cur.execute("PRAGMA table_info(cafe_bookings)")
        cols = {r[1] for r in cur.fetchall()}
        if 'duration_minutes' not in cols:
            cur.execute("ALTER TABLE cafe_bookings ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 60")
        if 'canceled_at' not in cols:
            cur.execute("ALTER TABLE cafe_bookings ADD COLUMN canceled_at TEXT")
        conn.commit()
        # Index to speed up overlap checks
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cafe_date_time_status ON cafe_bookings(date, time, status)")
        except Exception:
            pass
        conn.commit()

    def _slot_capacity():
        try:
            cap = int(os.getenv('CAFE_SLOT_CAPACITY', '10'))
            return max(1, cap)
        except Exception:
            return 10

    def _parse_time_to_min(tstr: str) -> int:
        try:
            h, m = (tstr or '00:00').split(':')
            return int(h) * 60 + int(m)
        except Exception:
            return 0

    def _minutes_to_time(m: int) -> str:
        m = int(m) % (24*60)
        return f"{m//60:02d}:{m%60:02d}"

    def _overlaps(start_a: int, dur_a: int, start_b: int, dur_b: int) -> bool:
        end_a = start_a + dur_a
        end_b = start_b + dur_b
        return start_a < end_b and start_b < end_a

    def _sum_booked_seats(conn, date: str, start_min: int, duration_min: int) -> int:
        cur = conn.cursor()
        cur.execute(
            "SELECT time, duration_minutes, party_size FROM cafe_bookings WHERE date=? AND status='confirmed'",
            (date,)
        )
        total = 0
        for t, d, p in cur.fetchall():
            if _overlaps(start_min, duration_min, _parse_time_to_min(t), int(d or 60)):
                total += int(p or 0)
        return total

    def _is_members_only(date_str: str) -> bool:
        from datetime import datetime as _dt
        try:
            day = _dt.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return False
        wd = day.weekday()
        return wd == 5  # Saturday

    def _is_closed(date_str: str) -> bool:
        from datetime import datetime as _dt
        try:
            day = _dt.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return False
        wd = day.weekday()
        return wd == 6  # Sunday

    @app.route('/api/cafe/slots')
    def cafe_slots():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        date = (request.args.get('date') or '').strip()
        try:
            _ = date and len(date) == 10
        except Exception:
            return jsonify({'error': 'Invalid or missing date'}), 400
        # Closed or members-only days
        if _is_closed(date):
            return jsonify({'date': date, 'closed': True, 'members_only': False, 'slots': []})
        if _is_members_only(date):
            return jsonify({'date': date, 'closed': False, 'members_only': True, 'slots': []})

        # Build slots from open/close times
        open_time = os.getenv('CAFE_OPEN', '10:00')
        close_time = os.getenv('CAFE_CLOSE', '22:00')
        step_min = int(os.getenv('CAFE_SLOT_STEP_MIN', '60'))
        default_dur = int(os.getenv('CAFE_DEFAULT_DURATION', '60'))
        cap = _slot_capacity()
        start_min = _parse_time_to_min(open_time)
        end_min = _parse_time_to_min(close_time)
        slots = []
        try:
            dbp = _cafe_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_cafe_tables(conn)
            cur = conn.cursor()
            m = start_min
            while m + default_dur <= end_min:
                used = _sum_booked_seats(conn, date, m, default_dur)
                remain = max(0, cap - used)
                slots.append({'time': _minutes_to_time(m), 'remaining': remain})
                m += step_min
            conn.close()
        except Exception as e:
            return jsonify({'error': f'Failed to load slots: {e}'}), 500
        return jsonify({'date': date, 'closed': False, 'members_only': False, 'capacity': cap, 'duration': default_dur, 'slots': slots})

    @app.route('/api/cafe/book', methods=['POST'])
    def cafe_book():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json(silent=True) or {}
        date = (data.get('date') or '').strip()
        time = (data.get('time') or '').strip()
        party_size = int(data.get('partySize') or 1)
        duration_min = int(data.get('duration') or os.getenv('CAFE_DEFAULT_DURATION', '60'))
        note = (data.get('note') or '').strip()

        if not date or not time:
            return jsonify({'error': 'date and time are required'}), 400
        if party_size < 1:
            return jsonify({'error': 'partySize must be >= 1'}), 400
        if duration_min < 30 or duration_min > 240:
            return jsonify({'error': 'duration must be between 30 and 240 minutes'}), 400

        # Enforce day rules
        if _is_closed(date):
            return jsonify({'error': 'Selected day is fully booked'}), 400
        if _is_members_only(date):
            return jsonify({'error': 'Members-only esports event day'}), 403

        # Capacity check + Save booking atomically
        from datetime import datetime as _dt
        try:
            dbp = _cafe_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_cafe_tables(conn)
            cur = conn.cursor()
            # Check overlap usage
            start_min = _parse_time_to_min(time)
            used = _sum_booked_seats(conn, date, start_min, duration_min)
            cap = _slot_capacity()
            if used + party_size > cap:
                remaining = max(0, cap - used)
                conn.close()
                return jsonify({'error': f'Not enough capacity in this slot', 'remaining': remaining, 'capacity': cap}), 409
            # Save
            cur.execute(
                """
                INSERT INTO cafe_bookings (user_id, date, time, party_size, note, status, created_at, duration_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(session.get('user_id') or 0),
                    date,
                    time,
                    party_size,
                    note,
                    'confirmed',
                    _dt.utcnow().isoformat(),
                    duration_min
                )
            )
            conn.commit()
            bid = cur.lastrowid
            conn.close()
            return jsonify({'success': True, 'booking_id': bid, 'status': 'confirmed'})
        except Exception as e:
            return jsonify({'error': f'Failed to save booking: {e}'}), 500

    @app.route('/api/cafe/bookings', methods=['GET'])
    def cafe_my_bookings():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            dbp = _cafe_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_cafe_tables(conn)
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM cafe_bookings WHERE user_id = ? ORDER BY date DESC, time DESC",
                (int(session.get('user_id') or 0),)
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return jsonify(rows)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/cafe/bookings/<int:bid>', methods=['DELETE'])
    def cafe_cancel_booking(bid: int):
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            dbp = _cafe_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_cafe_tables(conn)
            cur = conn.cursor()
            # verify ownership and current status
            cur.execute("SELECT id, user_id, status FROM cafe_bookings WHERE id=?", (bid,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return jsonify({'error': 'Booking not found'}), 404
            if int(row['user_id']) != int(session.get('user_id') or 0):
                conn.close()
                return jsonify({'error': 'Forbidden'}), 403
            if row['status'] != 'confirmed':
                conn.close()
                return jsonify({'error': 'Booking is not active'}), 400
            from datetime import datetime as _dt
            cur.execute(
                "UPDATE cafe_bookings SET status='canceled', canceled_at=? WHERE id=?",
                (_dt.utcnow().isoformat(), bid)
            )
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/cart')
    def cart():
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        items = session.get('cart', {}).get('items', [])
        subtotal = sum((i.get('unit_price', 0) * i.get('quantity', 1)) for i in items)
        return render_template('cart.html', items=items, subtotal=round(subtotal, 2))

    @app.route('/checkout')
    def checkout_page():
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        items = session.get('cart', {}).get('items', [])
        subtotal = sum((i.get('unit_price', 0) * i.get('quantity', 1)) for i in items)
        return render_template('checkout.html', items=items, subtotal=round(subtotal, 2))

    @app.route('/history')
    def history_page():
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        # Render a page that loads history via API for current user
        return render_template('history.html')

    # -------------- Community routes --------------
    def _community_can_access():
        return bool(session.get('user') or session.get('user_id') or session.get('community_email'))

    @app.route('/community')
    def community_page():
        if not _community_can_access():
            # allow discoverability but suggest joining
            flash('Join the community with your email to access updates.')
            return redirect(url_for('index'))
        return render_template('community.html')

    @app.route('/community/join', methods=['POST'])
    def community_join():
        # Open to all; users can join by email without logging in
        email = (request.json.get('email') if request.is_json else request.form.get('email')) or ''
        email = email.strip().lower()
        if not email or '@' not in email or '.' not in email:
            return jsonify({'success': False, 'error': 'Please enter a valid email'}), 400
        from datetime import datetime as _dt
        try:
            dbp = _community_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_community_tables(conn)
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO community_subscribers(email, joined_at) VALUES(?, ?)", (email, _dt.utcnow().isoformat()))
            # Link to account if logged in
            uid = int(session.get('user_id') or 0)
            if uid:
                cur.execute("UPDATE community_subscribers SET user_id=? WHERE email=?", (uid, email))
            conn.commit()
            conn.close()
            session['community_email'] = email
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/community/messages', methods=['GET', 'POST'])
    def community_messages():
        if request.method == 'GET':
            # Public feed, but page access controls viewing UI
            try:
                dbp = _community_db_path()
                conn = sqlite3.connect(dbp)
                conn.row_factory = sqlite3.Row
                _ensure_community_tables(conn)
                cur = conn.cursor()
                cur.execute("SELECT id, author, content, is_admin, created_at FROM community_messages ORDER BY id DESC LIMIT 50")
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                return jsonify(rows)
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        # POST -> admin-only create message
        if not (session.get('user') or session.get('user_id')) or not _is_admin():
            return jsonify({'error': 'Admins only'}), 403
        data = request.get_json(silent=True) or {}
        content = (data.get('content') or '').strip()
        if not content:
            return jsonify({'error': 'Message cannot be empty'}), 400
        from datetime import datetime as _dt
        try:
            dbp = _community_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_community_tables(conn)
            cur = conn.cursor()
            author = session.get('user') or 'admin'
            cur.execute(
                """
                INSERT INTO community_messages(user_id, author, content, is_admin, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (int(session.get('user_id') or 0), author, content, 1, _dt.utcnow().isoformat())
            )
            conn.commit()
            mid = cur.lastrowid
            conn.close()
            return jsonify({'success': True, 'id': mid})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/community/subscribers', methods=['GET'])
    def community_subscribers():
        # List subscribers; obfuscate emails for non-admins
        is_admin_flag = False
        try:
            is_admin_flag = _is_admin()
        except Exception:
            is_admin_flag = False
        try:
            dbp = _community_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_community_tables(conn)
            cur = conn.cursor()
            cur.execute("SELECT id, email, joined_at, display_name, photo_path FROM community_subscribers ORDER BY id DESC LIMIT 200")
            rows = []
            for r in cur.fetchall():
                email = r['email'] or ''
                def _mask(e):
                    try:
                        name, dom = e.split('@', 1)
                        shown = name[:2]
                        return f"{shown}{'*'*(max(0,len(name)-2))}@{dom}"
                    except Exception:
                        return e
                masked = email if is_admin_flag else _mask(email)
                photo_url = None
                if r['photo_path']:
                    try:
                        photo_url = url_for('static', filename=r['photo_path'])
                    except Exception:
                        photo_url = None
                rows.append({
                    'id': r['id'],
                    'email': email if is_admin_flag else masked,
                    'display_name': r['display_name'] or '',
                    'joined_at': r['joined_at'] or '',
                    'photo_url': photo_url
                })
            conn.close()
            return jsonify(rows)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/community/profile', methods=['POST'])
    def community_profile():
        # Update subscriber profile (display_name, photo). Requires joined email in session.
        email = (session.get('community_email') or '').strip().lower()
        if not email:
            return jsonify({'success': False, 'error': 'Join the community with your email first from Home'}), 403
        display_name = (request.form.get('display_name') or '').strip()
        photo = request.files.get('photo')
        # Find or create subscriber row
        from datetime import datetime as _dt
        try:
            dbp = _community_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_community_tables(conn)
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO community_subscribers(email, joined_at) VALUES(?, ?)", (email, _dt.utcnow().isoformat()))
            conn.commit()
            cur.execute("SELECT id, photo_path FROM community_subscribers WHERE email=?", (email,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return jsonify({'success': False, 'error': 'Subscriber not found'}), 404
            sub_id = int(row['id'])
            photo_path = row['photo_path']

            # Handle upload if provided
            saved_rel_path = None
            if photo and getattr(photo, 'filename', ''):
                fname = secure_filename(photo.filename)
                ext = ''
                if '.' in fname:
                    ext = '.' + fname.rsplit('.', 1)[1].lower()
                if ext not in ('.png', '.jpg', '.jpeg', '.webp'):
                    conn.close()
                    return jsonify({'success': False, 'error': 'Only PNG, JPG, JPEG, WEBP allowed'}), 400
                # Save under static/uploads/community
                upload_dir = os.path.join(app.static_folder, 'uploads', 'community')
                os.makedirs(upload_dir, exist_ok=True)
                new_name = f"sub_{sub_id}{ext}"
                abs_path = os.path.join(upload_dir, new_name)
                photo.save(abs_path)
                saved_rel_path = os.path.join('uploads', 'community', new_name)

            # Apply updates to subscriber
            if display_name:
                cur.execute("UPDATE community_subscribers SET display_name=? WHERE id=?", (display_name, sub_id))
            if saved_rel_path:
                cur.execute("UPDATE community_subscribers SET photo_path=? WHERE id=?", (saved_rel_path, sub_id))
            conn.commit()
            # If logged in, also mirror to User profile
            uid = int(session.get('user_id') or 0)
            if uid:
                try:
                    user = User.query.get(uid)
                    if user:
                        if display_name:
                            user.display_name = display_name
                        if saved_rel_path:
                            user.photo_path = saved_rel_path
                        db.session.commit()
                except Exception:
                    db.session.rollback()
            conn.close()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/community/me', methods=['GET'])
    def community_me():
        email = (session.get('community_email') or '').strip().lower()
        if not email:
            return jsonify({'error': 'Not joined'}), 404
        try:
            dbp = _community_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_community_tables(conn)
            cur = conn.cursor()
            cur.execute("SELECT id, email, display_name, photo_path, joined_at FROM community_subscribers WHERE email=?", (email,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return jsonify({'error': 'Not found'}), 404
            photo_url = None
            if row['photo_path']:
                try:
                    photo_url = url_for('static', filename=row['photo_path'])
                except Exception:
                    photo_url = None
            return jsonify({
                'email': row['email'],
                'display_name': row['display_name'] or '',
                'joined_at': row['joined_at'] or '',
                'photo_url': photo_url
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/account/username', methods=['POST'])
    def account_change_username():
        # Logged-in users can change their account username
        uid = session.get('user_id')
        if not uid:
            return jsonify({'success': False, 'error': 'Login required'}), 401
        data = request.get_json(silent=True) or {}
        new_username = (data.get('username') or '').strip()
        if not new_username or len(new_username) < 3:
            return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400
        try:
            # Check availability
            if User.query.filter_by(username=new_username).first():
                return jsonify({'success': False, 'error': 'Username already taken'}), 409
            user = User.query.get(int(uid))
            if not user:
                return jsonify({'success': False, 'error': 'User not found'}), 404
            user.username = new_username
            db.session.commit()
            # Update session display name
            session['user'] = new_username
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

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
            if not session.get('user') and not session.get('user_id'):
                return redirect(url_for('login'))

    @app.context_processor
    def inject_admin_flag():
        # Provide a convenience flag to templates for showing admin-only UI
        try:
            return { 'is_admin': _is_admin() }
        except Exception:
            return { 'is_admin': False }

    @app.context_processor
    def inject_user_profile():
        # Provide current user's display name to templates if available
        try:
            uid = session.get('user_id')
            if uid:
                u = User.query.get(int(uid))
                if u and getattr(u, 'display_name', None):
                    return { 'user_display_name': u.display_name }
        except Exception:
            pass
        return { 'user_display_name': None }

    # ---------------- Admin Dashboard ----------------
    def _is_admin():
        # Simple demo admin check: username 'admin' or user_id == 1, or env ADMIN_USERS contains username
        uname = session.get('user') or session.get('username') or ''
        if uname.lower() == 'admin':
            return True
        if (session.get('user_id') or 0) == 1:
            return True
        admin_users = os.getenv('ADMIN_USERS', '')
        if admin_users:
            allowed = {u.strip().lower() for u in admin_users.split(',') if u.strip()}
            if uname.lower() in allowed:
                return True
        return False

    @app.route('/admin')
    def admin_dashboard():
        if not (session.get('user') or session.get('user_id')):
            return redirect(url_for('login'))
        if not _is_admin():
            return "Forbidden: Admins only", 403

        # Purchases summary (games.db)
        games_dbp = os.path.join(app.instance_path, 'games.db')
        purchases = []
        totals = { 'orders': 0, 'revenue': 0.0 }
        method_totals = {}
        daily_map = {}
        try:
            gconn = sqlite3.connect(games_dbp)
            gconn.row_factory = sqlite3.Row
            cur = gconn.cursor()
            cur.execute("SELECT COUNT(*) as c, IFNULL(SUM(total_amount),0) as s FROM purchase_history")
            row = cur.fetchone()
            if row:
                totals['orders'] = int(row['c'] or 0)
                totals['revenue'] = float(row['s'] or 0)
            cur.execute("SELECT * FROM purchase_history ORDER BY purchase_date DESC LIMIT 25")
            purchases = [dict(r) for r in cur.fetchall()]
            # Aggregate by method and by day from all rows (not only last 25)
            cur.execute("SELECT purchase_date, total_amount, COALESCE(payment_method, 'Demo') as pm FROM purchase_history")
            for r in cur.fetchall():
                amt = float(r['total_amount'] or 0)
                method = (r['pm'] or 'Demo').lower()
                mt = method_totals.setdefault(method, {'orders': 0, 'revenue': 0.0})
                mt['orders'] += 1
                mt['revenue'] += amt
                # derive date key
                pdate = r['purchase_date'] or ''
                if 'T' in pdate:
                    dkey = pdate.split('T', 1)[0]
                elif ' ' in pdate:
                    dkey = pdate.split(' ', 1)[0]
                else:
                    dkey = pdate[:10]
                dm = daily_map.setdefault(dkey, {'date': dkey, 'orders': 0, 'revenue': 0.0})
                dm['orders'] += 1
                dm['revenue'] += amt
            gconn.close()
        except Exception:
            purchases = []

        # Cafe bookings (cafe.db)
        cafe_dbp = os.path.join(app.instance_path, 'cafe.db')
        bookings = []
        try:
            cconn = sqlite3.connect(cafe_dbp)
            cconn.row_factory = sqlite3.Row
            cur = cconn.cursor()
            cur.execute("SELECT * FROM cafe_bookings ORDER BY date DESC, time DESC")
            bookings = [dict(r) for r in cur.fetchall()]
            cconn.close()
        except Exception:
            bookings = []

        # Derive simple members list from activity
        members = {}
        for p in purchases:
            uid = int(p.get('user_id') or 0)
            m = members.setdefault(uid, {'user_id': uid, 'orders': 0, 'spent': 0.0, 'bookings': 0})
            m['orders'] += 1
            try:
                m['spent'] += float(p.get('total_amount') or 0)
            except Exception:
                pass
        for b in bookings:
            uid = int(b.get('user_id') or 0)
            m = members.setdefault(uid, {'user_id': uid, 'orders': 0, 'spent': 0.0, 'bookings': 0})
            m['bookings'] += 1
        members_list = sorted(members.values(), key=lambda x: (-x['spent'], -x['orders']))[:50]

        # Build daily revenue list (last 30 days)
        daily_list = sorted(daily_map.values(), key=lambda x: x['date'], reverse=True)[:30]
        daily_list = list(reversed(daily_list))  # chronological order for display
        daily_max = max((d['revenue'] for d in daily_list), default=0.0)

        return render_template(
            'admin.html',
            totals=totals,
            purchases=purchases,
            bookings=bookings,
            members=members_list,
            method_totals=method_totals,
            daily_revenue=daily_list,
            daily_max=daily_max
        )

    @app.route('/admin/purchase/<int:pid>/delivery', methods=['POST'])
    def admin_update_delivery(pid: int):
        # Admin-only endpoint to update delivery status
        if not (session.get('user') or session.get('user_id')):
            return redirect(url_for('login'))
        if not _is_admin():
            return jsonify({'error': 'Admins only'}), 403
        data = request.get_json(silent=True) or {}
        status = (data.get('status') or '').strip()
        allowed = {
            'Processing', 'Out for delivery', 'Delivered'
        }
        # Accept lower-case shorthands
        m = {
            'processing': 'Processing',
            'out': 'Out for delivery',
            'out for delivery': 'Out for delivery',
            'delivered': 'Delivered',
            'successful': 'Delivered',
            'success': 'Delivered'
        }
        status_norm = m.get(status.lower(), status)
        if status_norm not in allowed:
            return jsonify({'error': 'Invalid status'}), 400
        try:
            dbp = os.path.join(app.instance_path, 'games.db')
            conn = sqlite3.connect(dbp)
            cur = conn.cursor()
            cur.execute("UPDATE purchase_history SET delivery_status=? WHERE id=?", (status_norm, pid))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'status': status_norm})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/admin/revenue.csv')
    def admin_revenue_csv():
        if not (session.get('user') or session.get('user_id')):
            return redirect(url_for('login'))
        if not _is_admin():
            return "Forbidden: Admins only", 403
        games_dbp = os.path.join(app.instance_path, 'games.db')
        rows = []
        try:
            gconn = sqlite3.connect(games_dbp)
            gconn.row_factory = sqlite3.Row
            cur = gconn.cursor()
            cur.execute("SELECT id, user_id, purchase_date, total_amount, COALESCE(payment_method,'Demo') as payment_method FROM purchase_history ORDER BY purchase_date DESC")
            rows = [dict(r) for r in cur.fetchall()]
            gconn.close()
        except Exception:
            rows = []
        # Build CSV
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=['id', 'user_id', 'purchase_date', 'total_amount', 'payment_method'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        resp = make_response(buf.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = 'attachment; filename=revenue.csv'
        return resp

    # =====================================================================
    # KNOWLEDGE CONSTELLATION
    # =====================================================================

    # --- Topic keyword map (label -> list of trigger words) ---
    _TOPIC_KEYWORDS = {
        "GATE 2026":        ["gate 2026", "gate2026", "gate exam", "gate"],
        "Algorithms":       ["algorithm", "algorithms", "dsa", "sorting", "binary search",
                             "graph traversal", "bfs", "dfs", "dynamic programming", "dp",
                             "greedy", "recursion", "backtracking", "heap", "tree"],
        "Operating Systems":["operating system", "os", "process", "semaphore", "scheduling",
                             "deadlock", "paging", "segmentation", "memory management",
                             "thread", "mutex", "ipc"],
        "Computer Networks":["network", "tcp", "ip", "http", "dns", "routing", "subnet",
                             "osi", "socket", "bandwidth", "protocol"],
        "Databases":        ["sql", "database", "dbms", "query", "normalization",
                             "transaction", "acid", "index", "join", "er diagram"],
        "Mathematics":      ["math", "calculus", "linear algebra", "probability",
                             "statistics", "discrete math", "combinatorics", "matrix"],
        "Study Material":   ["notes", "note", "pdf", "question paper", "pyq",
                             "previous year", "study material", "cheat sheet", "formula"],
        "Data Structures":  ["data structure", "linked list", "stack", "queue", "array",
                             "hash table", "hashmap", "trie", "segment tree"],
        "Theory of Computation": ["toc", "automata", "turing machine", "context free",
                                  "regular expression", "grammar", "pushdown"],
        "Computer Architecture": ["architecture", "cpu", "cache", "pipeline", "risc",
                                  "cisc", "instruction set", "register"],
    }

    def _constellation_db_path():
        os.makedirs(app.instance_path, exist_ok=True)
        return os.path.join(app.instance_path, 'constellation.db')

    def _ensure_constellation_tables(conn):
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user1_id, user2_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                responded_at TEXT,
                UNIQUE(requester_id, receiver_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                content TEXT,
                file_path TEXT,
                file_name TEXT,
                file_type TEXT,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS constellation_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                node_type TEXT NOT NULL DEFAULT 'topic',
                source_message_id INTEGER,
                mention_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, label)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS constellation_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                source_node_id INTEGER NOT NULL,
                target_node_id INTEGER NOT NULL,
                weight INTEGER DEFAULT 1,
                UNIQUE(chat_id, source_node_id, target_node_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS idea_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS idea_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                source_message_id INTEGER,
                mention_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, label)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS idea_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                source_node_id INTEGER NOT NULL,
                target_node_id INTEGER NOT NULL,
                weight INTEGER DEFAULT 1,
                UNIQUE(chat_id, source_node_id, target_node_id)
            )
        """)
        conn.commit()

    _STOPWORDS = {
        'the','and','for','that','with','this','from','your','you','are','but','not','was','were','have','has','had',
        'our','out','into','about','there','their','then','than','them','they','will','would','what','when','where',
        'which','while','who','how','why','can','could','should','a','an','in','on','of','to','by','as','is','it',
        'be','or','at','if','we','i','me','my','mine','us','do','does','did','so','up','down','over','under'
    }

    def _extract_keywords(text, max_terms=6):
        if not text:
            return []
        import re
        text_l = text.lower()
        tags = re.findall(r"#([a-z0-9][a-z0-9_-]{1,})", text_l)
        words = re.findall(r"[a-z][a-z0-9+#-]{2,}", text_l)
        counts = {}
        for w in words:
            if w in _STOPWORDS:
                continue
            w = w.strip('#')
            if w in _STOPWORDS or len(w) < 3:
                continue
            counts[w] = counts.get(w, 0) + 1
        for t in tags:
            counts[t] = counts.get(t, 0) + 2
        ordered = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        return [k.title() for k, _ in ordered[:max_terms]]

    def _extract_topics(text):
        """Return list of matching topic labels from message text."""
        if not text:
            return []
        tl = text.lower()
        found = []
        for label, keywords in _TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in tl:
                    found.append(label)
                    break
        keywords = _extract_keywords(text)
        for kw in keywords:
            if kw not in found:
                found.append(kw)
        return found

    def _clean_graph_label(label):
        label = (label or '').strip()
        label = ' '.join(label.replace('\n', ' ').split())
        if len(label) > 42:
            label = label[:42].rstrip()
        return label

    def _dedupe_labels(labels, max_items=8):
        seen = set()
        clean = []
        for label in labels or []:
            label = _clean_graph_label(label)
            key = label.lower()
            if not label or key in seen:
                continue
            seen.add(key)
            clean.append(label)
            if len(clean) >= max_items:
                break
        return clean

    def _openai_json_request(payload, timeout=12):
        api_key = os.getenv('OPENAI_API_KEY', '').strip()
        if not api_key:
            return None
        api_url = os.getenv('OPENAI_API_BASE_URL', '').strip()
        if not api_url:
            api_url = 'https://openrouter.ai/api/v1/chat/completions' if api_key.startswith('sk-or-') else 'https://api.openai.com/v1/chat/completions'
        body = json.dumps(payload).encode('utf-8')
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        if 'openrouter.ai' in api_url:
            headers['HTTP-Referer'] = os.getenv('APP_PUBLIC_URL', 'http://localhost:5000')
            headers['X-Title'] = os.getenv('APP_NAME', 'Arcade')
        req = urllib.request.Request(
            api_url,
            data=body,
            headers=headers,
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None

    def _extract_idea_graph_with_ai(context_messages):
        """Return AI-suggested graph labels and edges from recent chat context."""
        if not os.getenv('OPENAI_API_KEY', '').strip():
            return None
        compact_messages = []
        for m in context_messages[-24:]:
            content = (m.get('content') or '').strip()
            if content:
                compact_messages.append({
                    'mode': m.get('mode', 'chat'),
                    'sender': str(m.get('sender_id', '')),
                    'content': content[:700],
                })
        if not compact_messages:
            return None

        api_key = os.getenv('OPENAI_API_KEY', '').strip()
        default_model = 'openai/gpt-4o-mini' if api_key.startswith('sk-or-') else 'gpt-4o-mini'
        payload = {
            'model': os.getenv('OPENAI_IDEA_MODEL', default_model),
            'temperature': 0.2,
            'response_format': {'type': 'json_object'},
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'You turn a two-person project conversation into a small meaningful graph. '
                        'Return only JSON with "nodes" and "edges". Nodes must be short noun phrases. '
                        'Edges must connect related node labels that both appear in nodes. Avoid generic labels.'
                    )
                },
                {
                    'role': 'user',
                    'content': json.dumps({
                        'max_nodes': 8,
                        'max_edges': 10,
                        'messages': compact_messages
                    })
                }
            ]
        }
        result = _openai_json_request(payload)
        try:
            raw = result['choices'][0]['message']['content']
            graph = json.loads(raw)
        except (TypeError, KeyError, IndexError, json.JSONDecodeError):
            return None

        nodes = _dedupe_labels(graph.get('nodes'), max_items=8)
        node_keys = {n.lower(): n for n in nodes}
        edges = []
        for edge in graph.get('edges') or []:
            if isinstance(edge, dict):
                src = edge.get('source') or edge.get('from')
                tgt = edge.get('target') or edge.get('to')
            elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
                src, tgt = edge[0], edge[1]
            else:
                continue
            src = node_keys.get(_clean_graph_label(src).lower())
            tgt = node_keys.get(_clean_graph_label(tgt).lower())
            if src and tgt and src != tgt:
                pair = tuple(sorted((src, tgt), key=str.lower))
                if pair not in edges:
                    edges.append(pair)
            if len(edges) >= 10:
                break
        return {'nodes': nodes, 'edges': edges} if nodes else None

    def _upsert_node(cur, chat_id, label, node_type, msg_id, now):
        """Insert or increment mention_count for a node; returns its id."""
        cur.execute(
            "SELECT id, mention_count FROM constellation_nodes WHERE chat_id=? AND label=?",
            (chat_id, label)
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE constellation_nodes SET mention_count=mention_count+1 WHERE id=?",
                (row[0],)
            )
            return row[0]
        else:
            cur.execute(
                """INSERT INTO constellation_nodes(chat_id, label, node_type, source_message_id, mention_count, created_at)
                   VALUES(?,?,?,?,1,?)""",
                (chat_id, label, node_type, msg_id, now)
            )
            return cur.lastrowid

    def _upsert_edge(cur, chat_id, src_id, tgt_id):
        if src_id == tgt_id:
            return
        a, b = (src_id, tgt_id) if src_id < tgt_id else (tgt_id, src_id)
        cur.execute(
            "SELECT id FROM constellation_edges WHERE chat_id=? AND source_node_id=? AND target_node_id=?",
            (chat_id, a, b)
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE constellation_edges SET weight=weight+1 WHERE id=?", (row[0],)
            )
        else:
            cur.execute(
                "INSERT INTO constellation_edges(chat_id, source_node_id, target_node_id, weight) VALUES(?,?,?,1)",
                (chat_id, a, b)
            )

    def _upsert_idea_node(cur, chat_id, label, msg_id, now):
        cur.execute(
            "SELECT id, mention_count FROM idea_nodes WHERE chat_id=? AND label=?",
            (chat_id, label)
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE idea_nodes SET mention_count=mention_count+1 WHERE id=?",
                (row[0],)
            )
            return row[0]
        cur.execute(
            """INSERT INTO idea_nodes(chat_id, label, source_message_id, mention_count, created_at)
               VALUES(?,?,?,?,?)""",
            (chat_id, label, msg_id, 1, now)
        )
        return cur.lastrowid

    def _upsert_idea_edge(cur, chat_id, src_id, tgt_id):
        if src_id == tgt_id:
            return
        a, b = (src_id, tgt_id) if src_id < tgt_id else (tgt_id, src_id)
        cur.execute(
            "SELECT id FROM idea_edges WHERE chat_id=? AND source_node_id=? AND target_node_id=?",
            (chat_id, a, b)
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE idea_edges SET weight=weight+1 WHERE id=?",
                (row[0],)
            )
        else:
            cur.execute(
                "INSERT INTO idea_edges(chat_id, source_node_id, target_node_id, weight) VALUES(?,?,?,1)",
                (chat_id, a, b)
            )

    def _get_or_create_chat(conn, uid1, uid2):
        cur = conn.cursor()
        a, b = (uid1, uid2) if uid1 < uid2 else (uid2, uid1)
        cur.execute(
            "SELECT id FROM chats WHERE user1_id=? AND user2_id=?", (a, b)
        )
        row = cur.fetchone()
        if row:
            return row[0]
        from datetime import datetime as _dt
        cur.execute(
            "INSERT INTO chats(user1_id, user2_id, created_at) VALUES(?,?,?)",
            (a, b, _dt.utcnow().isoformat())
        )
        conn.commit()
        return cur.lastrowid

    def _friendship_status(cur, uid1, uid2):
        if uid1 == uid2:
            return 'self'
        a, b = (uid1, uid2)
        cur.execute(
            """SELECT status, requester_id, receiver_id FROM friend_requests
               WHERE (requester_id=? AND receiver_id=?) OR (requester_id=? AND receiver_id=?)
               ORDER BY id DESC LIMIT 1""",
            (a, b, b, a)
        )
        row = cur.fetchone()
        return row['status'] if row else 'none'

    def _are_friends(cur, uid1, uid2):
        return _friendship_status(cur, uid1, uid2) == 'accepted'

    def _public_user(user):
        tag = _ensure_user_tag(user)
        return {
            'id': user.id,
            'username': user.username,
            'user_tag': tag,
            'handle': f"{user.username}#{tag}",
            'display_name': getattr(user, 'display_name', None) or user.username,
            'photo_path': getattr(user, 'photo_path', None)
        }

    def _find_user_by_handle(handle):
        handle = (handle or '').strip()
        if handle.startswith('@'):
            handle = handle[1:].strip()
        if '#' not in handle:
            return None
        username, tag = handle.rsplit('#', 1)
        username = username.strip().lstrip('@')
        tag = tag.strip()
        if not username or len(tag) != 4 or not tag.isdigit():
            return None
        try:
            for user in User.query.filter((User.user_tag == None) | (User.user_tag == '')).all():
                user.user_tag = _generate_user_tag()
            db.session.commit()
        except Exception:
            db.session.rollback()
        return User.query.filter(
            func.lower(User.username) == username.lower(),
            User.user_tag == tag
        ).first()

    # --- Page routes ---
    @app.route('/constellation')
    def constellation_page():
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        return render_template('constellation.html')

    @app.route('/constellation/<path:other_uid>')
    def constellation_chat(other_uid):
        if 'user' not in session and 'user_id' not in session:
            return redirect(url_for('login'))
        return render_template('constellation.html', open_uid=other_uid)

    # --- API: current user friendship identity ---
    @app.route('/api/constellation/me')
    def constellation_me():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'auth required'}), 401
            return jsonify(_mongo_public_user(current))
        user = db.session.get(User, int(session.get('user_id') or 0))
        if not user:
            return jsonify({'error': 'auth required'}), 401
        return jsonify(_public_user(user))

    # --- API: list accepted friends to DM ---
    @app.route('/api/constellation/users')
    def constellation_users():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'auth required'}), 401
            mdb = _mongo_db()
            rows = mdb.friend_requests.find({
                'status': 'accepted',
                '$or': [{'requester_key': current['_id']}, {'receiver_key': current['_id']}]
            }).sort('responded_at', DESCENDING)
            friend_keys = [r['receiver_key'] if r['requester_key'] == current['_id'] else r['requester_key'] for r in rows]
            users = list(mdb.users.find({'_id': {'$in': friend_keys}}).sort('username_lc', ASCENDING))
            return jsonify([_mongo_public_user(u) for u in users])
        me = int(session.get('user_id') or 0)
        try:
            dbp = _constellation_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_constellation_tables(conn)
            cur = conn.cursor()
            cur.execute(
                """SELECT requester_id, receiver_id FROM friend_requests
                   WHERE status='accepted' AND (requester_id=? OR receiver_id=?)
                   ORDER BY responded_at DESC, created_at DESC""",
                (me, me)
            )
            friend_ids = [r['receiver_id'] if r['requester_id'] == me else r['requester_id'] for r in cur.fetchall()]
            conn.close()
            if not friend_ids:
                return jsonify([])
            users = User.query.filter(User.id.in_(friend_ids)).order_by(User.username).all()
            return jsonify([_public_user(u) for u in users])
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/constellation/friends/requests')
    def constellation_friend_requests():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'auth required'}), 401
            mdb = _mongo_db()
            rows = mdb.friend_requests.find({
                'status': 'pending',
                '$or': [{'requester_key': current['_id']}, {'receiver_key': current['_id']}]
            }).sort('created_at', DESCENDING)
            requests = []
            for row in rows:
                other_key = row['requester_key'] if row['receiver_key'] == current['_id'] else row['receiver_key']
                other = mdb.users.find_one({'_id': other_key})
                if not other:
                    continue
                requests.append({
                    'id': str(row['_id']),
                    'direction': 'incoming' if row['receiver_key'] == current['_id'] else 'outgoing',
                    'user': _mongo_public_user(other)
                })
            return jsonify(requests)
        me = int(session.get('user_id') or 0)
        try:
            dbp = _constellation_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_constellation_tables(conn)
            cur = conn.cursor()
            cur.execute(
                """SELECT * FROM friend_requests
                   WHERE status='pending' AND (requester_id=? OR receiver_id=?)
                   ORDER BY created_at DESC""",
                (me, me)
            )
            requests = []
            for row in cur.fetchall():
                other_id = row['requester_id'] if row['receiver_id'] == me else row['receiver_id']
                other = db.session.get(User, other_id)
                if not other:
                    continue
                item = dict(row)
                item['direction'] = 'incoming' if row['receiver_id'] == me else 'outgoing'
                item['user'] = _public_user(other)
                requests.append(item)
            conn.close()
            return jsonify(requests)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/constellation/friends/request', methods=['POST'])
    def constellation_send_friend_request():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'auth required'}), 401
            data = request.get_json(silent=True) or {}
            handle = (data.get('handle') or '').strip()
            if '#' not in handle:
                return jsonify({'error': 'Enter the full username#0000'}), 400
            target = _mongo_find_user_by_handle(handle)
            if not target:
                return jsonify({'error': 'No user found with that tag'}), 404
            if target['_id'] == current['_id']:
                return jsonify({'error': 'You cannot add yourself'}), 400
            from datetime import datetime as _dt
            mdb = _mongo_db()
            pair_key = _mongo_pair_key(current['_id'], target['_id'])
            existing = mdb.friend_requests.find_one({'pair_key': pair_key})
            if existing and existing.get('status') == 'accepted':
                return jsonify({'success': True, 'status': 'accepted', 'message': 'Already friends'})
            if existing and existing.get('status') == 'pending':
                return jsonify({'success': True, 'status': 'pending', 'message': 'Friend request already pending'})
            mdb.friend_requests.update_one(
                {'pair_key': pair_key},
                {'$set': {
                    'pair_key': pair_key,
                    'requester_key': current['_id'],
                    'receiver_key': target['_id'],
                    'status': 'pending',
                    'created_at': _dt.utcnow().isoformat(),
                    'responded_at': None
                }},
                upsert=True
            )
            return jsonify({'success': True, 'status': 'pending'})
        me = int(session.get('user_id') or 0)
        data = request.get_json(silent=True) or {}
        handle = (data.get('handle') or '').strip()
        if '#' not in handle:
            return jsonify({'error': 'Enter the full username#0000'}), 400
        if os.environ.get('VERCEL') == '1' and not os.getenv('DATABASE_URL'):
            return jsonify({
                'error': 'Friend lookup needs a shared DATABASE_URL on Vercel. Local SQLite in /tmp is not shared between users.'
            }), 503
        target = _find_user_by_handle(handle)
        if not target:
            return jsonify({'error': 'No user found with that tag'}), 404
        if target.id == me:
            return jsonify({'error': 'You cannot add yourself'}), 400
        from datetime import datetime as _dt
        try:
            dbp = _constellation_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_constellation_tables(conn)
            cur = conn.cursor()
            status = _friendship_status(cur, me, target.id)
            if status == 'accepted':
                conn.close()
                return jsonify({'success': True, 'status': 'accepted', 'message': 'Already friends'})
            if status == 'pending':
                conn.close()
                return jsonify({'success': True, 'status': 'pending', 'message': 'Friend request already pending'})
            cur.execute(
                """INSERT OR REPLACE INTO friend_requests(requester_id, receiver_id, status, created_at, responded_at)
                   VALUES(?,?,?,?,NULL)""",
                (me, target.id, 'pending', _dt.utcnow().isoformat())
            )
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'status': 'pending'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/constellation/friends/respond', methods=['POST'])
    def constellation_respond_friend_request():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'auth required'}), 401
            data = request.get_json(silent=True) or {}
            req_id = (data.get('request_id') or '').strip()
            action = (data.get('action') or '').strip().lower()
            if action not in ('accept', 'decline'):
                return jsonify({'error': 'action must be accept or decline'}), 400
            from bson import ObjectId
            from bson.errors import InvalidId
            from datetime import datetime as _dt
            mdb = _mongo_db()
            try:
                request_oid = ObjectId(req_id)
            except (InvalidId, TypeError):
                return jsonify({'error': 'request not found'}), 404
            row = mdb.friend_requests.find_one({'_id': request_oid, 'receiver_key': current['_id'], 'status': 'pending'})
            if not row:
                return jsonify({'error': 'request not found'}), 404
            status = 'accepted' if action == 'accept' else 'declined'
            mdb.friend_requests.update_one({'_id': row['_id']}, {'$set': {'status': status, 'responded_at': _dt.utcnow().isoformat()}})
            if status == 'accepted':
                chat_id = _mongo_chat_id(row['requester_key'], row['receiver_key'])
                mdb.chats.update_one(
                    {'chat_id': chat_id},
                    {'$setOnInsert': {'chat_id': chat_id, 'participants': sorted([row['requester_key'], row['receiver_key']]), 'created_at': _dt.utcnow().isoformat()}},
                    upsert=True
                )
            return jsonify({'success': True, 'status': status})
        me = int(session.get('user_id') or 0)
        data = request.get_json(silent=True) or {}
        req_id = int(data.get('request_id') or 0)
        action = (data.get('action') or '').strip().lower()
        if action not in ('accept', 'decline'):
            return jsonify({'error': 'action must be accept or decline'}), 400
        from datetime import datetime as _dt
        try:
            dbp = _constellation_db_path()
            conn = sqlite3.connect(dbp)
            conn.row_factory = sqlite3.Row
            _ensure_constellation_tables(conn)
            cur = conn.cursor()
            cur.execute("SELECT * FROM friend_requests WHERE id=? AND receiver_id=? AND status='pending'", (req_id, me))
            req_row = cur.fetchone()
            if not req_row:
                conn.close()
                return jsonify({'error': 'request not found'}), 404
            status = 'accepted' if action == 'accept' else 'declined'
            cur.execute(
                "UPDATE friend_requests SET status=?, responded_at=? WHERE id=?",
                (status, _dt.utcnow().isoformat(), req_id)
            )
            if status == 'accepted':
                _get_or_create_chat(conn, req_row['requester_id'], req_row['receiver_id'])
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'status': status})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # --- API: get or create chat id ---
    @app.route('/api/constellation/chat/<path:other_uid>')
    def constellation_get_chat(other_uid):
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'auth required'}), 401
            other = _mongo_db().users.find_one({'_id': _mongo_key(other_uid)})
            if not other:
                return jsonify({'error': 'user not found'}), 404
            if not _mongo_are_friends(current['_id'], other['_id']):
                return jsonify({'error': 'friend request must be accepted before chatting'}), 403
            from datetime import datetime as _dt
            chat_id = _mongo_chat_id(current['_id'], other['_id'])
            _mongo_db().chats.update_one(
                {'chat_id': chat_id},
                {'$setOnInsert': {'chat_id': chat_id, 'participants': sorted([current['_id'], other['_id']]), 'created_at': _dt.utcnow().isoformat()}},
                upsert=True
            )
            return jsonify({'chat_id': chat_id})
        
        other_uid = int(other_uid)
        me = int(session.get('user_id') or 0)
        if other_uid == me:
            return jsonify({'error': 'choose another user to start a chat'}), 400
        if not db.session.get(User, other_uid):
            return jsonify({'error': 'user not found'}), 404
        try:
            # Check if users are friends (SQLAlchemy-based)
            # For now, we'll allow any two users to chat if they exist
            # In the future, you may want to add a friend verification check here
            
            # Get or create chat using SQLAlchemy
            chat = ConstellationChat.query.filter(
                db.or_(
                    db.and_(ConstellationChat.user1_id == me, ConstellationChat.user2_id == other_uid),
                    db.and_(ConstellationChat.user1_id == other_uid, ConstellationChat.user2_id == me)
                )
            ).first()
            
            if not chat:
                from datetime import datetime as _dt
                # Create new chat with user1_id < user2_id for consistency
                user1_id = min(me, other_uid)
                user2_id = max(me, other_uid)
                chat = ConstellationChat(
                    user1_id=user1_id,
                    user2_id=user2_id,
                    created_at=_dt.utcnow().isoformat()
                )
                db.session.add(chat)
                db.session.commit()
            
            return jsonify({'chat_id': chat.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # --- API: load messages for a chat ---
    @app.route('/api/constellation/messages/<path:chat_id>')
    def constellation_messages(chat_id):
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'MongoDB is unavailable on this Vercel instance. Check MONGODB_URI and Atlas network access.'}), 503
            mdb = _mongo_db()
            chat = mdb.chats.find_one({'chat_id': chat_id, 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            since = request.args.get('since_id', '')
            query = {'chat_id': chat_id}
            if since and since != '0':
                from bson import ObjectId
                from bson.errors import InvalidId
                try:
                    query['_id'] = {'$gt': ObjectId(since)}
                except (InvalidId, TypeError):
                    pass
            rows = []
            for r in mdb.messages.find(query).sort('created_at', ASCENDING).limit(100):
                rows.append({
                    'id': str(r['_id']),
                    # sender_id matches myKey (MongoDB _id = username string)
                    'sender_id': r.get('sender_key'),
                    'content': r.get('content'),
                    'created_at': r.get('created_at'),
                    'file_url': r.get('file_url'),
                    'file_name': r.get('file_name'),
                    'file_type': r.get('file_type'),
                })
            return jsonify(rows)
        
        # Use SQLAlchemy models
        me = int(session.get('user_id') or 0)
        try:
            chat_id = int(chat_id)
            # Verify membership
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            since = request.args.get('since_id', 0, type=int)
            msgs = ConstellationMessage.query.filter(
                ConstellationMessage.chat_id == chat_id,
                ConstellationMessage.id > since
            ).order_by(ConstellationMessage.id.asc()).limit(100).all()
            
            rows = []
            for msg in msgs:
                d = {
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'content': msg.content,
                    'created_at': msg.created_at,
                    'file_path': msg.file_path,
                    'file_name': msg.file_name,
                    'file_type': msg.file_type
                }
                if msg.file_path:
                    d['file_url'] = url_for('static', filename=msg.file_path) if not msg.file_path.startswith('/api/') else msg.file_path
                rows.append(d)
            
            return jsonify(rows)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # --- API: send message ---
    @app.route('/api/constellation/send', methods=['POST'])
    def constellation_send():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        data = request.get_json(silent=True) or {}
        chat_id_raw = data.get('chat_id') or ''
        content = (data.get('content') or '').strip()
        if not chat_id_raw or not content:
            return jsonify({'error': 'chat_id and content required'}), 400
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'MongoDB is unavailable on this Vercel instance. Check MONGODB_URI and Atlas network access.'}), 503
            mdb = _mongo_db()
            chat_id = str(chat_id_raw)
            chat = mdb.chats.find_one({'chat_id': chat_id, 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            from datetime import datetime as _dt
            now = _dt.utcnow().isoformat()
            inserted = mdb.messages.insert_one({'chat_id': chat_id, 'sender_key': current['_id'], 'content': content, 'created_at': now})
            topics = _extract_topics(content)
            edges = []
            for i in range(len(topics)):
                for j in range(i + 1, len(topics)):
                    edges.append((topics[i], topics[j]))
            _mongo_upsert_graph('chat', chat_id, topics, edges)
            return jsonify({'success': True, 'id': str(inserted.inserted_id), 'topics_found': topics})
        
        # Use SQLAlchemy models for persistence
        me = int(session.get('user_id') or 0)
        chat_id = int(chat_id_raw)
        from datetime import datetime as _dt
        try:
            # Verify membership using SQLAlchemy models
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            now = _dt.utcnow().isoformat()
            msg = ConstellationMessage(
                chat_id=chat.id,
                sender_id=me,
                content=content,
                created_at=now
            )
            db.session.add(msg)
            db.session.flush()  # Get the message ID
            msg_id = msg.id
            db.session.commit()
            
            # Topic extraction + graph update
            topics = _extract_topics(content)
            node_ids = []
            for topic in topics:
                node = ConstellationNode.query.filter_by(
                    chat_id=chat.id,
                    label=topic
                ).first()
                if not node:
                    node = ConstellationNode(
                        chat_id=chat.id,
                        label=topic,
                        node_type='topic',
                        source_message_id=msg_id,
                        mention_count=1,
                        created_at=now
                    )
                    db.session.add(node)
                    db.session.flush()
                else:
                    node.mention_count += 1
                    db.session.add(node)
                    db.session.flush()
                node_ids.append(node.id)
            
            # Connect all co-occurring topics in the same message
            for i in range(len(node_ids)):
                for j in range(i + 1, len(node_ids)):
                    edge = ConstellationEdge.query.filter_by(
                        chat_id=chat.id,
                        source_node_id=node_ids[i],
                        target_node_id=node_ids[j]
                    ).first()
                    if edge:
                        edge.weight += 1
                    else:
                        edge = ConstellationEdge(
                            chat_id=chat.id,
                            source_node_id=node_ids[i],
                            target_node_id=node_ids[j],
                            weight=1
                        )
                        db.session.add(edge)
            
            db.session.commit()
            return jsonify({'success': True, 'id': msg_id, 'topics_found': topics})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # --- Ideas mode: messages ---
    @app.route('/api/constellation/ideas/messages/<path:chat_id>')
    def constellation_idea_messages(chat_id):
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'MongoDB is unavailable on this Vercel instance. Check MONGODB_URI and Atlas network access.'}), 503
            mdb = _mongo_db()
            chat = mdb.chats.find_one({'chat_id': chat_id, 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            since = request.args.get('since_id', '')
            query = {'chat_id': chat_id}
            if since and since != '0':
                from bson import ObjectId
                from bson.errors import InvalidId
                try:
                    query['_id'] = {'$gt': ObjectId(since)}
                except (InvalidId, TypeError):
                    pass
            rows = [{
                'id': str(r['_id']),
                'sender_id': r.get('sender_key'),
                'content': r.get('content'),
                'created_at': r.get('created_at'),
                'file_url': r.get('file_url'),
                'file_name': r.get('file_name'),
                'file_type': r.get('file_type'),
            } for r in mdb.idea_messages.find(query).sort('created_at', ASCENDING).limit(100)]
            return jsonify(rows)
        
        # Use SQLAlchemy models
        chat_id = int(chat_id)
        me = int(session.get('user_id') or 0)
        try:
            # Verify membership
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            since = request.args.get('since_id', 0, type=int)
            msgs = IdeaMessage.query.filter(
                IdeaMessage.chat_id == chat_id,
                IdeaMessage.id > since
            ).order_by(IdeaMessage.id.asc()).limit(100).all()
            
            rows = []
            for msg in msgs:
                rows.append({
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'content': msg.content,
                    'created_at': msg.created_at
                })
            
            return jsonify(rows)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/constellation/ideas/send', methods=['POST'])
    def constellation_idea_send():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        data = request.get_json(silent=True) or {}
        chat_id_raw = data.get('chat_id') or ''
        content = (data.get('content') or '').strip()
        if not chat_id_raw or not content:
            return jsonify({'error': 'chat_id and content required'}), 400
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'MongoDB is unavailable on this Vercel instance. Check MONGODB_URI and Atlas network access.'}), 503
            mdb = _mongo_db()
            chat_id = str(chat_id_raw)
            chat = mdb.chats.find_one({'chat_id': chat_id, 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            from datetime import datetime as _dt
            now = _dt.utcnow().isoformat()
            inserted = mdb.idea_messages.insert_one({'chat_id': chat_id, 'sender_key': current['_id'], 'content': content, 'created_at': now})
            recent = list(mdb.messages.find({'chat_id': chat_id}).sort('created_at', DESCENDING).limit(16))
            recent += list(mdb.idea_messages.find({'chat_id': chat_id}).sort('created_at', DESCENDING).limit(16))
            context_messages = sorted([
                {'sender_id': r.get('sender_key'), 'content': r.get('content'), 'created_at': r.get('created_at'), 'mode': 'ideas' if 'idea' in str(r.get('_id')) else 'chat'}
                for r in recent
            ], key=lambda r: r.get('created_at') or '')
            ai_graph = _extract_idea_graph_with_ai(context_messages)
            topics = ai_graph['nodes'] if ai_graph else _extract_topics(content)
            edges = ai_graph['edges'] if ai_graph else [(topics[i], topics[j]) for i in range(len(topics)) for j in range(i + 1, len(topics))]
            _mongo_upsert_graph('ideas', chat_id, topics, edges)
            return jsonify({'success': True, 'id': str(inserted.inserted_id), 'topics_found': topics, 'ai_graph': bool(ai_graph)})
        
        # Use SQLAlchemy models
        me = int(session.get('user_id') or 0)
        chat_id = int(chat_id_raw)
        from datetime import datetime as _dt
        try:
            # Verify membership
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            now = _dt.utcnow().isoformat()
            msg = IdeaMessage(
                chat_id=chat.id,
                sender_id=me,
                content=content,
                created_at=now
            )
            db.session.add(msg)
            db.session.flush()
            msg_id = msg.id
            db.session.commit()
            
            # Topic extraction + graph update
            topics = _extract_topics(content)
            node_ids = []
            for topic in topics:
                node = IdeaNode.query.filter_by(
                    chat_id=chat.id,
                    label=topic
                ).first()
                if not node:
                    node = IdeaNode(
                        chat_id=chat.id,
                        label=topic,
                        source_message_id=msg_id,
                        mention_count=1,
                        created_at=now
                    )
                    db.session.add(node)
                    db.session.flush()
                else:
                    node.mention_count += 1
                    db.session.add(node)
                    db.session.flush()
                node_ids.append(node.id)
            
            # Connect all co-occurring topics in the same message
            for i in range(len(node_ids)):
                for j in range(i + 1, len(node_ids)):
                    edge = IdeaEdge.query.filter_by(
                        chat_id=chat.id,
                        source_node_id=node_ids[i],
                        target_node_id=node_ids[j]
                    ).first()
                    if edge:
                        edge.weight += 1
                    else:
                        edge = IdeaEdge(
                            chat_id=chat.id,
                            source_node_id=node_ids[i],
                            target_node_id=node_ids[j],
                            weight=1
                        )
                        db.session.add(edge)
            
            db.session.commit()
            return jsonify({'success': True, 'id': msg_id, 'topics_found': topics, 'ai_graph': False})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/constellation/ideas/graph/<path:chat_id>')
    def constellation_idea_graph(chat_id):
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'MongoDB is unavailable on this Vercel instance. Check MONGODB_URI and Atlas network access.'}), 503
            mdb = _mongo_db()
            chat = mdb.chats.find_one({'chat_id': chat_id, 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            return jsonify(_mongo_graph('ideas', chat_id))
        
        # Use SQLAlchemy models
        chat_id = int(chat_id)
        me = int(session.get('user_id') or 0)
        try:
            # Verify membership
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            # Get idea nodes
            nodes_query = IdeaNode.query.filter_by(chat_id=chat_id).order_by(IdeaNode.mention_count.desc()).all()
            nodes = []
            for n in nodes_query:
                nodes.append({
                    'id': n.id,
                    'label': n.label,
                    'node_type': 'idea',
                    'mention_count': n.mention_count
                })
            
            # Get idea edges
            edges_query = IdeaEdge.query.filter_by(chat_id=chat_id).all()
            edges = []
            for e in edges_query:
                edges.append({
                    'source_node_id': e.source_node_id,
                    'target_node_id': e.target_node_id,
                    'weight': e.weight
                })
            
            return jsonify({'nodes': nodes, 'edges': edges})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/constellation/file/<file_id>')
    def constellation_file(file_id):
        if not _mongo_available():
            return "MongoDB not available", 503
        mdb = _mongo_db()
        import gridfs
        from bson import ObjectId
        fs = gridfs.GridFS(mdb)
        try:
            grid_out = fs.get(ObjectId(file_id))
            from flask import send_file
            import io
            return send_file(io.BytesIO(grid_out.read()), mimetype=grid_out.content_type, download_name=grid_out.filename)
        except Exception as e:
            return "File not found", 404

    # --- API: upload file ---
    @app.route('/api/constellation/upload', methods=['POST'])
    def constellation_upload():
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        me = int(session.get('user_id') or 0)
        chat_id_raw = (request.form.get('chat_id') or '').strip()
        file = request.files.get('file')
        if not chat_id_raw or not file or not getattr(file, 'filename', ''):
            return jsonify({'error': 'chat_id and file required'}), 400

        fname = secure_filename(file.filename)
        ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
        allowed = {'pdf', 'png', 'jpg', 'jpeg', 'txt', 'doc', 'docx', 'xls', 'xlsx', 'webp'}
        if ext not in allowed:
            return jsonify({'error': f'File type .{ext} not allowed'}), 400
        file_type = 'pdf' if ext == 'pdf' else ('image' if ext in ('png', 'jpg', 'jpeg', 'webp') else 'note')

        if _mongo_available():
            # --- MongoDB / Vercel path: upload via Cloudinary ---
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'auth required'}), 401
            if not _cloudinary_configured():
                return jsonify({
                    'error': 'File uploads require Cloudinary to be configured. '
                             'Add CLOUDINARY_URL to your Vercel environment variables '
                             '(free at cloudinary.com).'
                }), 503
            mdb = _mongo_db()
            chat_id = str(chat_id_raw)
            chat = mdb.chats.find_one({'chat_id': chat_id, 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            # Determine Cloudinary resource type
            resource_type = 'image' if file_type == 'image' else 'raw'
            file_url, err = _cloudinary_upload(file, folder='constellation', resource_type=resource_type)
            if err:
                return jsonify({'error': f'Upload failed: {err}'}), 500
            from datetime import datetime as _dt
            now = _dt.utcnow().isoformat()
            topics = _extract_topics(fname.replace('_', ' ').replace('-', ' '))
            edges = [(topics[i], topics[j]) for i in range(len(topics)) for j in range(i + 1, len(topics))]
            inserted = mdb.messages.insert_one({
                'chat_id': chat_id,
                'sender_key': current['_id'],
                'content': None,
                'file_url': file_url,
                'file_name': file.filename,
                'file_type': file_type,
                'created_at': now
            })
            # ---- Upsert file node + topic nodes + edges in graph ----
            file_label = file.filename
            file_label_lc = file_label.lower()
            # Upsert the file node
            mdb.graph_nodes.update_one(
                {'chat_id': chat_id, 'mode': 'chat', 'label_lc': file_label_lc},
                {'$setOnInsert': {'chat_id': chat_id, 'mode': 'chat', 'label': file_label, 'node_type': 'file'},
                 '$inc': {'mention_count': 1}},
                upsert=True
            )
            # Upsert topic nodes and connect each one to the file node via an edge
            normalized_name = fname.lower().replace('_', ' ').replace('-', ' ')
            topics = _extract_topics(normalized_name)
            if topics:
                for topic in _dedupe_labels(topics, max_items=6):
                    topic_lc = topic.lower()
                    mdb.graph_nodes.update_one(
                        {'chat_id': chat_id, 'mode': 'chat', 'label_lc': topic_lc},
                        {'$setOnInsert': {'chat_id': chat_id, 'mode': 'chat', 'label': topic, 'node_type': 'topic'},
                         '$inc': {'mention_count': 1}},
                        upsert=True
                    )
                    # Edge between file node and topic node (sorted for uniqueness)
                    a, b = sorted([file_label_lc, topic_lc])
                    mdb.graph_edges.update_one(
                        {'chat_id': chat_id, 'mode': 'chat', 'source_label_lc': a, 'target_label_lc': b},
                        {'$setOnInsert': {'chat_id': chat_id, 'mode': 'chat',
                                          'source_label': a, 'target_label': b},
                         '$inc': {'weight': 1}},
                        upsert=True
                    )
            else:
                # Fallback: connect file to a generic "Shared Files" hub node
                hub_lc = 'shared files'
                mdb.graph_nodes.update_one(
                    {'chat_id': chat_id, 'mode': 'chat', 'label_lc': hub_lc},
                    {'$setOnInsert': {'chat_id': chat_id, 'mode': 'chat', 'label': 'Shared Files', 'node_type': 'topic'},
                     '$inc': {'mention_count': 1}},
                    upsert=True
                )
                a, b = sorted([file_label_lc, hub_lc])
                mdb.graph_edges.update_one(
                    {'chat_id': chat_id, 'mode': 'chat', 'source_label_lc': a, 'target_label_lc': b},
                    {'$setOnInsert': {'chat_id': chat_id, 'mode': 'chat',
                                      'source_label': a, 'target_label': b},
                     '$inc': {'weight': 1}},
                    upsert=True
                )
            return jsonify({'success': True, 'id': str(inserted.inserted_id), 'file_url': file_url})

        # --- SQLite / local path ---
        chat_id = int(chat_id_raw)
        from datetime import datetime as _dt
        try:
            # Verify membership using SQLAlchemy models
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            # Save file (with Vercel read-only filesystem fallback)
            upload_dir = os.path.join(app.static_folder, 'uploads', 'constellation')
            now = _dt.utcnow()
            unique_name = f"c{chat_id}_u{me}_{int(now.timestamp())}_{fname}"
            abs_path = os.path.join(upload_dir, unique_name)

            try:
                os.makedirs(upload_dir, exist_ok=True)
                file.save(abs_path)
            except OSError:
                pass  # Ignore Read-Only File System errors on Vercel

            rel_path = 'uploads/constellation/' + unique_name
            now_str = now.isoformat()
            
            # Insert message
            msg = ConstellationMessage(
                chat_id=chat_id,
                sender_id=me,
                content=None,
                file_path=rel_path,
                file_name=file.filename,
                file_type=file_type,
                created_at=now_str
            )
            db.session.add(msg)
            db.session.flush()
            msg_id = msg.id
            
            # Create a file node in the graph
            node_label = file.filename
            nid_file = ConstellationNode.query.filter_by(chat_id=chat_id, label=node_label).first()
            if not nid_file:
                nid_file = ConstellationNode(chat_id=chat_id, label=node_label, node_type='file', source_message_id=msg_id, mention_count=1, created_at=now_str)
                db.session.add(nid_file)
                db.session.flush()
            else:
                nid_file.mention_count += 1
                db.session.add(nid_file)
                db.session.flush()

            linked_topics = set()
            normalized_name = file.filename.lower().replace('_', ' ').replace('-', ' ')
            for topic in _extract_topics(normalized_name):
                nid_topic = ConstellationNode.query.filter_by(chat_id=chat_id, label=topic).first()
                if not nid_topic:
                    nid_topic = ConstellationNode(chat_id=chat_id, label=topic, node_type='topic', source_message_id=msg_id, mention_count=1, created_at=now_str)
                    db.session.add(nid_topic)
                    db.session.flush()
                else:
                    nid_topic.mention_count += 1
                    db.session.add(nid_topic)
                    db.session.flush()
                
                # Add edge
                edge = ConstellationEdge.query.filter_by(chat_id=chat_id, source_node_id=nid_file.id, target_node_id=nid_topic.id).first()
                if not edge:
                    edge2 = ConstellationEdge.query.filter_by(chat_id=chat_id, source_node_id=nid_topic.id, target_node_id=nid_file.id).first()
                    if edge2:
                        edge2.weight += 1
                        db.session.add(edge2)
                    else:
                        new_edge = ConstellationEdge(chat_id=chat_id, source_node_id=nid_file.id, target_node_id=nid_topic.id, weight=1)
                        db.session.add(new_edge)
                else:
                    edge.weight += 1
                    db.session.add(edge)
                
                linked_topics.add(topic)

            if not linked_topics:
                nid_hub = ConstellationNode.query.filter_by(chat_id=chat_id, label='Shared Files').first()
                if not nid_hub:
                    nid_hub = ConstellationNode(chat_id=chat_id, label='Shared Files', node_type='topic', source_message_id=msg_id, mention_count=1, created_at=now_str)
                    db.session.add(nid_hub)
                    db.session.flush()
                else:
                    nid_hub.mention_count += 1
                    db.session.add(nid_hub)
                    db.session.flush()
                
                edge = ConstellationEdge.query.filter_by(chat_id=chat_id, source_node_id=nid_file.id, target_node_id=nid_hub.id).first()
                if not edge:
                    edge2 = ConstellationEdge.query.filter_by(chat_id=chat_id, source_node_id=nid_hub.id, target_node_id=nid_file.id).first()
                    if edge2:
                        edge2.weight += 1
                        db.session.add(edge2)
                    else:
                        new_edge = ConstellationEdge(chat_id=chat_id, source_node_id=nid_file.id, target_node_id=nid_hub.id, weight=1)
                        db.session.add(new_edge)
                else:
                    edge.weight += 1
                    db.session.add(edge)
                    
            db.session.commit()
            return jsonify({'success': True, 'id': msg_id, 'file_url': url_for('static', filename=rel_path)})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # --- API: get graph data for constellation ---
    @app.route('/api/constellation/graph/<path:chat_id>')
    def constellation_graph(chat_id):
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401
        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'MongoDB is unavailable on this Vercel instance. Check MONGODB_URI and Atlas network access.'}), 503
            mdb = _mongo_db()
            chat = mdb.chats.find_one({'chat_id': chat_id, 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            return jsonify(_mongo_graph('chat', chat_id))
        
        # Use SQLAlchemy models
        chat_id = int(chat_id)
        me = int(session.get('user_id') or 0)
        try:
            # Verify membership
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            # Get nodes
            nodes_query = ConstellationNode.query.filter_by(chat_id=chat_id).order_by(ConstellationNode.mention_count.desc()).all()
            nodes = []
            for n in nodes_query:
                nodes.append({
                    'id': n.id,
                    'label': n.label,
                    'node_type': n.node_type,
                    'mention_count': n.mention_count
                })
            
            # Get edges
            edges_query = ConstellationEdge.query.filter_by(chat_id=chat_id).all()
            edges = []
            for e in edges_query:
                edges.append({
                    'source_node_id': e.source_node_id,
                    'target_node_id': e.target_node_id,
                    'weight': e.weight
                })
            
            return jsonify({'nodes': nodes, 'edges': edges})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # --- API: delete a node from the graph ---
    @app.route('/api/constellation/node/<path:chat_id>/<path:node_id>', methods=['DELETE'])
    def constellation_delete_node(chat_id, node_id):
        if 'user' not in session and 'user_id' not in session:
            return jsonify({'error': 'auth required'}), 401

        if _mongo_available():
            current = _mongo_current_user()
            if not current:
                return jsonify({'error': 'MongoDB is unavailable on this Vercel instance. Check MONGODB_URI and Atlas network access.'}), 503
            mdb = _mongo_db()
            chat = mdb.chats.find_one({'chat_id': str(chat_id), 'participants': current['_id']})
            if not chat:
                return jsonify({'error': 'forbidden'}), 403
            mdb.graph_nodes.delete_one({'chat_id': str(chat_id), 'label_lc': str(node_id)})
            mdb.graph_edges.delete_many({'chat_id': str(chat_id), '$or': [{'source_label_lc': str(node_id)}, {'target_label_lc': str(node_id)}]})
            return jsonify({'success': True})

        me = int(session.get('user_id') or 0)
        chat_id = int(chat_id)
        node_id = int(node_id)
        try:
            # Verify membership using SQLAlchemy
            chat = ConstellationChat.query.get(chat_id)
            if not chat or me not in (chat.user1_id, chat.user2_id):
                return jsonify({'error': 'forbidden'}), 403
            
            # Delete edges
            ConstellationEdge.query.filter(
                db.and_(
                    ConstellationEdge.chat_id == chat_id,
                    db.or_(
                        ConstellationEdge.source_node_id == node_id,
                        ConstellationEdge.target_node_id == node_id
                    )
                )
            ).delete()
            
            # Delete node
            ConstellationNode.query.filter_by(chat_id=chat_id, id=node_id).delete()
            
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    # Bind to the host/port expected by PaaS providers (e.g., Render)
    # Default to 0.0.0.0 and PORT env var when available.
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
