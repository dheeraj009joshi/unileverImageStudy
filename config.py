import os
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv()

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    MONGODB_SETTINGS = {
        'host': os.environ.get('MONGODB_URI') or 'mongodb+srv://dlovej009:Dheeraj2006@cluster0.dnu8vna.mongodb.net/iped_system'
    }
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Azure Blob Storage Configuration
    AZURE_STORAGE_CONNECTION_STRING = os.environ.get('AZURE_STORAGE_CONNECTION_STRING') or "DefaultEndpointsProtocol=https;AccountName=printxd;AccountKey=CaL/3SmhK8iKVM02i/cIN1VgE3058lyxRnCxeRd2J1k/9Ay6I67GC2CMnW//lJhNl+71WwxYXHnC+AStkbW1Jg==;EndpointSuffix=core.windows.net"
    AZURE_CONTAINER_NAME = os.environ.get('AZURE_CONTAINER_NAME') or "mf2"
    
    # Session and CSRF settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour CSRF token expiry

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True  # Require HTTPS in production

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
