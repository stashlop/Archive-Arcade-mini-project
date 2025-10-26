import os
import json
import sqlite3
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app

cart_bp = Blueprint('cart_api', __name__, url_prefix='/api/cart')

def _ensure_cart():
    if 'cart' not in session:
        session['cart'] = {'items': []}
    return session['cart']

def _item_key(item_type, item_id, action):
    return f"{item_type}-{item_id}-{action}"

def _fetch_item_details(item_type, item_id, action):
    # Returns title and unit_price for given item
    if item_type == 'book':
        dbp = os.path.join(current_app.instance_path, 'books.db')
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, title, buy_price, rent_price FROM books WHERE id = ?", (item_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        unit_price = row['buy_price'] if action == 'buy' else row['rent_price']
        return {'title': row['title'], 'unit_price': float(unit_price)}
    elif item_type == 'game':
        dbp = os.path.join(current_app.instance_path, 'games.db')
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, title, buy_price, rent_price FROM games WHERE id = ?", (item_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        # If your games table uses different column names, adjust above fields accordingly
        unit_price = row['buy_price'] if action == 'buy' else row['rent_price']
        return {'title': row['title'], 'unit_price': float(unit_price)}
    return None

def _totals(items):
    subtotal = sum(i['unit_price'] * i['quantity'] for i in items)
    total_qty = sum(i['quantity'] for i in items)
    return float(round(subtotal, 2)), int(total_qty)

def _games_db_path():
    inst = current_app.instance_path if hasattr(current_app, 'instance_path') else 'instance'
    os.makedirs(inst, exist_ok=True)
    return os.path.join(inst, 'games.db')

def _ensure_purchase_history_table(conn):
    cur = conn.cursor()
    # Create table if it doesn't exist (base columns)
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

    # Ensure payment_method column exists for compatibility with cart checkout
    cur.execute("PRAGMA table_info(purchase_history)")
    existing = {row[1] for row in cur.fetchall()}
    if 'payment_method' not in existing:
        cur.execute("ALTER TABLE purchase_history ADD COLUMN payment_method TEXT")
        conn.commit()

@cart_bp.route('', methods=['GET'])
def get_cart():
    cart = _ensure_cart()
    items = cart['items']
    subtotal, total_qty = _totals(items)
    return jsonify({
        'items': items,
        'subtotal': subtotal,
        'total_quantity': total_qty
    })

@cart_bp.route('/count', methods=['GET'])
def cart_count():
    cart = _ensure_cart()
    _, total_qty = _totals(cart['items'])
    return jsonify({'count': total_qty})

@cart_bp.route('/add', methods=['POST'])
def add_to_cart():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json(force=True)
    item_type = data.get('itemType')  # 'book' or 'game'
    item_id = data.get('itemId')
    action = data.get('action', 'buy')  # 'buy' or 'rent'
    quantity = int(data.get('quantity', 1))

    if item_type not in ('book', 'game') or not item_id or action not in ('buy', 'rent') or quantity < 1:
        return jsonify({'error': 'Invalid payload'}), 400

    details = _fetch_item_details(item_type, item_id, action)
    if not details:
        return jsonify({'error': 'Item not found'}), 404

    cart = _ensure_cart()
    key = _item_key(item_type, item_id, action)

    # Merge item if same key exists
    for it in cart['items']:
        if it['key'] == key:
            it['quantity'] += quantity
            session.modified = True
            subtotal, total_qty = _totals(cart['items'])
            return jsonify({'success': True, 'count': total_qty, 'subtotal': subtotal})

    cart['items'].append({
        'key': key,
        'item_type': item_type,
        'item_id': item_id,
        'title': details['title'],
        'action': action,
        'unit_price': details['unit_price'],
        'quantity': quantity
    })
    session.modified = True
    subtotal, total_qty = _totals(cart['items'])
    return jsonify({'success': True, 'count': total_qty, 'subtotal': subtotal})

@cart_bp.route('/remove', methods=['POST'])
def remove_from_cart():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json(force=True)
    key = data.get('key')
    if not key:
        return jsonify({'error': 'key required'}), 400

    cart = _ensure_cart()
    before = len(cart['items'])
    cart['items'] = [it for it in cart['items'] if it['key'] != key]
    session.modified = True
    subtotal, total_qty = _totals(cart['items'])
    return jsonify({'success': True, 'removed': before - len(cart['items']), 'count': total_qty, 'subtotal': subtotal})

@cart_bp.route('/clear', methods=['POST'])
def clear_cart():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    session['cart'] = {'items': []}
    session.modified = True
    return jsonify({'success': True, 'count': 0, 'subtotal': 0.0})

@cart_bp.route('/checkout', methods=['POST'])
def checkout():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    cart = _ensure_cart()
    if not cart['items']:
        return jsonify({'error': 'Cart is empty'}), 400

    # Demo payment flow: accept optional buyer/payment info and always succeed
    payload = {}
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    buyer = payload.get('buyer', {}) if isinstance(payload.get('buyer'), dict) else {}
    payment_method = (payload.get('paymentMethod') or 'Demo').strip()

    items = cart['items']
    subtotal, _ = _totals(items)

    # Persist purchase history into games.db (shared demo history store)
    try:
        dbp = _games_db_path()
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        _ensure_purchase_history_table(conn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO purchase_history (user_id, purchase_date, total_amount, buyer_name, buyer_email, payment_method, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(session.get('user_id') or 0),
                datetime.utcnow().isoformat(),
                float(subtotal),
                buyer.get('name', ''),
                buyer.get('email', ''),
                payment_method,
                json.dumps(items)
            )
        )
        conn.commit()
        purchase_id = cur.lastrowid
        conn.close()
    except Exception as e:
        current_app.logger.exception(f"Failed to save purchase history: {e}")
        return jsonify({'error': 'Failed to record purchase'}), 500

    # Clear the cart after successful demo checkout
    session['cart'] = {'items': []}
    session.modified = True
    return jsonify({'success': True, 'message': 'Checkout complete. Thank you!', 'purchase_id': purchase_id})