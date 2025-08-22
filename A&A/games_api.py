from flask import Blueprint, current_app, jsonify, request
import sqlite3
import os
from pathlib import Path

games_bp = Blueprint('games_api', __name__)

def get_db_path():
    inst = current_app.instance_path if hasattr(current_app, 'instance_path') else 'instance'
    Path(inst).mkdir(parents=True, exist_ok=True)
    return os.path.join(inst, 'games.db')

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
        ("Baldur's Gate 3", "Epic CRPG adventure with deep choices and co-op.", "RPG,Co-op", 59.99, 9.99, "Baldurs_Gate_3.jpeg"),
        ("Alan Wake 2", "Psychological horror thriller with cinematic storytelling.", "Horror,Narrative", 49.99, 7.99, "Alan_Wake_2.jpeg"),
        ("Cyberpunk 2077", "Open-world RPG in a neon-soaked metropolis.", "RPG,Open-World", 29.99, 6.99, "cyberpunk.jpeg"),
        ("Red Dead Redemption 2", "Open-world western with cinematic storytelling.", "Open-World,Action", 39.99, 8.99, "red.jpeg"),
        ("The Witcher 3: Wild Hunt", "Open-world RPG full of monsters and choices.", "RPG,Open-World", 29.99, 6.49, "witcher.jpeg"),
        ("Disco Elysium", "A groundbreaking RPG focused on choice and investigation.", "Indie,RPG", 19.99, 4.49, "Disco.jpeg"),
        ("Silent Hill 2 (Remake)", "Reimagined survival-horror classic.", "Horror,Survival", 39.99, 8.49, "hill.jpeg"),
        ("God of War (2018)", "A mythic reimagining: father, son, and monsters.", "Action,Adventure", 29.99, 6.99, "god.jpeg")
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