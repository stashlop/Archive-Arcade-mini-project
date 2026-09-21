import os
import sys
import tempfile
import pytest

# Add A&A to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'A&A')))

from app import create_app
from models import db, User

@pytest.fixture
def app():
    temp_dir = tempfile.mkdtemp()
    os.environ['INSTANCE_PATH'] = temp_dir
    os.environ['TESTING'] = '1'
    
    app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{os.path.join(temp_dir, 'arcade.db').replace('\\', '/')}"
    })
    app.instance_path = temp_dir
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_client(client, app):
    # Register and log in a test user
    client.post('/signup', data={
        'username': 'tester',
        'email': 'tester@example.com',
        'password': 'Password123!'
    }, follow_redirects=True)
    return client
