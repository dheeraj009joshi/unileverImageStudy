from flask import Blueprint, render_template, current_app
from flask_login import current_user
from models.study import Study
from models.response import StudyResponse

index_bp = Blueprint('index', __name__)

@index_bp.route('/')
def index():
    """Main landing page."""
    # Get some public stats for the landing page
    total_studies = Study.objects.count()
    total_responses = StudyResponse.objects.count()
    
    # Get recent studies for showcase
    recent_studies = Study.objects.filter(status='active').order_by('-created_at').limit(3)
    
    # Get dynamic configuration values
    config = current_app.config
    
    return render_template('index.html', 
                         total_studies=total_studies,
                         total_responses=total_responses,
                         recent_studies=recent_studies,
                         app_name=config.get('APP_NAME'),
                         app_description=config.get('APP_DESCRIPTION'),
                         app_tagline=config.get('APP_TAGLINE'),
                         app_subtagline=config.get('APP_SUBTAGLINE'),
                         features=config.get('FEATURES'),
                         social_links=config.get('SOCIAL_LINKS'),
                         contact_info=config.get('CONTACT_INFO'),
                         company_name=config.get('COMPANY_NAME'),
                         company_year=config.get('COMPANY_YEAR'))
