import concurrent.futures
from datetime import date, timedelta


def _next_weekday(weekday, weeks_ahead=1):
    """An upcoming date on the given weekday (Monday=0), so tests never book in the past."""
    today = date.today()
    return (today + timedelta(days=(weekday - today.weekday()) % 7 + 7 * weeks_ahead)).isoformat()

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
        'date': _next_weekday(2),
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
        'date': _next_weekday(0),
        'time': '16:00',
        'partySize': 10,
        'duration': 60
    })
    assert res.status_code == 200

    # Overbooking should be rejected with 409
    res = auth_client.post('/api/cafe/book', json={
        'date': _next_weekday(0),
        'time': '16:00',
        'partySize': 1,
        'duration': 60
    })
    assert res.status_code == 409


def test_cafe_booking_rejects_invalid_input(auth_client):
    monday = _next_weekday(0)
    cases = [
        {'date': '2020-01-06', 'time': '14:00', 'partySize': 2},     # past date
        {'date': 'not-a-date', 'time': '14:00', 'partySize': 2},
        {'date': monday, 'time': '25:00', 'partySize': 2},           # bad time
        {'date': monday, 'time': '08:00', 'partySize': 2},           # before opening
        {'date': monday, 'time': '21:30', 'partySize': 2, 'duration': 60},  # runs past closing
        {'date': monday, 'time': '14:00', 'partySize': 'lots'},      # not a number
        {'date': monday, 'time': '14:00', 'partySize': 50},          # over capacity
    ]
    for payload in cases:
        res = auth_client.post('/api/cafe/book', json=payload)
        assert res.status_code == 400, (payload, res.get_json())
        assert 'error' in res.get_json()


def test_cafe_slots_validates_date(auth_client):
    assert auth_client.get('/api/cafe/slots?date=garbage').status_code == 400
    res = auth_client.get(f'/api/cafe/slots?date={_next_weekday(0)}')
    assert res.status_code == 200
    assert res.get_json()['slots']
