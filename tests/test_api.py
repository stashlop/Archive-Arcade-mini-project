from models import Book, Game, db

def test_books_api(auth_client, app):
    with app.app_context():
        b1 = Book(title='One Piece Special', author='Oda', category='Manga', genre='Adventure', buy_price=10.0)
        b2 = Book(title='Clean Code Special', author='Martin', category='Technical', genre='Programming', buy_price=30.0)
        db.session.add_all([b1, b2])
        db.session.commit()

    res = auth_client.get('/api/books')
    assert res.status_code == 200
    books = res.get_json()
    assert len(books) >= 2

    res = auth_client.get('/api/books?category=Manga')
    assert res.status_code == 200
    filtered = res.get_json()
    assert all(b['category'] == 'Manga' for b in filtered)

def test_games_api(client, app):
    with app.app_context():
        g1 = Game(title='Zelda', category='Action', buy_price=50.0)
        db.session.add(g1)
        db.session.commit()

    res = client.get('/api/games')
    assert res.status_code == 200
    games = res.get_json()
    assert isinstance(games, list)
