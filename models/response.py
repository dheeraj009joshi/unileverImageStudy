from mongoengine import Document, StringField, ReferenceField, DateTimeField, BooleanField, IntField, ListField, DictField, EmbeddedDocument, EmbeddedDocumentField, FloatField
from datetime import datetime
import uuid

class ElementInteraction(EmbeddedDocument):
    """Embedded document for tracking element interactions and timing."""
    element_id = StringField(required=True, max_length=10)
    view_time_seconds = FloatField(required=True, min_value=0.0)
    hover_count = IntField(default=0, min_value=0)
    click_count = IntField(default=0, min_value=0)
    first_view_time = DateTimeField()
    last_view_time = DateTimeField()

class CompletedTask(EmbeddedDocument):
    """Embedded document for individual completed task data."""
    task_id = StringField(required=True, max_length=20)
    respondent_id = IntField(required=True, min_value=0)
    task_index = IntField(required=True, min_value=0)
    elements_shown_in_task = DictField(required=True)  # Copy from study.tasks
    task_start_time = DateTimeField(required=True)
    task_completion_time = DateTimeField(required=True)
    task_duration_seconds = FloatField(required=True, min_value=0.0)
    rating_given = IntField(required=True)
    rating_timestamp = DateTimeField(required=True)
    element_interactions = ListField(EmbeddedDocumentField(ElementInteraction))

class ClassificationAnswer(EmbeddedDocument):
    """Embedded document for classification question answers."""
    question_id = StringField(required=True, max_length=10)
    question_text = StringField(required=True, max_length=500)
    # question_type removed - all classification questions are single choice
    answer = StringField(required=True, max_length=1000)
    answer_timestamp = DateTimeField(required=True)
    time_spent_seconds = FloatField(default=0.0)

class StudyResponse(Document):
    """Study response model for anonymous respondent submissions."""
    
    # Basic Information
    _id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Study and Respondent Identification
    study = ReferenceField('Study', required=True)
    session_id = StringField(required=True, unique=True, max_length=50)
    respondent_id = IntField(required=True, min_value=0)  # Assigned from study.tasks
    
    # Progress Tracking
    current_task_index = IntField(default=0, min_value=0)
    completed_tasks_count = IntField(default=0, min_value=0)
    total_tasks_assigned = IntField(required=True, min_value=1)
    
    # Task Completion Records
    completed_tasks = ListField(EmbeddedDocumentField(CompletedTask))
    
    # Session Management
    session_start_time = DateTimeField(required=True)
    session_end_time = DateTimeField()
    is_completed = BooleanField(default=False)
    
    # Classification and Demographics
    classification_answers = ListField(EmbeddedDocumentField(ClassificationAnswer))
    personal_info = DictField()  # Age, gender, education, etc.
    
    # Analytics Data
    ip_address = StringField(max_length=45)  # IPv6 support
    user_agent = StringField(max_length=500)
    browser_info = DictField()
    
    # Progress and Timing
    completion_percentage = FloatField(default=0.0, min_value=0.0, max_value=100.0)
    total_study_duration = FloatField(default=0.0, min_value=0.0)
    last_activity = DateTimeField(default=datetime.utcnow)
    
    # Abandonment Detection
    is_abandoned = BooleanField(default=False)
    abandonment_timestamp = DateTimeField()
    abandonment_reason = StringField(max_length=200)
    
    meta = {
        'collection': 'study_responses',
        'indexes': [
            'study',
            'session_id',
            'respondent_id',
            'session_start_time',
            'is_completed',
            'is_abandoned'
        ]
    }
    
    def update_completion_percentage(self):
        """Update completion percentage based on completed tasks."""
        if self.total_tasks_assigned > 0:
            self.completion_percentage = (self.completed_tasks_count / self.total_tasks_assigned) * 100.0
        else:
            self.completion_percentage = 0.0
    
    def add_completed_task(self, task_data):
        """Add a completed task to the response."""
        completed_task = CompletedTask(**task_data)
        self.completed_tasks.append(completed_task)
        self.completed_tasks_count = len(self.completed_tasks)
        self.update_completion_percentage()
        
        # Update total study duration
        if self.session_start_time and completed_task.task_completion_time:
            self.total_study_duration = (completed_task.task_completion_time - self.session_start_time).total_seconds()
    
    def mark_completed(self):
        """Mark the study response as completed."""
        self.is_completed = True
        self.session_end_time = datetime.utcnow()
        if self.session_start_time:
            self.total_study_duration = (self.session_end_time - self.session_start_time).total_seconds()
        self.completion_percentage = 100.0
    
    def mark_abandoned(self, reason="User left study"):
        """Mark the study response as abandoned."""
        self.is_abandoned = True
        self.abandonment_timestamp = datetime.utcnow()
        self.abandonment_reason = reason
    
    def to_dict(self):
        """Convert response to dictionary for JSON serialization."""
        return {
            'id': str(self._id),
            'study_id': str(self.study._id),
            'session_id': self.session_id,
            'respondent_id': self.respondent_id,
            'current_task_index': self.current_task_index,
            'completed_tasks_count': self.completed_tasks_count,
            'total_tasks_assigned': self.total_tasks_assigned,
            'completed_tasks': [task.to_mongo().to_dict() for task in self.completed_tasks],
            'session_start_time': self.session_start_time.isoformat() if self.session_start_time else None,
            'session_end_time': self.session_end_time.isoformat() if self.session_end_time else None,
            'is_completed': self.is_completed,
            'classification_answers': [ans.to_mongo().to_dict() for ans in self.classification_answers],
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'browser_info': self.browser_info,
            'completion_percentage': self.completion_percentage,
            'total_study_duration': self.total_study_duration,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'is_abandoned': self.is_abandoned,
            'abandonment_timestamp': self.abandonment_timestamp.isoformat() if self.abandonment_timestamp else None,
            'abandonment_reason': self.abandonment_reason
        }
    
    def __repr__(self):
        return f'<StudyResponse {self.session_id} for Study {self.study._id}>'

class TaskSession(Document):
    """Individual task timing tracking for detailed analytics."""
    
    # Basic Information
    _id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    # Session Identification
    session_id = StringField(required=True, max_length=50)
    task_id = StringField(required=True, max_length=20)
    study_response = ReferenceField('StudyResponse', required=True)
    
    # Page-Level Timing
    classification_page_time = FloatField(default=0.0, min_value=0.0)
    orientation_page_time = FloatField(default=0.0, min_value=0.0)
    individual_task_page_times = ListField(FloatField())
    
    # Page Transitions
    page_transitions = ListField(DictField())  # [{page: "classification", timestamp: "..."}, ...]
    
    # Element Interaction Logs
    element_interactions = ListField(EmbeddedDocumentField(ElementInteraction))
    
    # Task Abandonment Detection
    is_completed = BooleanField(default=False)
    abandonment_timestamp = DateTimeField()
    abandonment_reason = StringField(max_length=200)
    recovery_attempts = IntField(default=0, min_value=0)
    
    # Performance Analytics
    browser_performance = DictField()
    page_load_times = ListField(FloatField())
    device_info = DictField()
    screen_resolution = StringField(max_length=20)
    
    # Timestamps
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    meta = {
        'collection': 'task_sessions',
        'indexes': [
            'session_id',
            'task_id',
            'study_response',
            'created_at',
            'is_completed'
        ]
    }
    
    def add_page_transition(self, page_name, timestamp=None):
        """Add a page transition record."""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        transition = {
            'page': page_name,
            'timestamp': timestamp.isoformat()
        }
        self.page_transitions.append(transition)
    
    def add_element_interaction(self, element_id, interaction_type, duration=0.0):
        """Add or update element interaction data."""
        # Find existing interaction for this element
        existing_interaction = None
        for interaction in self.element_interactions:
            if interaction.element_id == element_id:
                existing_interaction = interaction
                break
        
        if existing_interaction:
            if interaction_type == 'view':
                existing_interaction.view_time_seconds += duration
                existing_interaction.last_view_time = datetime.utcnow()
                if not existing_interaction.first_view_time:
                    existing_interaction.first_view_time = datetime.utcnow()
            elif interaction_type == 'hover':
                existing_interaction.hover_count += 1
            elif interaction_type == 'click':
                existing_interaction.click_count += 1
        else:
            # Create new interaction
            interaction_data = {
                'element_id': element_id,
                'view_time_seconds': duration if interaction_type == 'view' else 0.0,
                'hover_count': 1 if interaction_type == 'hover' else 0,
                'click_count': 1 if interaction_type == 'click' else 0,
                'first_view_time': datetime.utcnow() if interaction_type == 'view' else None,
                'last_view_time': datetime.utcnow() if interaction_type == 'view' else None
            }
            new_interaction = ElementInteraction(**interaction_data)
            self.element_interactions.append(new_interaction)
    
    def mark_completed(self):
        """Mark the task session as completed."""
        self.is_completed = True
        self.updated_at = datetime.utcnow()
    
    def to_dict(self):
        """Convert task session to dictionary for JSON serialization."""
        return {
            'id': str(self._id),
            'session_id': self.session_id,
            'task_id': self.task_id,
            'study_response_id': str(self.study_response._id),
            'classification_page_time': self.classification_page_time,
            'orientation_page_time': self.orientation_page_time,
            'individual_task_page_times': self.individual_task_page_times,
            'page_transitions': self.page_transitions,
            'element_interactions': [interaction.to_mongo().to_dict() for interaction in self.element_interactions],
            'is_completed': self.is_completed,
            'abandonment_timestamp': self.abandonment_timestamp.isoformat() if self.abandonment_timestamp else None,
            'abandonment_reason': self.abandonment_reason,
            'recovery_attempts': self.recovery_attempts,
            'browser_performance': self.browser_performance,
            'page_load_times': self.page_load_times,
            'device_info': self.device_info,
            'screen_resolution': self.screen_resolution,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<TaskSession {self.task_id} for Session {self.session_id}>'
