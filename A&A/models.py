from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    user_tag = db.Column(db.String(4), nullable=True, unique=True)
    email = db.Column(db.String(255), nullable=True, unique=True)
    # Optional profile fields (self-healing added in app startup)
    display_name = db.Column(db.String(120))
    photo_path = db.Column(db.String(255))

class ConstellationChat(db.Model):
    __tablename__ = 'constellation_chats'
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    
    __table_args__ = (db.UniqueConstraint('user1_id', 'user2_id', name='_constellation_chat_uc'),)

class ConstellationMessage(db.Model):
    __tablename__ = 'constellation_messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text)
    file_path = db.Column(db.String(255))
    file_name = db.Column(db.String(255))
    file_type = db.Column(db.String(50))
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())

class IdeaMessage(db.Model):
    __tablename__ = 'idea_messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text)
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())

class ConstellationNode(db.Model):
    __tablename__ = 'constellation_nodes'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    label = db.Column(db.String(255), nullable=False)
    node_type = db.Column(db.String(50), default='topic')
    source_message_id = db.Column(db.Integer, db.ForeignKey('constellation_messages.id'))
    mention_count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    
    __table_args__ = (db.UniqueConstraint('chat_id', 'label', name='_constellation_node_uc'),)

class IdeaNode(db.Model):
    __tablename__ = 'idea_nodes'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    label = db.Column(db.String(255), nullable=False)
    source_message_id = db.Column(db.Integer, db.ForeignKey('idea_messages.id'))
    mention_count = db.Column(db.Integer, default=1)
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    
    __table_args__ = (db.UniqueConstraint('chat_id', 'label', name='_idea_node_uc'),)

class ConstellationEdge(db.Model):
    __tablename__ = 'constellation_edges'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    source_node_id = db.Column(db.Integer, db.ForeignKey('constellation_nodes.id'), nullable=False)
    target_node_id = db.Column(db.Integer, db.ForeignKey('constellation_nodes.id'), nullable=False)
    weight = db.Column(db.Integer, default=1)
    
    __table_args__ = (db.UniqueConstraint('chat_id', 'source_node_id', 'target_node_id', name='_constellation_edge_uc'),)

class IdeaEdge(db.Model):
    __tablename__ = 'idea_edges'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    source_node_id = db.Column(db.Integer, db.ForeignKey('idea_nodes.id'), nullable=False)
    target_node_id = db.Column(db.Integer, db.ForeignKey('idea_nodes.id'), nullable=False)
    weight = db.Column(db.Integer, default=1)
    
    __table_args__ = (db.UniqueConstraint('chat_id', 'source_node_id', 'target_node_id', name='_idea_edge_uc'),)
