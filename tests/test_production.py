"""Regression tests for production hardening (auth, admin rights, error handling)."""
import os

from app import _shared_instance_secret


def _signup(client, username, email=None, password='Password123!'):
    return client.post('/signup', data={
        'username': username,
        'email': email or f'{username}@example.com',
        'password': password,
    })


def test_healthz(client):
    res = client.get('/healthz')
    assert res.status_code == 200
    assert res.get_json() == {'status': 'ok'}


def test_unknown_page_renders_404(client):
    res = client.get('/definitely-not-here')
    assert res.status_code == 404
    assert b'Page not found' in res.data
    res = client.get('/api/definitely-not-here')
    assert res.status_code == 404
    assert res.get_json() == {'error': 'Not found'}


def test_shared_secret_is_stable_across_workers(tmp_path):
    first = _shared_instance_secret(str(tmp_path))
    second = _shared_instance_secret(str(tmp_path))
    assert first and first == second
    assert len(first) == 64


def test_username_differing_only_in_case_cannot_register(client):
    client.get('/')  # seeds the admin account
    _signup(client, 'Admin', email='impostor@example.com')
    with client.session_transaction() as sess:
        assert sess.get('user_id') is None
    # and so cannot reach the admin dashboard
    assert client.get('/admin').status_code == 302


def test_signup_validation(client):
    for username, email, password in [
        ('ab', 'short@example.com', 'Password123!'),          # username too short
        ('<script>', 'xss@example.com', 'Password123!'),     # disallowed characters
        ('validname', 'not-an-email', 'Password123!'),
        ('validname', 'valid@example.com', 'short'),         # password too short
    ]:
        _signup(client, username, email=email, password=password)
        with client.session_transaction() as sess:
            assert sess.get('user_id') is None, (username, email, password)


def test_login_honours_safe_next_only(client):
    _signup(client, 'nextuser')
    client.get('/logout')
    res = client.post('/login?next=/cafe', data={'ident': 'nextuser', 'password': 'Password123!'})
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/cafe')
    client.get('/logout')
    for bad in ('//evil.example.com', '/\t/evil.example.com', '/\\evil.example.com', 'https://evil.example.com'):
        client.get('/logout')
        res = client.post('/login', data={'ident': 'nextuser', 'password': 'Password123!', 'next': bad})
        assert res.status_code == 302
        assert 'evil.example.com' not in res.headers['Location'], bad


def test_restricted_page_redirects_with_next(client):
    res = client.get('/books')
    assert res.status_code == 302
    assert '/login?next=' in res.headers['Location']
    assert client.get('/api/books').status_code == 401


def test_seed_and_manual_purchase_endpoints_are_admin_only(auth_client):
    assert auth_client.post('/admin/seed_games').status_code == 403
    res = auth_client.post('/api/purchase', json={'items': [{'title': 'x'}], 'total': 99999})
    assert res.status_code == 403


def test_chat_requires_accepted_friendship(app):
    alice, bob = app.test_client(), app.test_client()
    _signup(alice, 'alice2')
    _signup(bob, 'bob2')
    with app.app_context():
        from models import User
        bob_id = User.query.filter_by(username='bob2').first().id
    res = alice.get(f'/api/constellation/chat/{bob_id}')
    assert res.status_code == 403
    assert alice.get('/api/constellation/chat/not-a-number').status_code == 404


def test_cart_rejects_malformed_payload(auth_client):
    res = auth_client.post('/api/cart/add', json={'itemType': 'book', 'itemId': 'abc', 'quantity': 'x'})
    assert res.status_code == 400
    res = auth_client.post('/api/cart/add', data='not json', content_type='application/json')
    assert res.status_code == 400


def test_server_errors_do_not_leak_details(auth_client, app, monkeypatch):
    import dbconn

    def boom(*args, **kwargs):
        raise RuntimeError('secret-internal-detail')

    monkeypatch.setattr(dbconn, 'connect', boom)
    res = auth_client.get('/api/cafe/bookings')
    assert res.status_code == 500
    assert b'secret-internal-detail' not in res.data


def test_network_status_hides_host_details_in_production(client, app, monkeypatch):
    monkeypatch.setenv('TESTING', '0')
    app.config['TESTING'] = False
    data = client.get('/api/network-status').get_json()
    assert data == {'status': 'online'}
