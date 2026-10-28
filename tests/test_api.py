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

def test_books_page_reads_unified_db(auth_client):
    res = auth_client.get('/books')
    assert res.status_code == 200

def test_video_games_page_games_can_be_added_to_cart(auth_client):
    res = auth_client.get('/video_games')
    assert res.status_code == 200

    games = auth_client.get('/api/games').get_json()
    assert games
    res = auth_client.post('/api/cart/add', json={
        'itemType': 'game',
        'itemId': games[0]['id'],
        'action': 'buy',
        'quantity': 1
    })
    assert res.status_code == 200
    assert res.get_json()['success'] is True

def test_community_messages_feed(client):
    res = client.get('/api/community/messages')
    assert res.status_code == 200
    assert res.get_json() == []
