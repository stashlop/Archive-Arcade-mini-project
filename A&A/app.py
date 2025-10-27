import os
import sqlite3
import io
import csv
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify, make_response
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
            # Ensure a default admin user exists for demo access
            try:
                from sqlalchemy.exc import SQLAlchemyError
                if not User.query.filter_by(username='admin').first():
                    admin_pw = os.getenv('ADMIN_DEFAULT_PASSWORD', 'admin123')
                    admin_user = User(username='admin', password_hash=generate_password_hash(admin_pw))
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
                # Reset and set session identity to the new user
                session.pop('user', None)
                session.pop('user_id', None)
                session['user'] = username
                session['user_id'] = new_user.id
                return redirect(url_for('home'))
        return render_template('signup.html')

    @app.route('/logout')
    def logout():
        # Clear all identity and cart data to avoid cross-user leakage
        session.pop('user', None)
        session.pop('username', None)
        session.pop('user_id', None)
        session.pop('cart', None)
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
                    ("Baldur's Gate 3", "Epic CRPG adventure with deep choices and co-op.", "RPG,Co-op", 59.99, 9.99, "images/games/Baldurs_Gate_3.jpeg"),
                    ("Alan Wake 2", "Psychological horror thriller with cinematic storytelling.", "Horror,Narrative", 49.99, 7.99, "images/games/Alan_Wake_2.jpeg"),
                    ("Cyberpunk 2077", "Open-world RPG in a neon-soaked metropolis.", "RPG,Open-World", 29.99, 6.99, "images/games/cyberpunk.jpeg"),
                    ("Red Dead Redemption 2", "Open-world western with cinematic storytelling.", "Open-World,Action", 39.99, 8.99, "images/games/red.jpeg"),
                    ("The Witcher 3", "Open-world RPG full of monsters and choices.", "RPG,Open-World", 29.99, 6.49, "images/games/witcher.jpeg"),
                    ("Disco Elysium", "A groundbreaking RPG focused on choice and investigation.", "Indie,RPG", 19.99, 4.49, "images/games/Disco.jpeg"),
                    ("Silent Hill 2 (Remake)", "Reimagined survival-horror classic.", "Horror,Survival", 39.99, 8.49, "images/games/hill.jpeg"),
                    ("God of War", "A mythic reimagining: father, son, and monsters.", "Action,Adventure", 29.99, 6.99, "images/games/god.jpeg")
                ]
                
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

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
