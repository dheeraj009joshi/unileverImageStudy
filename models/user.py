from mongoengine import Document, StringField, EmailField, DateTimeField, BooleanField, ReferenceField, ListField
from flask_login import UserMixin
from datetime import datetime
import bcrypt
import uuid

class User(Document, UserMixin):
    """User model for study creators with authentication."""
    
    _id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    username = StringField(required=True, unique=True, max_length=50)
    email = EmailField(required=True, unique=True, max_length=100)
    name = StringField(required=True, max_length=100)
    password_hash = StringField(required=True)
    phone = StringField(max_length=20)
    date_of_birth = StringField(max_length=10)  # YYYY-MM-DD format
    is_active = BooleanField(default=True)
    is_verified = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    last_login = DateTimeField()
    
    # Relationships
    studies = ListField(ReferenceField('Study'))
    
    meta = {
        'collection': 'users',
        'indexes': [
            'username',
            'email',
            'created_at'
        ]
    }
    
    def set_password(self, password):
        """Hash and set password using bcrypt."""
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def check_password(self, password):
        """Check if provided password matches stored hash."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def get_id(self):
        """Return string ID for Flask-Login."""
        return str(self._id)
    
    def to_dict(self):
        """Convert user to dictionary for JSON serialization."""
        return {
            'id': str(self._id),
            'username': self.username,
            'email': self.email,
            'name': self.name,
            'phone': self.phone,
            'date_of_birth': self.date_of_birth,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'studies_count': len(self.studies)
        }
    
    def __repr__(self):
        return f'<User {self.username}>'
