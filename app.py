import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from mongoengine import connect
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime
import json
    # Register blueprints
from routes.index import index_bp
from routes.auth import auth_bp
from routes.study_creation import study_creation_bp
from routes.study_participation import study_participation
from routes.dashboard import dashboard_bp
from routes.api import api_bp
    

# Import configuration
from config import config

# Import models
from models.user import User
from models.study import Study, RatingScale, StudyElement, ClassificationQuestion, IPEDParameters
from models.study_draft import StudyDraft
from models.response import StudyResponse, TaskSession

# Import forms
from forms.auth import LoginForm, RegistrationForm, PasswordResetRequestForm, PasswordResetForm, ProfileUpdateForm
from forms.study import (
    Step1aBasicDetailsForm, Step1bStudyTypeForm, Step1cRatingScaleForm,
    Step2cIPEDParametersForm, Step3aTaskGenerationForm, Step3bLaunchForm
)

# Initialize extensions
login_manager = LoginManager()
csrf = CSRFProtect()
cache = Cache()

def create_app(config_name='default'):
    """Application factory function."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions
    # Connect to MongoDB with highly optimized settings for performance
    connect(
        host=app.config['MONGODB_SETTINGS']['host'],
        maxPoolSize=50,  # Increased for better concurrency
        minPoolSize=5,   # Increased minimum connections
        maxIdleTimeMS=60000,  # Keep connections alive longer
        serverSelectionTimeoutMS=2000,  # Faster server selection
        connectTimeoutMS=2000,  # Faster connection
        socketTimeoutMS=10000,  # Reasonable socket timeout
        waitQueueTimeoutMS=2000,  # Faster queue timeout
        maxConnecting=10,  # Limit concurrent connections
        retryWrites=True,  # Enable retry for writes
        retryReads=True,   # Enable retry for reads
        w='majority',      # Write concern
        readPreference='primaryPreferred'  # Read preference
    )
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    # Initialize CSRF protection
    csrf.init_app(app)
    

    
    # Configure session management for persistence
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 30  # 30 days
    app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    

    app.register_blueprint(index_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(study_participation)
    app.register_blueprint(study_creation_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)
    

    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.objects(_id=user_id).first()
        except:
            return None
    
    # Health check endpoint
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring."""
        try:
            # Simple connection check - much faster
            from mongoengine import get_db
            db = get_db()
            # Use a lightweight command instead of ping
            db.command('ismaster', maxTimeMS=1000)
            return jsonify({'status': 'healthy', 'database': 'connected'}), 200
        except Exception as e:
            return jsonify({'status': 'unhealthy', 'database': str(e)}), 500
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500
    
    # Main routes
    @app.route('/')
    def index():
        """Main landing page."""
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return render_template('index.html')
    
    @app.route('/about')
    def about():
        """About page."""
        return render_template('about.html')
    
    @app.route('/contact')
    def contact():
        """Contact page."""
        return render_template('contact.html')
    
    # File upload helper
    def allowed_file(filename):
        """Check if file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
    
    def save_uploaded_file(file, study_id):
        """Save uploaded file and return file path."""
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Create unique filename
            unique_filename = f"{study_id}_{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            return unique_filename
        return None
    
    # Register template filters
    @app.template_filter('format_datetime')
    def format_datetime_filter(value, format='%Y-%m-%d %H:%M'):
        if value is None:
            return ""
        return value.strftime(format)
    
    @app.template_filter('format_duration')
    def format_duration_filter(seconds):
        if seconds is None:
            return "0s"
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
    
    return app

def create_tables():
    """Create database tables/indexes with performance optimization."""
    app = create_app()
    with app.app_context():
        try:
            # Create basic indexes
            User.ensure_indexes()
            Study.ensure_indexes()
            StudyDraft.ensure_indexes()
            StudyResponse.ensure_indexes()
            TaskSession.ensure_indexes()
            
            # Create additional compound indexes for better performance
            from mongoengine import get_db
            db = get_db()
            
            # Study indexes for dashboard queries
            db.studies.create_index([('creator', 1), ('status', 1), ('created_at', -1)], background=True)
            db.studies.create_index([('share_token', 1)], background=True)
            db.studies.create_index([('status', 1), ('created_at', -1)], background=True)
            
            # StudyResponse indexes for analytics
            db.study_responses.create_index([('study', 1), ('created_at', -1)], background=True)
            db.study_responses.create_index([('study', 1), ('is_completed', 1)], background=True)
            db.study_responses.create_index([('study', 1), ('is_abandoned', 1)], background=True)
            db.study_responses.create_index([('session_id', 1)], background=True)
            db.study_responses.create_index([('last_activity', -1)], background=True)
            
            # User indexes
            db.users.create_index([('username', 1)], background=True)
            db.users.create_index([('email', 1)], background=True)
            
            print("Database indexes created successfully with performance optimization!")
            
        except Exception as e:
            print(f"Error creating indexes: {e}")
            # Continue with basic indexes if advanced ones fail
            print("Continuing with basic indexes...")

if __name__ == '__main__':
    app = create_app()
    
    # # Create database indexes if they don't exist
    # create_tables()
    
    app.run(debug=True, host='0.0.0.0', port=51000)
