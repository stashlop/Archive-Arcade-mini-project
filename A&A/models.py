from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    user_tag = db.Column(db.String(4), nullable=True, unique=True)
    email = db.Column(db.String(255), nullable=True, unique=True)
    display_name = db.Column(db.String(120))
    photo_path = db.Column(db.String(255))
    created_at = db.Column(db.String(255), default=lambda: datetime.utcnow().isoformat())

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    genre = db.Column(db.String(100))
    buy_price = db.Column(db.Float, default=0.0)
    rent_price = db.Column(db.Float, default=0.0)
    image = db.Column(db.String(255))
    isbn = db.Column(db.String(50))
    pages = db.Column(db.Integer)
    publication_year = db.Column(db.Integer)

class Game(db.Model):
    __tablename__ = 'games'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    buy_price = db.Column(db.Float, default=0.0)
    rent_price = db.Column(db.Float, default=0.0)
    image = db.Column(db.String(255))

class PurchaseHistory(db.Model):
    __tablename__ = 'purchase_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    purchase_date = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    total_amount = db.Column(db.Float, nullable=False)
    buyer_name = db.Column(db.String(255))
    buyer_email = db.Column(db.String(255))
    items_json = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(100), default='Demo')
    delivery_status = db.Column(db.String(100), default='Processing')

class CafeBooking(db.Model):
    __tablename__ = 'cafe_bookings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    time = db.Column(db.String(50), nullable=False)
    party_size = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.Text)
    status = db.Column(db.String(50), nullable=False, default='confirmed')
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    duration_minutes = db.Column(db.Integer, default=60)
    canceled_at = db.Column(db.String(255), nullable=True)

class CommunitySubscriber(db.Model):
    __tablename__ = 'community_subscribers'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    joined_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    display_name = db.Column(db.String(120), nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)

class CommunityMessage(db.Model):
    __tablename__ = 'community_messages'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('community_subscribers.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())

class FriendRequest(db.Model):
    __tablename__ = 'friend_requests'
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='pending')
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    responded_at = db.Column(db.String(255), nullable=True)
    
    __table_args__ = (db.UniqueConstraint('requester_id', 'receiver_id', name='_friend_request_uc'),)

class ConstellationChat(db.Model):
    __tablename__ = 'constellation_chats'
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())
    
    __table_args__ = (db.UniqueConstraint('user1_id', 'user2_id', name='_constellation_chat_uc'),)

class ConstellationMessage(db.Model):
    __tablename__ = 'constellation_messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text)
    file_path = db.Column(db.String(255))
    file_name = db.Column(db.String(255))
    file_type = db.Column(db.String(50))
    created_at = db.Column(db.String(255), nullable=False, default=lambda: datetime.utcnow().isoformat())

class IdeaMessage(db.Model):
    __tablename__ = 'idea_messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('constellation_chats.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
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
