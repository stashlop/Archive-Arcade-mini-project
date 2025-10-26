import os
import sqlite3
from flask import Blueprint, request, jsonify, current_app, session

books_bp = Blueprint('books_api', __name__, url_prefix='/api')

def init_books_db():
    """Initialize books database with sample data"""
    try:
        dbp = os.path.join(current_app.instance_path, 'books.db')
        conn = sqlite3.connect(dbp)
        cur = conn.cursor()
        
        # Create books table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                description TEXT,
                category TEXT,
                genre TEXT,
                buy_price REAL DEFAULT 0,
                rent_price REAL DEFAULT 0,
                image TEXT,
                isbn TEXT,
                pages INTEGER,
                publication_year INTEGER
            )
        """)
        
        # Check if table is empty
        cur.execute("SELECT COUNT(*) FROM books")
        if cur.fetchone()[0] == 0:
            # Seed with sample books
            sample_books = [
                # Manga
                ("One Piece Vol. 1", "Eiichiro Oda", "...", "Manga", "Adventure,Shounen", 9.99, 2.99, "onepiece.jpg", "978-1421506333", 200, 1999),
                ("Attack on Titan Vol. 1", "Hajime Isayama",
                 "Humanity fights for survival against giant titans.",
                 "Manga", "Action,Drama", 10.99, 3.49, "aot1.jpeg",
                 "978-1612620244", 192, 2012),
                ("Demon Slayer Vol. 1", "Koyoharu Gotouge", "...", "Manga", "Action,Supernatural", 9.99, 2.99, "demonslayer.jpg", "978-1974700523", 192, 2018),
                
                # Light Novels
                ("Sword Art Online Vol. 1", "Reki Kawahara", "Trapped in a virtual MMORPG where death is real.", "Light Novel", "Sci-Fi,Romance", 14.99, 4.99, "sao.jpg", "978-0316371247", 240, 2014),
                ("Re:Zero Vol. 1", "Tappei Nagatsuki", "Subaru discovers he can return from death in another world.", "Light Novel", "Fantasy,Psychological", 14.99, 4.99, "rezero.jpg", "978-0316315302", 256, 2016),
                ("Overlord Vol. 1", "Kugane Maruyama", "A player becomes trapped as his undead character in a game world.", "Light Novel", "Fantasy,Dark", 14.99, 4.99, "overlord.jpg", "978-0316272247", 272, 2016),
                
                # Traditional Novels
                ("Dune", "Frank Herbert", "Epic sci-fi saga on the desert planet Arrakis.", "Novel", "Science Fiction", 16.99, 5.99, "dune.jpg", "978-0441172719", 688, 1965),
                ("The Hobbit", "J.R.R. Tolkien", "Bilbo Baggins' unexpected journey to reclaim a treasure.", "Novel", "Fantasy", 14.99, 4.99, "hobbit.jpg", "978-0547928227", 300, 1937),
                ("1984", "George Orwell", "Dystopian masterpiece about surveillance and control.", "Novel", "Dystopian,Classic", 13.99, 4.49, "1984.jpg", "978-0452284234", 328, 1949),
                
                # Technical Books
                ("Clean Code", "Robert C. Martin", "A handbook of agile software craftsmanship.", "Technical", "Programming", 49.99, 12.99, "cleancode.jpg", "978-0132350884", 464, 2008),
                ("Design Patterns", "Gang of Four", "Elements of reusable object-oriented software.", "Technical", "Programming", 54.99, 14.99, "designpatterns.jpg", "978-0201633612", 395, 1994),
                
                # Non-Fiction
                ("Sapiens", "Yuval Noah Harari", "A brief history of humankind and our species' journey.", "Non-Fiction", "History,Science", 18.99, 6.99, "sapiens.jpg", "978-0062316097", 443, 2014),
                ("Atomic Habits", "James Clear", "Tiny changes that create remarkable results.", "Non-Fiction", "Self-Help", 16.99, 5.99, "atomichabits.jpg", "978-0735211292", 320, 2018)
            ]
            
            cur.executemany("""
                INSERT INTO books (title, author, description, category, genre, buy_price, rent_price, image, isbn, pages, publication_year) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, sample_books)
            conn.commit()
            
        conn.close()
        return True
    except Exception as e:
        print(f"Database error: {e}")
        return False

@books_bp.route('/books')
def get_books():
    """Get all books with optional filtering"""
    try:
        dbp = os.path.join(current_app.instance_path, 'books.db')
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        
        # Get filter parameters
        category = request.args.get('category')
        genre = request.args.get('genre')
        search = request.args.get('search')
        
        query = "SELECT * FROM books WHERE 1=1"
        params = []
        
        if category:
            query += " AND category = ?"
            params.append(category)
            
        if genre:
            query += " AND genre LIKE ?"
            params.append(f'%{genre}%')
            
        if search:
            query += " AND (title LIKE ? OR author LIKE ? OR description LIKE ?)"
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
            
        query += " ORDER BY title"
        
        cur = conn.cursor()
        cur.execute(query, params)
        books = [dict(row) for row in cur.fetchall()]
        conn.close()
        
        return jsonify(books)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@books_bp.route('/books/<int:book_id>')
def get_book(book_id):
    """Get a specific book by ID"""
    try:
        dbp = os.path.join(current_app.instance_path, 'books.db')
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        
        cur = conn.cursor()
        cur.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        book = cur.fetchone()
        conn.close()
        
        if book:
            return jsonify(dict(book))
        else:
            return jsonify({'error': 'Book not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@books_bp.route('/purchase/book', methods=['POST'])
def purchase_book():
    """Handle book purchase"""
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
        
    data = request.get_json()
    book_id = data.get('bookId')
    
    if not book_id:
        return jsonify({'error': 'Book ID required'}), 400
    
    try:
        # Get book details
        dbp = os.path.join(current_app.instance_path, 'books.db')
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        
        cur = conn.cursor()
        cur.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        book = cur.fetchone()
        
        if not book:
            conn.close()
            return jsonify({'error': 'Book not found'}), 404
            
        # Here you would typically:
        # 1. Process payment
        # 2. Add to user's library
        # 3. Send confirmation email
        # For now, we'll just simulate success
        
        conn.close()
        return jsonify({
            'success': True,
            'message': f'Successfully purchased "{book["title"]}" for ${book["buy_price"]}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@books_bp.route('/rent/book', methods=['POST'])
def rent_book():
    """Handle book rental"""
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
        
    data = request.get_json()
    book_id = data.get('bookId')
    
    if not book_id:
        return jsonify({'error': 'Book ID required'}), 400
    
    try:
        dbp = os.path.join(current_app.instance_path, 'books.db')
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        
        cur = conn.cursor()
        cur.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        book = cur.fetchone()
        
        if not book:
            conn.close()
            return jsonify({'error': 'Book not found'}), 404
            
        conn.close()
        return jsonify({
            'success': True,
            'message': f'Successfully rented "{book["title"]}" for ${book["rent_price"]} (7 days)'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500