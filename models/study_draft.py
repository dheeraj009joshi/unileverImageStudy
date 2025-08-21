from mongoengine import Document, StringField, DictField, DateTimeField, ReferenceField, UUIDField, BooleanField
from datetime import datetime
import uuid

class StudyDraft(Document):
    """Model for storing study creation drafts in the database."""
    
    _id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))
    user = ReferenceField('User', required=True)
    current_step = StringField(required=True, default='1a')
    
    # Step data stored as dictionaries
    step1a_data = DictField(default={})
    step1b_data = DictField(default={})
    step1c_data = DictField(default={})
    step1c_layer_data = DictField(default={})  # For layer study category setup
    step2a_data = DictField(default={})
    step2a_layer_data = DictField(default={})  # For layer study categories and elements
    step2b_data = DictField(default={})
    step2c_data = DictField(default={})
    step3a_data = DictField(default={})
    step3b_data = DictField(default={})
    
    # Metadata
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    is_complete = BooleanField(default=False)
    
    meta = {
        'collection': 'study_drafts',
        'indexes': [
            'user',
            'created_at',
            ('user', 'created_at')
        ]
    }
    
    def update_step_data(self, step, data):
        """Update data for a specific step."""
        step_field = f'step{step}_data'
        if hasattr(self, step_field):
            setattr(self, step_field, data)
            self.updated_at = datetime.utcnow()
            self.save()
    
    def get_step_data(self, step):
        """Get data for a specific step."""
        step_field = f'step{step}_data'
        return getattr(self, step_field, {})
    
    def is_step_complete(self, step):
        """Check if a specific step is complete."""
        step_data = self.get_step_data(step)
        
        # For layer-specific steps, check if they have meaningful data
        if step == '1c_layer':
            # Check if num_categories is set
            return bool(step_data.get('num_categories'))
        elif step == '2a_layer':
            # Check if categories data exists
            return bool(step_data.get('categories'))
        else:
            # For other steps, check if any data exists
            return bool(step_data)
    
    def can_proceed_to_step(self, target_step):
        """Check if user can proceed to a specific step."""
        # Get study type to determine the correct flow
        study_type = self.get_step_data('1b').get('study_type', 'grid')
        
        if study_type == 'layer':
            step_order = ['1a', '1b', '1c', '1c_layer', '2a_layer', '2b', '2c', '3a', '3b']
        else:
            step_order = ['1a', '1b', '1c', '2a', '2b', '2c', '3a', '3b']
            
        if target_step not in step_order:
            return False
            
        target_index = step_order.index(target_step)
        
        # For forward navigation, require previous steps to be complete
        for i in range(target_index):
            if not self.is_step_complete(step_order[i]):
                return False
        return True
    
    def can_access_step(self, target_step):
        """Check if user can access a specific step (for navigation)."""
        # Get study type to determine the correct flow
        study_type = self.get_step_data('1b').get('study_type', 'grid')
        
        if study_type == 'layer':
            step_order = ['1a', '1b', '1c', '1c_layer', '2a_layer', '2b', '2c', '3a', '3b']
        else:
            step_order = ['1a', '1b', '1c', '2a', '2b', '2c', '3a', '3b']
            
        if target_step not in step_order:
            return False
            
        target_index = step_order.index(target_step)
        
        # For navigation (including going back), allow access to completed steps
        if target_index == 0:  # step1a
            return True
        elif target_index == 1:  # step1b
            return self.is_step_complete('1a')
        elif target_step == '1c':  # step1c (Rating Scale) - common for both study types
            return self.is_step_complete('1a') and self.is_step_complete('1b')
        elif target_step == '1c_layer':  # step1c_layer (Categories) - only for layer studies
            return self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c')
        elif target_step in ['2a', '2a_layer']:  # Elements step (varies by study type)
            if target_step == '2a':  # Grid study elements
                return self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c')
            else:  # Layer study categories & elements
                return self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c') and self.is_step_complete('1c_layer')
        else:  # steps 2b and beyond
            return (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                   self.is_step_complete('1c') and
                   (self.is_step_complete('1c_layer') or True) and  # 1c_layer only required for layer studies
                   (self.is_step_complete('2a') or self.is_step_complete('2a_layer')))
    
    def get_all_data(self):
        """Get all collected data as a dictionary."""
        return {
            'step1a': self.step1a_data,
            'step1b': self.step1b_data,
            'step1c': self.step1c_data,
            'step1c_layer': self.step1c_layer_data,
            'step2a': self.step2a_data,
            'step2a_layer': self.step2a_layer_data,
            'step2b': self.step2b_data,
            'step2c': self.step2c_data,
            'step3a': self.step3a_data,
            'step3b': self.step3b_data
        }
    
    def mark_complete(self):
        """Mark the draft as complete."""
        self.is_complete = True
        self.updated_at = datetime.utcnow()
        self.save()
    
    def to_dict(self):
        """Convert to dictionary for easy access."""
        return {
            'id': str(self._id),
            'current_step': self.current_step,
            'step1a_data': self.step1a_data,
            'step1b_data': self.step1b_data,
            'step1c_data': self.step1c_data,
            'step1c_layer_data': self.step1c_layer_data,
            'step2a_data': self.step2a_data,
            'step2a_layer_data': self.step2a_layer_data,
            'step2b_data': self.step2b_data,
            'step2c_data': self.step2c_data,
            'step3a_data': self.step3a_data,
            'step3b_data': self.step3b_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_complete': self.is_complete
        }
