import os
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv()

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    MONGODB_SETTINGS = {
        'host': os.environ.get('MONGODB_URI') or 'mongodb+srv://dlovej009:Dheeraj2006@cluster0.dnu8vna.mongodb.net/RDE_system'
    }
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # Increased to 100MB for multiple file uploads
    MAX_CONTENT_LENGTH_PER_FILE = 16 * 1024 * 1024  # 16MB max per individual file
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Request size limits for large forms
    MAX_CONTENT_LENGTH_TOTAL = 200 * 1024 * 1024  # 200MB total request size
    MAX_CONTENT_LENGTH_FORMS = 50 * 1024 * 1024  # 50MB for form data
    
    # Azure Blob Storage Configuration
    AZURE_STORAGE_CONNECTION_STRING = os.environ.get('AZURE_STORAGE_CONNECTION_STRING') or "DefaultEndpointsProtocol=https;AccountName=printxd;AccountKey=CaL/3SmhK8iKVM02i/cIN1VgE3058lyxRnCxeRd2J1k/9Ay6I67GC2CMnW//lJhNl+71WwxYXHnC+AStkbW1Jg==;EndpointSuffix=core.windows.net"
    AZURE_CONTAINER_NAME = os.environ.get('AZURE_CONTAINER_NAME') or "mf2"
    
    # Parallel upload configuration
    AZURE_UPLOAD_MAX_WORKERS = int(os.environ.get('AZURE_UPLOAD_MAX_WORKERS', '30'))  # Number of parallel upload workers for ultra-fast uploads
    
    # Session and CSRF settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour CSRF token expiry
    
    # Dynamic Application Configuration
    APP_NAME = os.environ.get('APP_NAME', 'Mindsurve')
    APP_DESCRIPTION = os.environ.get('APP_DESCRIPTION', 'Professional RDE Study System for Research and Data Collection')
    APP_TAGLINE = os.environ.get('APP_TAGLINE', 'Conduct cutting-edge research with our advanced Rule Developing Experimentatio platform')
    APP_SUBTAGLINE = os.environ.get('APP_SUBTAGLINE', 'Create, manage, and analyze studies with enterprise-grade tools')
    
    # Company Information
    COMPANY_NAME = os.environ.get('COMPANY_NAME', 'Mindsurve')
    COMPANY_YEAR = os.environ.get('COMPANY_YEAR', '2024')
    COMPANY_WEBSITE = os.environ.get('COMPANY_WEBSITE', 'https://Mindsurve.com')
    COMPANY_EMAIL = os.environ.get('COMPANY_EMAIL', 'contact@Mindsurve.com')
    
    # Feature Descriptions
    FEATURES = {
        'algorithm': {
            'title': 'Advanced RDE Algorithm',
            'description': 'Sophisticated Rule Developing Experimentatio with balanced matrix generation for optimal research outcomes.',
            'icon': '🧠'
        },
        'analytics': {
            'title': 'Real-time Analytics',
            'description': 'Comprehensive analytics and reporting tools to track study progress and analyze results.',
            'icon': '📊'
        },
        'mobile': {
            'title': 'Mobile Optimized',
            'description': 'Fully responsive design that works seamlessly across all devices and screen sizes.',
            'icon': '📱'
        }
    }
    
    # Social Media Links
    SOCIAL_LINKS = {
        'twitter': os.environ.get('SOCIAL_TWITTER', 'https://twitter.com/Mindsurve'),
        'linkedin': os.environ.get('SOCIAL_LINKEDIN', 'https://linkedin.com/company/Mindsurve'),
        'github': os.environ.get('SOCIAL_GITHUB', 'https://github.com/Mindsurve'),
        'youtube': os.environ.get('SOCIAL_YOUTUBE', 'https://youtube.com/@Mindsurve')
    }
    
    # Contact Information
    CONTACT_INFO = {
        'address': os.environ.get('CONTACT_ADDRESS', '123 Research Drive, Innovation City, IC 12345'),
        'phone': os.environ.get('CONTACT_PHONE', '+1 (555) 123-4567'),
        'support_email': os.environ.get('SUPPORT_EMAIL', 'support@Mindsurve.com'),
        'sales_email': os.environ.get('SALES_EMAIL', 'sales@Mindsurve.com')
    }

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
