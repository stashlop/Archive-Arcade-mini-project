from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # Optional profile fields (self-healing added in app startup)
    display_name = db.Column(db.String(120))
    photo_path = db.Column(db.String(255))