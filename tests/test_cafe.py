import concurrent.futures

def test_cafe_book_requires_auth(client):
    res = client.post('/api/cafe/book', json={
        'date': '2026-10-10',
        'time': '14:00',
        'partySize': 2,
        'duration': 60
    })
    assert res.status_code == 401

def test_cafe_booking_success_and_cancel(auth_client):
    res = auth_client.post('/api/cafe/book', json={
        'date': '2026-10-14',
        'time': '14:00',
        'partySize': 4,
        'duration': 60,
        'note': 'Window seat'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    bid = data['booking_id']

    # Check my bookings
    res = auth_client.get('/api/cafe/bookings')
    assert res.status_code == 200
    bookings = res.get_json()
    assert any(b['id'] == bid for b in bookings)

    # Cancel booking
    res = auth_client.delete(f'/api/cafe/bookings/{bid}')
    assert res.status_code == 200
    assert res.get_json()['success'] is True

def test_cafe_capacity_limit(auth_client):
    # Book capacity (10 seats)
    res = auth_client.post('/api/cafe/book', json={
        'date': '2026-10-12',
        'time': '16:00',
        'partySize': 10,
        'duration': 60
    })
    assert res.status_code == 200

    # Overbooking should be rejected with 409
    res = auth_client.post('/api/cafe/book', json={
        'date': '2026-10-12',
        'time': '16:00',
        'partySize': 1,
        'duration': 60
    })
    assert res.status_code == 409
