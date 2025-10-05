from mongoengine import Document, StringField, DictField, DateTimeField, ReferenceField, UUIDField, BooleanField
from datetime import datetime
import uuid
import time

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
    grid_config_data = DictField(default={})  # For grid study categories and elements
    grid_iped_data = DictField(default={})  # For grid study IPED parameters
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
        # Handle special cases for layer-specific and grid-specific steps
        if step == 'layer_config':
            step_field = 'layer_config_data'
        elif step == 'layer_iped':
            step_field = 'layer_iped_data'
        elif step == 'grid_config':
            step_field = 'grid_config_data'
        elif step == 'grid_iped':
            step_field = 'grid_iped_data'
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
        start_time = time.time()
        print(f"⏱️  [PERF] get_step_data({step}) started")
        
        if step == 'layer_config':
            result = self.layer_config_data
        elif step == 'layer_iped':
            # For layer_iped, return the IPED parameters from layer_iped_data
            result = self.layer_iped_data or {}
        elif step == 'grid_config':
            result = self.grid_config_data
        elif step == 'grid_iped':
            # For grid_iped, return the IPED parameters from grid_iped_data
            result = self.grid_iped_data or {}
        elif step == '3a_grid':
            result = self.step3a_grid_data or {}
        elif step == '3a_layer':
            result = self.step3a_layer_data or {}
        else:
            step_field = f'step{step}_data'
            result = getattr(self, step_field, {})
        
        total_duration = time.time() - start_time
        print(f"⏱️  [PERF] get_step_data({step}) total: {total_duration:.3f}s")
        return result
    
    def is_step_complete(self, step):
        """Check if a specific step is complete."""
        start_time = time.time()
        print(f"⏱️  [PERF] is_step_complete({step}) started")
        
        step_data_start = time.time()
        step_data = self.get_step_data(step)
        step_data_duration = time.time() - step_data_start
        print(f"⏱️  [PERF] Step data retrieval took {step_data_duration:.3f}s")
        
        # For layer-specific steps, check if they have meaningful data
        if step == 'layer_config':
            # Check if layers data exists and has at least one layer with images
            layers = step_data.get('layers', [])
            layers_with_images = [layer for layer in layers if len(layer.get('images', [])) > 0]
            result = len(layers_with_images) > 0
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - {result}")
            print(f"⏱️  [PERF] Total layers: {len(layers)}, Layers with images: {len(layers_with_images)}")
            return result
        elif step == 'grid_config':
            # Check if grid categories data exists and has at least one category with elements
            categories = step_data.get('categories', [])
            result = len(categories) > 0 and all(len(category.get('elements', [])) > 0 for category in categories)
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - {result}")
            return result
        elif step == 'grid_iped':
            # Check if IPED parameters are set
            result = (step_data.get('number_of_respondents') and
                   step_data.get('exposure_tolerance_cv') is not None)
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - {result}")
            return result
        elif step == 'layer_iped':
            # Check if IPED parameters are set
            result = (step_data.get('number_of_respondents') and 
                   step_data.get('exposure_tolerance_pct') is not None)
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - {result}")
            return result
        elif step == '3a':
            # Check if task matrix has been generated
            # For grid studies, check 3a_grid data
            grid_data_start = time.time()
            grid_data = self.get_step_data('3a_grid')
            grid_data_duration = time.time() - grid_data_start
            print(f"⏱️  [PERF] 3a_grid data retrieval took {grid_data_duration:.3f}s")
            
            if grid_data and grid_data.get('tasks_matrix'):
                total_duration = time.time() - start_time
                print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - TRUE (grid)")
                return True
            # For layer studies, check 3a_layer data
            layer_data_start = time.time()
            layer_data = self.get_step_data('3a_layer')
            layer_data_duration = time.time() - layer_data_start
            print(f"⏱️  [PERF] 3a_layer data retrieval took {layer_data_duration:.3f}s")
            
            if layer_data and layer_data.get('tasks_matrix'):
                total_duration = time.time() - start_time
                print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - TRUE (layer)")
                return True
            
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - FALSE")
            return False
        else:
            # For other steps, check if any data exists
            result = bool(step_data)
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] is_step_complete({step}) total: {total_duration:.3f}s - {result}")
            return result
    
    def can_proceed_to_step(self, target_step):
        """Check if user can proceed to a specific step."""
        start_time = time.time()
        print(f"⏱️  [PERF] can_proceed_to_step({target_step}) started")
        
        # Get study type to determine the correct flow
        study_type_start = time.time()
        study_type = self.get_step_data('1b').get('study_type', 'grid')
        study_type_duration = time.time() - study_type_start
        print(f"⏱️  [PERF] Study type retrieval took {study_type_duration:.3f}s")
        
        if study_type == 'layer':
            step_order = ['1a', '1b', '1c', '2b', 'layer_config', 'layer_iped', '3a', '3b']
        else:
            step_order = ['1a', '1b', '1c', '2b', 'grid_config', 'grid_iped', '3a', '3b']
            
        if target_step not in step_order:
            return False
            
        target_index = step_order.index(target_step)
        
        # For forward navigation, require previous steps to be complete
        completion_check_start = time.time()
        for i in range(target_index):
            step_to_check = step_order[i]
            step_check_start = time.time()
            if not self.is_step_complete(step_to_check):
                step_check_duration = time.time() - step_check_start
                print(f"⏱️  [PERF] Step {step_to_check} completion check took {step_check_duration:.3f}s - NOT COMPLETE")
                print(f"DEBUG: Cannot proceed to {target_step} - step {step_to_check} is not complete")
                completion_check_duration = time.time() - completion_check_start
                print(f"⏱️  [PERF] Total completion check took {completion_check_duration:.3f}s")
                total_duration = time.time() - start_time
                print(f"⏱️  [PERF] can_proceed_to_step({target_step}) total: {total_duration:.3f}s - FALSE")
                return False
            step_check_duration = time.time() - step_check_start
            print(f"⏱️  [PERF] Step {step_to_check} completion check took {step_check_duration:.3f}s - COMPLETE")
        
        completion_check_duration = time.time() - completion_check_start
        print(f"⏱️  [PERF] Total completion check took {completion_check_duration:.3f}s")
        total_duration = time.time() - start_time
        print(f"⏱️  [PERF] can_proceed_to_step({target_step}) total: {total_duration:.3f}s - TRUE")
        return True
    
    def can_access_step(self, target_step):
        """Check if user can access a specific step (for navigation)."""
        start_time = time.time()
        print(f"⏱️  [PERF] can_access_step({target_step}) started")
        
        # Get study type to determine the correct flow
        study_type_start = time.time()
        study_type = self.get_step_data('1b').get('study_type', 'grid')
        study_type_duration = time.time() - study_type_start
        print(f"⏱️  [PERF] Study type retrieval took {study_type_duration:.3f}s")
        
        if study_type == 'layer':
            step_order = ['1a', '1b', '1c', '2b', 'layer_config', 'layer_iped', '3a', '3b']
        else:
            step_order = ['1a', '1b', '1c', '2b', 'grid_config', 'grid_iped', '3a', '3b']
            
        if target_step not in step_order:
            return False
            
        target_index = step_order.index(target_step)
        
        # For navigation (including going back), allow access to completed steps
        if target_index == 0:  # step1a
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - TRUE (step1a)")
            return True
        elif target_index == 1:  # step1b
            step_check_start = time.time()
            result = self.is_step_complete('1a')
            step_check_duration = time.time() - step_check_start
            print(f"⏱️  [PERF] Step 1a completion check took {step_check_duration:.3f}s")
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
            return result
        elif target_step == '1c':  # step1c (Rating Scale) - common for both study types
            step_check_start = time.time()
            result = self.is_step_complete('1a') and self.is_step_complete('1b')
            step_check_duration = time.time() - step_check_start
            print(f"⏱️  [PERF] Steps 1a,1b completion check took {step_check_duration:.3f}s")
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
            return result
        elif target_step == '2b':  # step2b (Classification Questions) - common for both study types
            step_check_start = time.time()
            result = self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c')
            step_check_duration = time.time() - step_check_start
            print(f"⏱️  [PERF] Steps 1a,1b,1c completion check took {step_check_duration:.3f}s")
            total_duration = time.time() - start_time
            print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
            return result
        elif target_step in ['2a', 'grid_config', 'layer_config']:  # Content setup step (varies by study type)
            if target_step == '2a':  # Grid study elements setup (legacy)
                step_check_start = time.time()
                result = self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c') and self.is_step_complete('2b')
                step_check_duration = time.time() - step_check_start
                print(f"⏱️  [PERF] Steps 1a,1b,1c,2b completion check took {step_check_duration:.3f}s")
                total_duration = time.time() - start_time
                print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
                return result
            elif target_step == 'grid_config':  # Grid study configuration
                step_check_start = time.time()
                result = self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c') and self.is_step_complete('2b')
                step_check_duration = time.time() - step_check_start
                print(f"⏱️  [PERF] Steps 1a,1b,1c,2b completion check took {step_check_duration:.3f}s")
                total_duration = time.time() - start_time
                print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
                return result
            else:  # Layer study configuration
                step_check_start = time.time()
                result = self.is_step_complete('1a') and self.is_step_complete('1b') and self.is_step_complete('1c') and self.is_step_complete('2b')
                step_check_duration = time.time() - step_check_start
                print(f"⏱️  [PERF] Steps 1a,1b,1c,2b completion check took {step_check_duration:.3f}s")
                total_duration = time.time() - start_time
                print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
                return result
        else:  # steps grid_iped, layer_iped, 3a, 3b
            if target_step in ['grid_iped', 'layer_iped']:  # IPED parameters
                if target_step == 'grid_iped':  # Grid study IPED
                    step_check_start = time.time()
                    result = (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and 
                           self.is_step_complete('grid_config'))
                    step_check_duration = time.time() - step_check_start
                    print(f"⏱️  [PERF] Steps 1a,1b,1c,2b,grid_config completion check took {step_check_duration:.3f}s")
                    total_duration = time.time() - start_time
                    print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
                    return result
                else:  # Layer study IPED
                    step_check_start = time.time()
                    result = (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and 
                           self.is_step_complete('layer_config'))
                    step_check_duration = time.time() - step_check_start
                    print(f"⏱️  [PERF] Steps 1a,1b,1c,2b,layer_config completion check took {step_check_duration:.3f}s")
                    total_duration = time.time() - start_time
                    print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
                    return result
            else:  # steps 3a, 3b
                if study_type == 'layer':
                    # For layer studies, check layer_config and layer_iped
                    step_check_start = time.time()
                    result = (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and
                           self.is_step_complete('layer_config') and self.is_step_complete('layer_iped'))
                    step_check_duration = time.time() - step_check_start
                    print(f"⏱️  [PERF] Steps 1a,1b,1c,2b,layer_config,layer_iped completion check took {step_check_duration:.3f}s")
                    total_duration = time.time() - start_time
                    print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
                    return result
                else:
                    # For grid studies, check grid_config and grid_iped
                    step_check_start = time.time()
                    result = (self.is_step_complete('1a') and self.is_step_complete('1b') and 
                           self.is_step_complete('1c') and self.is_step_complete('2b') and
                           self.is_step_complete('grid_config') and self.is_step_complete('grid_iped'))
                    step_check_duration = time.time() - step_check_start
                    print(f"⏱️  [PERF] Steps 1a,1b,1c,2b,grid_config,grid_iped completion check took {step_check_duration:.3f}s")
                    total_duration = time.time() - start_time
                    print(f"⏱️  [PERF] can_access_step({target_step}) total: {total_duration:.3f}s - {result}")
                    return result
    
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
