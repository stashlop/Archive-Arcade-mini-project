import json
from models import Book, Game, db

def test_unauthorized_cart_add(client):
    res = client.post('/api/cart/add', json={
        'itemType': 'book',
        'itemId': 1,
        'action': 'buy',
        'quantity': 1
    })
    assert res.status_code == 401

def test_cart_workflow(auth_client, app):
    # Seed or fetch book and game in unified database
    with app.app_context():
        book = Book.query.first()
        if not book:
            book = Book(title='Clean Code Test', author='Robert Martin', buy_price=10.0, rent_price=3.0)
            db.session.add(book)
            db.session.commit()
        book_id = book.id

    # Add book to cart
    res = auth_client.post('/api/cart/add', json={
        'itemType': 'book',
        'itemId': book_id,
        'action': 'buy',
        'quantity': 2
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['count'] == 2

    # Get cart
    res = auth_client.get('/api/cart')
    assert res.status_code == 200
    data = res.get_json()
    assert len(data['items']) == 1
    assert data['total_quantity'] == 2

    # Checkout
    res = auth_client.post('/api/cart/checkout', json={
        'buyer': {'name': 'Test Buyer', 'email': 'buyer@example.com'},
        'paymentMethod': 'CreditCard'
    })
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # Cart should be empty after checkout
    res = auth_client.get('/api/cart')
    assert res.get_json()['total_quantity'] == 0
