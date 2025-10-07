from random import choice
from mongoengine import Document, StringField, ReferenceField, DateTimeField, BooleanField, IntField, ListField, DictField, EmbeddedDocument, EmbeddedDocumentField, URLField, FloatField
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
    element_id = StringField(required=True, max_length=100)  # UUID for element
    name = StringField(required=True, max_length=100)
    description = StringField(max_length=500)
    element_type = StringField(required=True, choices=['image', 'text'])
    
    content = StringField(required=True)  # File path for images, text content for text
    alt_text = StringField(max_length=200)  # For accessibility

class LayerImage(EmbeddedDocument):
    """Embedded document for images within a layer."""
    image_id = StringField(required=True, max_length=100)  # Increased from 20 to 100 for UUIDs
    name = StringField(required=True, max_length=100)
    url = StringField(required=True)  # Azure blob URL
    alt_text = StringField(max_length=200)
    order = IntField(required=True)  # Order within the layer

class StudyLayer(EmbeddedDocument):
    """Embedded document for layers in a layer study."""
    layer_id = StringField(required=True, max_length=100)  # Increased from 20 to 100 for UUIDs
    name = StringField(required=True, max_length=100)  # User-defined name
    description = StringField(max_length=500)
    z_index = IntField(required=True)  # Z-index for stacking order (0, 1, 2, 3...)
    images = ListField(EmbeddedDocumentField(LayerImage), required=True)
    order = IntField(required=True)  # User-defined order (can be changed by drag & drop)

class GridCategory(EmbeddedDocument):
    """Embedded document for categories in a grid study."""
    category_id = StringField(required=True, max_length=100)  # UUID for category
    name = StringField(required=True, max_length=100)  # User-defined name
    description = StringField(max_length=500)
    elements = ListField(EmbeddedDocumentField(StudyElement), required=True)  # Elements within this category
    order = IntField(required=True)  # User-defined order (can be changed by drag & drop)



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
    # Common parameters
    number_of_respondents = IntField(required=True, min_value=1, max_value=10000)
    total_tasks = IntField(required=True)  # Calculated: tasks_per_consumer * number_of_respondents
    
    # Grid study parameters
    num_elements = IntField(required=False, min_value=4, max_value=5000)
    tasks_per_consumer = IntField(required=False, min_value=1, max_value=240)
    exposure_tolerance_cv = FloatField(required=False, min_value=0.1, max_value=5.0, default=1.0)
    
    # Layer study parameters
    exposure_tolerance_pct = FloatField(required=False, min_value=0.5, max_value=5.0, default=2.0)
    
    # Optional parameters
    seed = IntField(required=False, min_value=1, max_value=999999999)
    
    # Legacy fields for backward compatibility
    min_active_elements = IntField(required=False, min_value=1, max_value=20)
    max_active_elements = IntField(required=False, min_value=1, max_value=20)
    
    def get_study_type(self):
        """Determine study type based on available parameters."""
        if self.num_elements is not None:
            return 'grid'
        else:
            return 'layer'
    
    def validate(self, clean=True):
        """Custom validation for IPED parameters."""
        errors = super().validate(clean)
        
        if self.get_study_type() == 'grid':
            if not self.num_elements:
                errors['num_elements'] = 'Number of elements is required for grid studies'
            if not self.tasks_per_consumer:
                errors['tasks_per_consumer'] = 'Tasks per consumer is required for grid studies'
        elif self.get_study_type() == 'layer':
            if not self.exposure_tolerance_pct:
                errors['exposure_tolerance_pct'] = 'Exposure tolerance is required for layer studies'
        
        return errors

class Study(Document):
    """Study model with complete IPED configuration and task matrix for both grid and layer studies."""
    
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
    
    # Grid Study Categories (for grid study type)
    grid_categories = ListField(EmbeddedDocumentField(GridCategory))  # Required for grid studies
    
    # Layer Study Configuration (for layer study type)
    study_layers = ListField(EmbeddedDocumentField(StudyLayer))  # Required for layer studies
    
    # Default Background for Layer Studies (optional)
    default_background = DictField()  # Contains url, name, and metadata for default background
    
    # Legacy field for backward compatibility (deprecated)
    elements = ListField(EmbeddedDocumentField(StudyElement))  # Deprecated: use grid_categories instead
    
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
    in_progress_responses = IntField(default=0)
    
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
    
    def get_available_respondent_id(self):
        """Get next available respondent ID for anonymous access."""
        if not self.tasks:
            return None
        
        # Find first available respondent_id
        for respondent_id in range(self.iped_parameters.number_of_respondents):
            if str(respondent_id) in self.tasks:
                return respondent_id
        
        return None
    
    def increment_total_responses(self):
        """Increment the total responses counter."""
        self.total_responses += 1
        self.save()
        return self.total_responses
    
    def increment_completed_responses(self):
        """Increment the completed responses counter."""
        self.completed_responses += 1
        self.save()
        return self.completed_responses
    
    def increment_abandoned_responses(self):
        """Increment the abandoned responses counter."""
        self.abandoned_responses += 1
        self.save()
        return self.abandoned_responses

    def increment_in_progress_responses(self):
        """Increment the in-progress responses counter."""
        self.in_progress_responses += 1
        self.save()
        return self.in_progress_responses

    def decrement_in_progress_responses(self):
        """Decrement the in-progress responses counter safely."""
        if self.in_progress_responses > 0:
            self.in_progress_responses -= 1
            self.save()
        return self.in_progress_responses
    
    def update_response_counters(self):
        """Update response counters based on actual StudyResponse objects."""
        from models.response import StudyResponse
        
        # Count actual responses from database
        total_count = StudyResponse.objects(study=self).count()
        completed_count = StudyResponse.objects(study=self, is_completed=True).count()
        abandoned_count = StudyResponse.objects(study=self, is_abandoned=True).count()
        in_progress_count = StudyResponse.objects(study=self, is_completed=False, is_abandoned=False).count()
        
        # Update counters if they differ
        if (self.total_responses != total_count or 
            self.completed_responses != completed_count or 
            self.abandoned_responses != abandoned_count):
            
            self.total_responses = total_count
            self.completed_responses = completed_count
            self.abandoned_responses = abandoned_count
            self.in_progress_responses = in_progress_count
            self.save()
            
            print(f"✅ Updated study {self.title} response counters:")
            print(f"   Total: {self.total_responses}")
            print(f"   Completed: {self.completed_responses}")
            print(f"   Abandoned: {self.abandoned_responses}")
            print(f"   In Progress: {self.in_progress_responses}")
        
        return {
            'total': self.total_responses,
            'completed': self.completed_responses,
            'abandoned': self.abandoned_responses,
            'in_progress': self.in_progress_responses
        }

    def auto_mark_completed_if_reached(self):
        """Mark study completed when completed responses reach planned respondents."""
        try:
            target = int(getattr(self.iped_parameters, 'number_of_respondents', 0) or 0)
        except Exception:
            target = 0
        if target > 0 and self.completed_responses >= target and self.status != 'completed':
            self.status = 'completed'
            self.completed_at = datetime.utcnow()
            self.save()
            return True
        return False
    
    def get_real_time_counts(self):
        """Get real-time response counts from database for consistency."""
        from models.response import StudyResponse
        
        total = StudyResponse.objects(study=self).count()
        completed = StudyResponse.objects(study=self, is_completed=True).count()
        abandoned = StudyResponse.objects(study=self, is_abandoned=True).count()
        in_progress = StudyResponse.objects(study=self, is_completed=False, is_abandoned=False).count()
        
        return {
            'total': total,
            'completed': completed,
            'abandoned': abandoned,
            'in_progress': in_progress
        }
    
    def get_respondent_tasks(self, respondent_id):
        """Get tasks for a specific respondent."""
        if not self.tasks or str(respondent_id) not in self.tasks:
            return None
        return self.tasks[str(respondent_id)]
    
    def get_study_elements(self):
        """Get study elements based on study type."""
        if self.study_type == 'grid':
            return self.elements
        else:  # layer study
            # Flatten all images from all layers
            all_images = []
            for layer in self.study_layers:
                for image in layer.images:
                    all_images.append({
                        'element_id': f"{layer.layer_id}_{image.image_id}",
                        'name': image.name,
                        'description': f"Layer: {layer.name}",
                        'element_type': 'image',
                        'content': image.url,
                        'alt_text': image.alt_text,
                        'layer_name': layer.name,
                        'z_index': layer.z_index
                    })
            return all_images
    
    def get_layer_configuration(self):
        """Get layer configuration for layer studies."""
        if self.study_type != 'layer':
            return None
        return {
            'layers': [
                {
                    'id': layer.layer_id,
                    'name': layer.name,
                    'description': layer.description,
                    'z_index': layer.z_index,
                    'order': layer.order,
                    'images': [
                        {
                            'id': img.image_id,
                            'name': img.name,
                            'url': img.url,
                            'alt_text': img.alt_text,
                            'order': img.order
                        } for img in layer.images
                    ]
                } for layer in self.study_layers
            ]
        }
    
    def to_dict(self):
        """Convert study to dictionary for JSON serialization."""
        base_dict = {
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
            'classification_questions': [q.to_mongo().to_dict() for q in self.classification_questions] if self.classification_questions else [],
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
        
        # Add study type specific data
        if self.study_type == 'grid':
            base_dict['grid_categories'] = [cat.to_mongo().to_dict() for cat in self.grid_categories] if self.grid_categories else []
            # Legacy support for old elements field
            base_dict['elements'] = [elem.to_mongo().to_dict() for elem in self.elements] if self.elements else []
            base_dict['iped_parameters'] = {
                'num_elements': self.iped_parameters.num_elements,
                'tasks_per_consumer': self.iped_parameters.tasks_per_consumer,
                'number_of_respondents': self.iped_parameters.number_of_respondents,
                'exposure_tolerance_cv': self.iped_parameters.exposure_tolerance_cv,
                'total_tasks': self.iped_parameters.total_tasks
            } if self.iped_parameters else None
        else:  # layer study
            base_dict['study_layers'] = [layer.to_mongo().to_dict() for layer in self.study_layers] if self.study_layers else []
            base_dict['iped_parameters'] = {
                'number_of_respondents': self.iped_parameters.number_of_respondents,
                'exposure_tolerance_pct': self.iped_parameters.exposure_tolerance_pct,
                'total_tasks': self.iped_parameters.total_tasks
            } if self.iped_parameters else None
        
        return base_dict
    
    def validate(self, clean=True):
        """Custom validation for Study model."""
        errors = super().validate(clean)
        
        if self.study_type == 'grid':
            # Check for new grid_categories structure
            if self.grid_categories:
                total_elements = sum(len(cat.elements) for cat in self.grid_categories)
                if total_elements < 4:
                    errors['grid_categories'] = 'Grid studies must have at least 4 elements across all categories'
                if self.study_layers:
                    errors['study_layers'] = 'Grid studies should not have study layers'
            # Legacy support for old elements structure
            elif self.elements:
                if len(self.elements) < 4:
                    errors['elements'] = 'Grid studies must have at least 4 elements'
                if self.study_layers:
                    errors['study_layers'] = 'Grid studies should not have study layers'
            else:
                errors['grid_categories'] = 'Grid studies must have categories with elements'
        elif self.study_type == 'layer':
            if not self.study_layers or len(self.study_layers) < 1:
                errors['study_layers'] = 'Layer studies must have at least 1 layer'
            if self.grid_categories:
                errors['grid_categories'] = 'Layer studies should not have grid categories'
            if self.elements:
                errors['elements'] = 'Layer studies should not have individual elements'
        
        return errors
    
    def __repr__(self):
        return f'<Study {self.title}>'
