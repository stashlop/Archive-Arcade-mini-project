import sqlite3, os, json
from flask import Blueprint, current_app, jsonify, request, session
from pathlib import Path
from datetime import datetime

games_bp = Blueprint('games_api', __name__)

def get_db_path():
    inst = current_app.instance_path if hasattr(current_app, 'instance_path') else 'instance'
    Path(inst).mkdir(parents=True, exist_ok=True)
    return os.path.join(inst, 'games.db')

def init_purchase_history_db(conn):
    """
    Ensure purchase_history table exists and contains all expected columns.
    Adds missing columns via ALTER TABLE to avoid runtime insert failures.
    """
    cur = conn.cursor()
    # Create table if it doesn't exist (without assuming all columns are present)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            purchase_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            buyer_name TEXT,
            buyer_email TEXT,
            items_json TEXT NOT NULL
        )
        """
    )
    conn.commit()

    # Introspect existing columns
    cur.execute("PRAGMA table_info(purchase_history)")
    cols = {row[1] for row in cur.fetchall()}

    # Add missing columns as needed
    if 'payment_method' not in cols:
        cur.execute("ALTER TABLE purchase_history ADD COLUMN payment_method TEXT")
        conn.commit()

def init_db(conn):
    cur = conn.cursor()
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
    conn.commit()
    # Also initialize purchase history table
    init_purchase_history_db(conn)

def row_to_game(r):
    return {
        "id": r["id"],
        "title": r["title"],
        "description": r["description"],
        "category": r["category"] or "",
        "buy_price": float(r["buy_price"]) if r["buy_price"] is not None else 0.0,
        "rent_price": float(r["rent_price"]) if r["rent_price"] is not None else 0.0,
        "image": r["image"]
    }

@games_bp.route('/api/games', methods=['GET'])
def list_games():
    dbp = get_db_path()
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    cur = conn.cursor()
    cur.execute("SELECT * FROM games ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return jsonify([row_to_game(r) for r in rows])

@games_bp.route('/admin/seed_games', methods=['POST'])
def seed_games():
    """
    Seed some sample games into the DB. Call once (POST) from CLI or browser for setup.
    """
    sample = [
        ("Baldur's Gate 3", "Epic CRPG adventure with deep choices and co-op.", "RPG,Co-op", 59.99, 9.99, "images/games/Baldurs_Gate_3.jpeg"),
        ("Alan Wake 2", "Psychological horror thriller with cinematic storytelling.", "Horror,Narrative", 49.99, 7.99, "images/games/Alan_Wake_2.jpeg"),
        ("Cyberpunk 2077", "Open-world RPG in a neon-soaked metropolis.", "RPG,Open-World", 29.99, 6.99, "images/games/cyberpunk.jpeg"),
        ("Red Dead Redemption 2", "Open-world western with cinematic storytelling.", "Open-World,Action", 39.99, 8.99, "images/games/red.jpeg"),
        ("The Witcher 3: Wild Hunt", "Open-world RPG full of monsters and choices.", "RPG,Open-World", 29.99, 6.49, "images/games/witcher.jpeg"),
        ("Disco Elysium", "A groundbreaking RPG focused on choice and investigation.", "Indie,RPG", 19.99, 4.49, "images/games/Disco.jpeg"),
        ("Silent Hill 2 (Remake)", "Reimagined survival-horror classic.", "Horror,Survival", 39.99, 8.49, "images/games/hill.jpeg"),
        ("God of War (2018)", "A mythic reimagining: father, son, and monsters.", "Action,Adventure", 29.99, 6.99, "images/games/god.jpeg")
    ]
    dbp = get_db_path()
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    cur = conn.cursor()
    cur.executemany("INSERT INTO games (title, description, category, buy_price, rent_price, image) VALUES (?,?,?,?,?,?)", sample)
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "seeded": len(sample)}), 201

@games_bp.route('/api/purchase', methods=['POST'])
def save_purchase():
    """Save a purchase to the database"""
    if not session.get('user_id'):
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        data = request.json
        if not data or 'items' not in data or not data['items']:
            return jsonify({"error": "Invalid purchase data"}), 400
            
        user_id = session.get('user_id')
        purchase_date = data.get('date') or datetime.utcnow().isoformat()
        total_amount = float(data.get('total', 0))
        buyer_name = data.get('buyer', {}).get('name', '')
        buyer_email = data.get('buyer', {}).get('email', '')
        payment_method = (data.get('paymentMethod') or 'Demo').strip()
        items_json = json.dumps(data.get('items', []))
        
        dbp = get_db_path()
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        
        # Ensure both tables exist
        init_db(conn)
        
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO purchase_history 
               (user_id, purchase_date, total_amount, buyer_name, buyer_email, payment_method, items_json) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, purchase_date, total_amount, buyer_name, buyer_email, payment_method, items_json)
        )
        conn.commit()
        purchase_id = cur.lastrowid
        conn.close()
        
        return jsonify({"success": True, "purchase_id": purchase_id}), 201
        
    except Exception as e:
        current_app.logger.error(f"Purchase error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@games_bp.route('/api/purchase/history', methods=['GET'])
def get_purchase_history():
    """Get purchase history for the current user"""
    if not session.get('user_id'):
        return jsonify({"error": "Authentication required"}), 401
    
    try:
        user_id = session.get('user_id')
        dbp = get_db_path()
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        
        # Ensure both tables exist
        init_db(conn)
        
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM purchase_history 
               WHERE user_id = ? 
               ORDER BY purchase_date DESC""",
            (user_id,)
        )
        rows = cur.fetchall()
        
        history = []
        for row in rows:
            items = json.loads(row['items_json'])
            history.append({
                "id": row['id'],
                "date": row['purchase_date'],
                "total": row['total_amount'],
                "paymentMethod": row['payment_method'] if 'payment_method' in row.keys() else None,
                "buyer": {
                    "name": row['buyer_name'],
                    "email": row['buyer_email']
                },
                "items": items
            })
        
        conn.close()
        return jsonify(history)
        
    except Exception as e:
        current_app.logger.error(f"Get history error: {str(e)}")
        return jsonify({"error": str(e)}), 500