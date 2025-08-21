from flask import Blueprint, render_template
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
    
    return render_template('index.html', 
                         total_studies=total_studies,
                         total_responses=total_responses,
                         recent_studies=recent_studies)
