from models import User

def test_signup(client, app):
    res = client.post('/signup', data={
        'username': 'alice',
        'email': 'alice@example.com',
        'password': 'SecretPassword123'
    }, follow_redirects=True)
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('user') == 'alice'
        assert sess.get('username') == 'alice'
        assert sess.get('user_id') is not None

    with app.app_context():
        user = User.query.filter_by(username='alice').first()
        assert user is not None
        assert user.email == 'alice@example.com'

def test_login_logout(client):
    # First sign up
    client.post('/signup', data={
        'username': 'bob',
        'email': 'bob@example.com',
        'password': 'BobPassword123'
    }, follow_redirects=True)
    
    # Log out
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('user') is None
        assert sess.get('user_id') is None

    # Log back in
    res = client.post('/login', data={
        'ident': 'bob',
        'password': 'BobPassword123'
    }, follow_redirects=True)
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('user') == 'bob'
        assert sess.get('username') == 'bob'
        assert sess.get('user_id') is not None

def test_invalid_login(client):
    res = client.post('/login', data={
        'ident': 'nonexistent',
        'password': 'wrong'
    }, follow_redirects=True)
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('user') is None
