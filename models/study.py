from random import choice
from mongoengine import Document, StringField, ReferenceField, DateTimeField, BooleanField, IntField, ListField, DictField, EmbeddedDocument, EmbeddedDocumentField, URLField
from datetime import datetime
import numpy as np
import json
import uuid

class RatingScale(EmbeddedDocument):
    """Embedded document for rating scale configuration."""
    min_value = IntField(required=True, min_value=1, max_value=9)
    max_value = IntField(required=True, choices=[ 5, 7, 9])
    min_label = StringField(required=True, max_length=100)
    max_label = StringField(required=True, max_length=100)
    middle_label = StringField(max_length=100)  # Optional middle label

class StudyElement(EmbeddedDocument):
    """Embedded document for study elements (images or text)."""
    element_id = StringField(required=True, max_length=10)  # E1, E2, E3, etc.
    name = StringField(required=True, max_length=100)
    description = StringField(max_length=500)
    element_type = StringField(required=True, choices=['image', 'text'])
    
    content = StringField(required=True)  # File path for images, text content for text
    alt_text = StringField(max_length=200)  # For accessibility

class LayerCategory(EmbeddedDocument):
    """Embedded document for layer study categories (A, B, C, D, etc.)."""
    category_id = StringField(required=True, max_length=10)  # A, B, C, D, etc.
    category_name = StringField(required=True, max_length=100)
    elements = ListField(EmbeddedDocumentField(StudyElement), required=True)
    order = IntField(required=True)

class ClassificationQuestion(EmbeddedDocument):
    """Embedded document for classification questions."""
    question_id = StringField(required=True, max_length=10)
    question_text = StringField(required=True, max_length=500)
    question_type = StringField(choices=['single_choice', 'multiple_choice', 'text', 'number', 'date'])
    answer_options = ListField(StringField(max_length=200))  # For choice questions
    is_required = BooleanField(default=False)
    order = IntField(required=True)

class IPEDParameters(EmbeddedDocument):
    """Embedded document for IPED study parameters."""
    num_elements = IntField(required=True, min_value=1, max_value=100)
    tasks_per_consumer = IntField(required=True, min_value=1, max_value=100)
    number_of_respondents = IntField(required=True, min_value=1, max_value=10000)
    min_active_elements = IntField(required=True, min_value=1, max_value=20)
    max_active_elements = IntField(required=True, min_value=1, max_value=20)
    total_tasks = IntField(required=True)  # Calculated: tasks_per_consumer * number_of_respondents

class Study(Document):
    """Study model with complete IPED configuration and task matrix."""
    
    # Basic Information
    _id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    title = StringField(required=True, max_length=200)
    background = StringField(required=True, max_length=2000)
    language = StringField(required=True, max_length=10, default='en')
    main_question = StringField(required=True, max_length=1000)
    orientation_text = StringField(required=True, max_length=55000)
    
    # Study Type and Configuration
    study_type = StringField(required=True, choices=['grid', 'layer'])
    rating_scale = EmbeddedDocumentField(RatingScale, required=True)
    
    # Grid Study Elements (for grid study type)
    elements = ListField(EmbeddedDocumentField(StudyElement))  # Optional for layer studies
    
    # Layer Study Categories (for layer study type)
    layer_categories = ListField(EmbeddedDocumentField(LayerCategory))  # Optional for grid studies
    
    # Common fields
    classification_questions = ListField(EmbeddedDocumentField(ClassificationQuestion))
    iped_parameters = EmbeddedDocumentField(IPEDParameters, required=True)
    
    # Task Matrix (Generated IPED Structure)
    tasks = DictField()  # IPED task matrix structure
    
    # Study Management
    creator = ReferenceField('User', required=True)
    status = StringField(required=True, choices=['draft', 'active', 'paused', 'completed'], default='draft')
    share_token = StringField(unique=True, required=True)  # For anonymous access
    share_url = URLField()
    
    # Timestamps
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    launched_at = DateTimeField()
    completed_at = DateTimeField()
    
    # Statistics
    total_responses = IntField(default=0)
    completed_responses = IntField(default=0)
    abandoned_responses = IntField(default=0)
    
    meta = {
        'collection': 'studies',
        'indexes': [
            'creator',
            'status',
            'share_token',
            'created_at',
            'study_type'
        ]
    }
    
    def generate_share_url(self, base_url):
        """Generate shareable URL for anonymous access."""
        self.share_url = f"{base_url}/participate/{self.share_token}"
        return self.share_url
    
    def generate_tasks(self):
        """Generate IPED task matrix using the algorithm from fn.py."""
        num_elements = self.iped_parameters.num_elements
        tasks_per_consumer = self.iped_parameters.tasks_per_consumer
        num_consumers = self.iped_parameters.number_of_respondents
        min_active = self.iped_parameters.min_active_elements
        max_active = self.iped_parameters.max_active_elements
        
        total_tasks = tasks_per_consumer * num_consumers
        
        # Generate candidate pool
        candidate_pool = []
        num_candidates_to_generate = total_tasks * 20  # Increased for better variety
        
        while len(candidate_pool) < num_candidates_to_generate:
            random_task = np.random.randint(0, 2, num_elements)
            if min_active <= sum(random_task) <= max_active:
                candidate_pool.append(random_task)
        
        if len(candidate_pool) < total_tasks:
            final_tasks = candidate_pool
        else:
            # Select tasks ensuring better distribution
            final_tasks = np.array(candidate_pool)[np.random.choice(len(candidate_pool), total_tasks, replace=False)]
        
        # Convert to the required structure with balanced distribution per respondent
        tasks_structure = {}
        element_names = [f"E{i+1}" for i in range(num_elements)]
        
        # Shuffle tasks to ensure random distribution per respondent
        np.random.shuffle(final_tasks)
        
        for respondent_id in range(num_consumers):
            respondent_tasks = []
            start_idx = respondent_id * tasks_per_consumer
            end_idx = start_idx + tasks_per_consumer
            
            # Get tasks for this specific respondent
            respondent_task_data = final_tasks[start_idx:end_idx]
            
            for task_index, task_data in enumerate(respondent_task_data):
                # Create elements_shown dictionary
                elements_shown = {}
                for i, element_name in enumerate(element_names):
                    # Element is only shown if it's active in this task
                    element_active = int(task_data[i])
                    elements_shown[element_name] = element_active
                    
                    # Element content is only shown if the element itself is shown
                    if element_active and self.elements and i < len(self.elements):
                        print(f"DEBUG: Element {i}: {self.elements[i]}")
                        print(f"DEBUG: Element content: {getattr(self.elements[i], 'content', 'NO_CONTENT_ATTR')}")
                        elements_shown[f"{element_name}_content"] = getattr(self.elements[i], 'content', '')
                    else:
                        print(f"DEBUG: Element {i} not active or no content available")
                        elements_shown[f"{element_name}_content"] = ""

                
                task_obj = {
                    "task_id": f"{respondent_id}_{task_index}",
                    "elements_shown": elements_shown,
                    "task_index": task_index
                }
                respondent_tasks.append(task_obj)
            
            tasks_structure[str(respondent_id)] = respondent_tasks
        
        self.tasks = tasks_structure
        return tasks_structure
    
    def get_available_respondent_id(self):
        """Get next available respondent ID for anonymous access."""
        if not self.tasks:
            return None
        
        # Find first available respondent_id
        for respondent_id in range(self.iped_parameters.number_of_respondents):
            if str(respondent_id) in self.tasks:
                return respondent_id
        
        return None
    
    def get_respondent_tasks(self, respondent_id):
        """Get tasks for a specific respondent."""
        if not self.tasks or str(respondent_id) not in self.tasks:
            return None
        return self.tasks[str(respondent_id)]
    
    def to_dict(self):
        """Convert study to dictionary for JSON serialization."""
        return {
            'id': str(self._id),
            'title': self.title,
            'background': self.background,
            'language': self.language,
            'main_question': self.main_question,
            'orientation_text': self.orientation_text,
            'study_type': self.study_type,
            'rating_scale': {
                'min_value': self.rating_scale.min_value,
                'max_value': self.rating_scale.max_value,
                'min_label': self.rating_scale.min_label,
                'max_label': self.rating_scale.max_label,
                'middle_label': self.rating_scale.middle_label
            } if self.rating_scale else None,
            'elements': [elem.to_mongo().to_dict() for elem in self.elements] if self.elements else [],
            'classification_questions': [q.to_mongo().to_dict() for q in self.classification_questions] if self.classification_questions else [],
            'iped_parameters': {
                'num_elements': self.iped_parameters.num_elements,
                'tasks_per_consumer': self.iped_parameters.tasks_per_consumer,
                'number_of_respondents': self.iped_parameters.number_of_respondents,
                'min_active_elements': self.iped_parameters.min_active_elements,
                'max_active_elements': self.iped_parameters.max_active_elements,
                'total_tasks': self.iped_parameters.total_tasks
            } if self.iped_parameters else None,
            'status': self.status,
            'share_token': self.share_token,
            'share_url': self.share_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'launched_at': self.launched_at.isoformat() if self.launched_at else None,
            'total_responses': self.total_responses,
            'completed_responses': self.completed_responses,
            'abandoned_responses': self.abandoned_responses
        }
    
    def __repr__(self):
        return f'<Study {self.title}>'
