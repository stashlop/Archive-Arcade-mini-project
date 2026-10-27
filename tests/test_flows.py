"""End-to-end flows over the raw-SQL features (catalog pages, community, friends)."""


def _signup(client, username):
    client.post('/signup', data={
        'username': username,
        'email': f'{username}@example.com',
        'password': 'Password123!'
    })


def test_catalog_pages_render(auth_client):
    res = auth_client.get('/books')
    assert res.status_code == 200
    assert b'Dune' in res.data
    res = auth_client.get('/video_games')
    assert res.status_code == 200
    assert b'Cyberpunk' in res.data
    # Case-insensitive search (SQLite LIKE semantics, ILIKE on PostgreSQL)
    res = auth_client.get('/api/books?search=dune')
    assert res.status_code == 200
    assert any(b['title'] == 'Dune' for b in res.get_json())


def test_community_join_and_messages(client):
    res = client.post('/community/join', json={'email': 'fan@example.com'})
    assert res.get_json()['success'] is True
    # Joining twice is ignored rather than erroring
    res = client.post('/community/join', json={'email': 'fan@example.com'})
    assert res.get_json()['success'] is True
    res = client.get('/api/community/messages')
    assert res.status_code == 200
    assert res.get_json() == []


def test_admin_can_post_community_message(client):
    client.get('/')  # first request creates the default admin user
    client.post('/login', data={'ident': 'admin', 'password': 'admin123'})
    res = client.post('/api/community/messages', json={'content': 'Tournament on Friday'})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['id']
    msgs = client.get('/api/community/messages').get_json()
    assert msgs[0]['content'] == 'Tournament on Friday'
    assert msgs[0]['author'] == 'admin'
    assert client.get('/admin').status_code == 200


def test_friend_request_creates_chat(app):
    alice, bob = app.test_client(), app.test_client()
    _signup(alice, 'alice')
    _signup(bob, 'bob')
    with app.app_context():
        from models import User
        bob_tag = User.query.filter_by(username='bob').first().user_tag

    res = alice.post('/api/constellation/friends/request', json={'handle': f'bob#{bob_tag}'})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['status'] == 'pending'

    reqs = bob.get('/api/constellation/friends/requests').get_json()
    incoming = [r for r in reqs if r['direction'] == 'incoming']
    req_id = incoming[0]['id']
    res = bob.post('/api/constellation/friends/respond', json={'request_id': req_id, 'action': 'accept'})
    assert res.status_code == 200, res.get_json()

    with app.app_context():
        from models import ConstellationChat
        assert ConstellationChat.query.count() == 1
