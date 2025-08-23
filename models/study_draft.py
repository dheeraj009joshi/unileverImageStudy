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
    layer_config_data = DictField(default={})  # New unified layer configuration
    layer_iped_data = DictField(default={})  # For layer study IPED parameters
    step2b_data = DictField(default={})
    step2c_data = DictField(default={})
    step3a_data = DictField(default={})
    step3a_grid_data = DictField(default={})  # For grid study task generation
    step3a_layer_data = DictField(default={})  # For layer study task generation
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
        # Handle special cases for layer-specific steps
        if step == 'layer_config':
            step_field = 'layer_config_data'
        elif step == 'layer_iped':
            step_field = 'layer_iped_data'
        elif step == '3a_grid':
            step_field = 'step3a_grid_data'
        elif step == '3a_layer':
            step_field = 'step3a_layer_data'
        else:
            step_field = f'step{step}_data'
        
        if hasattr(self, step_field):
            setattr(self, step_field, data)
            self.updated_at = datetime.utcnow()
            self.save()
        else:
            # Log error to console since we can't use current_app in models
            print(f"ERROR: Field '{step_field}' not found for step '{step}'")
    
    def get_step_data(self, step):
        """Get data for a specific step."""
        if step == 'layer_config':
            return self.layer_config_data
        elif step == 'layer_iped':
            # For layer_iped, return the IPED parameters from layer_iped_data
            return self.layer_iped_data or {}
        elif step == '3a_grid':
            return self.step3a_grid_data or {}
        elif step == '3a_layer':
            return self.step3a_layer_data or {}
        else:
            step_field = f'step{step}_data'
            return getattr(self, step_field, {})
    
    def is_step_complete(self, step):
        """Check if a specific step is complete."""
        step_data = self.get_step_data(step)
        
        # For layer-specific steps, check if they have meaningful data
        if step == 'layer_config':
            # Check if layers data exists and has at least one layer
            layers = step_data.get('layers', [])
            return len(layers) > 0 and all(len(layer.get('images', [])) > 0 for layer in layers)
        elif step == 'layer_iped':
            # Check if IPED parameters are set
            return (step_data.get('number_of_respondents') and 
                   step_data.get('exposure_tolerance_pct') is not None)
        elif step == '3a':
            # Check if task matrix has been generated
            # For grid studies, check 3a_grid data
            grid_data = self.get_step_data('3a_grid')
            if grid_data and grid_data.get('tasks_matrix'):
                return True
            # For layer studies, check 3a_layer data
            layer_data = self.get_step_data('3a_layer')
            if layer_data and layer_data.get('tasks_matrix'):
                return True
            return False
        else:
            # For other steps, check if any data exists
            return bool(step_data)
    
    def can_proceed_to_step(self, target_step):
        """Check if user can proceed to a specific step."""
        # Get study type to determine the correct flow
        study_type = self.get_step_data('1b').get('study_type', 'grid')
        
        if study_type == 'layer':
            step_order = ['1a', '1b', '1c', '2b', 'layer_config', 'layer_iped', '3a', '3b']
        else:
            step_order = ['1a', '1b', '1c', '2b', '2a', '2c', '3a', '3b']
            
        if target_step not in step_order:
            return False
            
        target_index = step_order.index(target_step)
        
        # For forward navigation, require previous steps to be complete
        for i in range(target_index):
            step_to_check = step_order[i]
            if not self.is_step_complete(step_to_check):
                print(f"DEBUG: Cannot proceed to {target_step} - step {step_to_check} is not complete")
                return False
        return True
    
    def can_access_step(self, target_step):
        """Check if user can access a specific step (for navigation)."""
        # Get study type to determine the correct flow
        study_type = self.get_step_data('1b').get('study_type', 'grid')
        
        if study_type == 'layer':
            step_order = ['1a', '1b', '1c', '2b', 'layer_config', 'layer_iped', '3a', '3b']
        else:
            step_order = ['1a', '1b', '1c', '2b', '2a', '2c', '3a', '3b']
            
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
        elif target_step == '2b':  # step2b (Classification Questions) - common for both study types
            return self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c')
        elif target_step in ['2a', 'layer_config']:  # Content setup step (varies by study type)
            if target_step == '2a':  # Grid study elements
                return self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c') and self.is_step_complete('2b')
            else:  # Layer study configuration
                return self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c') and self.is_step_complete('2b')
        else:  # steps 2c, layer_iped, 3a, 3b
            if target_step in ['2c', 'layer_iped']:  # IPED parameters
                if target_step == '2c':  # Grid study IPED
                    return (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and 
                           self.is_step_complete('2a'))
                else:  # Layer study IPED
                    return (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and 
                           self.is_step_complete('layer_config'))
            else:  # steps 3a, 3b
                if study_type == 'layer':
                    # For layer studies, check layer_config and layer_iped
                    return (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and
                           self.is_step_complete('layer_config') and self.is_step_complete('layer_iped'))
                else:
                    # For grid studies, check step2a and step2c
                    return (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and
                           self.is_step_complete('2a') and self.is_step_complete('2c'))
    
    def get_all_data(self):
        """Get all collected data as a dictionary."""
        return {
            'step1a': self.step1a_data,
            'step1b': self.step1b_data,
            'step1c': self.step1c_data,
            'step1c_layer_data': self.step1c_layer_data,
            'step2a': self.step2a_data,
            'step2a_layer_data': self.step2a_layer_data,
            'layer_config_data': self.layer_config_data,
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
            'layer_config_data': self.layer_config_data,
            'step2b_data': self.step2b_data,
            'step2c_data': self.step2c_data,
            'step3a_data': self.step3a_data,
            'step3b_data': self.step3b_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_complete': self.is_complete
        }
