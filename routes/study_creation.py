from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
from models.study import Study, RatingScale, StudyElement, ClassificationQuestion, IPEDParameters
from models.study_draft import StudyDraft
from forms.study import (
    Step1aBasicDetailsForm, Step1bStudyTypeForm, Step1cRatingScaleForm,
    Step2cIPEDParametersForm, Step3aTaskGenerationForm, Step3bLaunchForm,
    LayerStudyCategoryForm
)
from utils.azure_storage import upload_to_azure, is_valid_image_file, get_file_size_mb

study_creation_bp = Blueprint('study_creation', __name__, url_prefix='/study/create')

def get_study_draft():
    """Get or create study creation draft in database."""
    # Try to get existing draft
    draft = StudyDraft.objects(user=current_user, is_complete=False).order_by('-created_at').first()
    
    if not draft:
        # Create new draft
        draft = StudyDraft(user=current_user, current_step='1a')
        draft.save()
    
    return draft

def save_uploaded_file(file, study_id):
    """Save uploaded file to Azure Blob Storage and return URL."""
    if file and file.filename:
        # Validate file type
        if not is_valid_image_file(file.filename):
            return None
        
        # Check file size (max 16MB)
        file_size_mb = get_file_size_mb(file)
        if file_size_mb > 16:
            return None
        
        # Upload to Azure
        azure_url = upload_to_azure(file)
        return azure_url
    return None

@study_creation_bp.route('/')
@login_required
def index():
    """Study creation index - redirect to first step."""
    return redirect(url_for('study_creation.step1a'))

@study_creation_bp.route('/<step_id>')
@login_required
def navigate_to_step(step_id):
    """Navigate to a specific step if accessible."""
    draft = get_study_draft()
    
    # Check if step is accessible
    if not draft.can_access_step(step_id):
        flash('You cannot access this step yet. Please complete previous steps first.', 'warning')
        return redirect(url_for('study_creation.index'))
    
    # Redirect to the appropriate step route
    if step_id == '1a':
        return redirect(url_for('study_creation.step1a'))
    elif step_id == '1b':
        return redirect(url_for('study_creation.step1b'))
    elif step_id == '1c':
        return redirect(url_for('study_creation.step1c'))
    elif step_id == '1c_layer':
        return redirect(url_for('study_creation.step1c_layer'))
    elif step_id == '2a':
        return redirect(url_for('study_creation.step2a'))
    elif step_id == '2a_layer':
        return redirect(url_for('study_creation.step2a_layer'))
    elif step_id == '2b':
        return redirect(url_for('study_creation.step2b'))
    elif step_id == '2c':
        return redirect(url_for('study_creation.step2c'))
    elif step_id == '3a':
        return redirect(url_for('study_creation.step3a'))
    elif step_id == '3b':
        return redirect(url_for('study_creation.step3b'))
    else:
        flash('Invalid step specified.', 'error')
        return redirect(url_for('study_creation.index'))

@study_creation_bp.route('/step1a', methods=['GET', 'POST'])
@login_required
def step1a():
    """Step 1a: Basic Study Details."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('1a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.index'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('1a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.index'))
    
    form = Step1aBasicDetailsForm()
    if form.validate_on_submit():
        draft.update_step_data('1a', {
            'title': form.title.data,
            'background': form.background.data,
            'language': form.language.data,
            'terms_accepted': form.terms_accepted.data
        })
        draft.current_step = '1b'
        draft.save()
        flash('Basic details saved successfully!', 'success')
        return redirect(url_for('study_creation.step1b'))
    
    # Pre-populate form if data exists
    step_data = draft.get_step_data('1a')
    if step_data:
        form.title.data = step_data.get('title', '')
        form.background.data = step_data.get('background', '')
        form.language.data = step_data.get('language', 'en')
        form.terms_accepted.data = step_data.get('terms_accepted', False)
    
    return render_template('study_creation/step1a.html', form=form, current_step='1a', draft=draft)

@study_creation_bp.route('/step1b', methods=['GET', 'POST'])
@login_required
def step1b():
    """Step 1b: Study Type & Main Question."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('1b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1a'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('1b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1a'))
    
    form = Step1bStudyTypeForm()
    if form.validate_on_submit():
        study_type = form.study_type.data
        draft.update_step_data('1b', {
            'study_type': study_type,
            'main_question': form.main_question.data,
            'orientation_text': form.orientation_text.data
        })
        
        # Both study types go to step1c (Rating Scale) - it's common for both
        draft.current_step = '1c'
        draft.save()
        flash('Study type and questions saved successfully!', 'success')
        return redirect(url_for('study_creation.step1c'))
    
    # Pre-populate form if data exists
    step_data = draft.get_step_data('1b')
    if step_data:
        form.study_type.data = step_data.get('study_type', 'image')
        form.main_question.data = step_data.get('main_question', '')
        form.orientation_text.data = step_data.get('orientation_text', '')
    
    return render_template('study_creation/step1b.html', form=form, current_step='1b', draft=draft)

@study_creation_bp.route('/step1c', methods=['GET', 'POST'])
@login_required
def step1c():
    """Step 1c: Rating Scale Configuration."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('1c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1b'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('1c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1b'))
    
    form = Step1cRatingScaleForm()
    if form.validate_on_submit():
        draft.update_step_data('1c', {
            'min_value': form.min_value.data,
            'max_value': form.max_value.data,
            'min_label': form.min_label.data,
            'max_label': form.max_label.data,
            'middle_label': form.middle_label.data
        })
        
        # Redirect based on study type
        study_type = draft.get_step_data('1b').get('study_type', 'grid')
        if study_type == 'grid':
            draft.current_step = '2a'
            draft.save()
            flash('Rating scale configuration saved successfully!', 'success')
            return redirect(url_for('study_creation.step2a'))
        else:  # layer study
            draft.current_step = '1c_layer'
            draft.save()
            flash('Rating scale configuration saved successfully!', 'success')
            return redirect(url_for('study_creation.step1c_layer'))
    
    # Pre-populate form if data exists
    step_data = draft.get_step_data('1c')
    if step_data:
        form.min_value.data = step_data.get('min_value', 1)
        form.max_value.data = step_data.get('max_value', 5)
        form.min_label.data = step_data.get('min_label', '')
        form.max_label.data = step_data.get('max_label', '')
        form.middle_label.data = step_data.get('middle_label', '')
    
    return render_template('study_creation/step1c.html', form=form, current_step='1c', draft=draft)

@study_creation_bp.route('/step1c_layer', methods=['GET', 'POST'])
@login_required
def step1c_layer():
    """Step 1c Layer: Layer Study Category Setup."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        if not draft.can_access_step('1c_layer'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1b'))
    else:
        if not draft.can_proceed_to_step('1c_layer'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1b'))
    
    form = LayerStudyCategoryForm()
    if form.validate_on_submit():
        num_categories = form.num_categories.data
        draft.update_step_data('1c_layer', {
            'num_categories': num_categories
        })
        draft.current_step = '2a_layer'
        draft.save()
        flash(f'Category setup saved! You will configure {num_categories} categories.', 'success')
        return redirect(url_for('study_creation.step2a_layer'))
    
    # Pre-populate form if data exists
    step_data = draft.get_step_data('1c_layer')
    if step_data:
        form.num_categories.data = step_data.get('num_categories', 2)
    
    return render_template('study_creation/step1c_layer.html', form=form, current_step='1c_layer', draft=draft)

@study_creation_bp.route('/step2a', methods=['GET', 'POST'])
@login_required
def step2a():
    """Step 2a: Study Elements Setup."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('2a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1c'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('2a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1c'))
    
    study_type = draft.get_step_data('1b').get('study_type', 'grid')
    
    if request.method == 'POST':
        # Handle dynamic form submission
        elements_data = []
        num_elements = int(request.form.get('num_elements', 4))
        
        for i in range(num_elements):
            element_data = {
                'element_id': f"E{i+1}",
                'name': request.form.get(f'element_{i}_name', ''),
                'description': request.form.get(f'element_{i}_description', ''),
                'alt_text': request.form.get(f'element_{i}_alt_text', '')
            }
            
            # All elements are always images by default
            file = request.files.get(f'element_{i}_image')
            current_image = request.form.get(f'element_{i}_current_image', '')
            
            if file and file.filename:
                # New image uploaded - upload to Azure and get URL
                azure_url = save_uploaded_file(file, f"element_{i}")
                if azure_url:
                    element_data['content'] = azure_url
                    element_data['element_type'] = 'image'
                    print(f"DEBUG: Uploaded image for element {i+1}: {azure_url}")
                else:
                    flash(f'Failed to upload image for element {i+1}. Please check file type and size.', 'error')
                    return render_template('study_creation/step2a.html', 
                                        study_type=study_type, num_elements=num_elements, 
                                        elements_data=elements_data, current_step='2a')
            elif current_image:
                # No new image, but current image exists - keep the current image
                element_data['content'] = current_image
                element_data['element_type'] = 'image'
                print(f"DEBUG: Using existing image for element {i+1}: {current_image}")
            else:
                # No image at all - this is required for all elements
                flash(f'Image file is required for element {i+1}', 'error')
                return render_template('study_creation/step2a.html', 
                                    study_type=study_type, num_elements=num_elements, 
                                    elements_data=elements_data, current_step='2a')
            
            elements_data.append(element_data)
        
        # Debug: Print what we're about to save
        print(f"DEBUG: Saving elements to draft:")
        for i, elem in enumerate(elements_data):
            print(f"DEBUG: Element {i}: {elem}")
        
        draft.update_step_data('2a', {
            'elements': elements_data,
            'study_type': study_type,
            'num_elements': num_elements
        })
        draft.current_step = '2b'
        draft.save()
        
        # Debug: Verify what was saved
        saved_data = draft.get_step_data('2a')
        print(f"DEBUG: Saved data: {saved_data}")
        
        flash('Study elements saved successfully!', 'success')
        return redirect(url_for('study_creation.step2b'))
    
    # Get number of elements from form or previous data or default
    if request.args.get('num_elements'):
        num_elements = int(request.args.get('num_elements'))
    else:
        # Try to get from existing step2a data
        existing_data = draft.get_step_data('2a')
        if existing_data and 'elements' in existing_data:
            # Prioritize the stored num_elements value over the existing elements count
            stored_num_elements = existing_data.get('num_elements', 4)
            existing_count = len(existing_data['elements'])
            # Use stored num_elements if it exists, otherwise use the larger of existing count or default
            num_elements = stored_num_elements if stored_num_elements > 0 else max(existing_count, 4)
        else:
            num_elements = 4
    elements_data = draft.get_step_data('2a').get('elements', []) if draft.get_step_data('2a') else []
    
    # Debug logging
    print(f"DEBUG: num_elements = {num_elements}")
    print(f"DEBUG: elements_data length = {len(elements_data) if elements_data else 0}")
    print(f"DEBUG: existing_data = {draft.get_step_data('2a')}")
    
    return render_template('study_creation/step2a.html', 
                         study_type=study_type, num_elements=num_elements, 
                         elements_data=elements_data, current_step='2a', draft=draft)

@study_creation_bp.route('/step2a_layer', methods=['GET', 'POST'])
@login_required
def step2a_layer():
    """Step 2a Layer: Layer Study Categories and Elements Setup."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        if not draft.can_access_step('2a_layer'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1c_layer'))
    else:
        if not draft.can_proceed_to_step('2a_layer'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step1c_layer'))
    
    # Get number of categories from previous step
    step1c_layer_data = draft.get_step_data('1c_layer')
    if not step1c_layer_data:
        flash('Please complete the category setup step first.', 'warning')
        return redirect(url_for('study_creation.step1c_layer'))
    
    num_categories = step1c_layer_data.get('num_categories', 2)
    if not num_categories or num_categories < 2 or num_categories > 10:
        num_categories = 2  # Default fallback
    
    if request.method == 'POST':
        # Handle dynamic form submission for categories
        categories_data = []
        
        for i in range(num_categories):
            category_id = chr(65 + i)  # A, B, C, D, etc.
            category_name = request.form.get(f'category_{i}_name', f'Category {category_id}')
            num_elements = int(request.form.get(f'category_{i}_num_elements', 4))
            
            category_elements = []
            for j in range(num_elements):
                element_data = {
                    'element_id': f"{category_id}{j+1}",
                    'name': request.form.get(f'category_{i}_element_{j}_name', ''),
                    'description': request.form.get(f'category_{i}_element_{j}_description', ''),
                    'alt_text': request.form.get(f'category_{i}_element_{j}_alt_text', '')
                }
                
                # Handle image file upload to Azure
                file = request.files.get(f'category_{i}_element_{j}_image')
                current_image = request.form.get(f'category_{i}_element_{j}_current_image', '')
                
                if file and file.filename:
                    azure_url = save_uploaded_file(file, f"category_{i}_element_{j}")
                    if azure_url:
                        element_data['content'] = azure_url
                        element_data['element_type'] = 'image'
                    else:
                        flash(f'Failed to upload image for {category_id}{j+1}. Please check file type and size.', 'error')
                        return render_template('study_creation/step2a_layer.html', 
                                            num_categories=num_categories, current_step='2a_layer')
                elif current_image:
                    element_data['content'] = current_image
                    element_data['element_type'] = 'image'
                else:
                    flash(f'Image file is required for {category_id}{j+1}', 'error')
                    return render_template('study_creation/step2a_layer.html', 
                                        num_categories=num_categories, current_step='2a_layer')
                
                category_elements.append(element_data)
            
            categories_data.append({
                'category_id': category_id,
                'category_name': category_name,
                'elements': category_elements,
                'order': i
            })
        
        draft.update_step_data('2a_layer', {
            'categories': categories_data,
            'study_type': 'layer'
        })
        draft.current_step = '2b'
        draft.save()
        flash('Layer study categories and elements saved successfully!', 'success')
        return redirect(url_for('study_creation.step2b'))
    
    # Get existing data if available
    existing_data = draft.get_step_data('2a_layer')
    categories_data = existing_data.get('categories', []) if existing_data else []
    
    return render_template('study_creation/step2a_layer.html', 
                         num_categories=num_categories, 
                         categories_data=categories_data,
                         current_step='2a_layer', draft=draft)

@study_creation_bp.route('/step2b', methods=['GET', 'POST'])
@login_required
def step2b():
    """Step 2b: Classification Questions."""
    draft = get_study_draft()
    
    # Determine which previous step to check based on study type
    study_type = draft.get_step_data('1b').get('study_type', 'grid')
    previous_step = '2a_layer' if study_type == 'layer' else '2a'
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('2b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for(f'study_creation.{previous_step}'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('2b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for(f'study_creation.{previous_step}'))
    
    if request.method == 'POST':
        # Handle dynamic form submission with individual option fields
        questions_data = []
        num_questions = int(request.form.get('num_questions', 2))
        
        for i in range(num_questions):
            # Collect all options for this question
            answer_options = []
            option_index = 0
            while True:
                option_value = request.form.get(f'question_{i}_option_{option_index}')
                if option_value is None:  # No more options
                    break
                if option_value.strip():  # Only add non-empty options
                    answer_options.append(option_value.strip())
                option_index += 1
            
            question_data = {
                'question_id': f"Q{i+1}",
                'question_text': request.form.get(f'question_{i}_text', ''),
                'answer_options': answer_options,
                'is_required': request.form.get(f'question_{i}_required') == 'on',
                'order': i + 1
            }
            questions_data.append(question_data)
        
        draft.update_step_data('2b', {
            'questions': questions_data
        })
        draft.current_step = '2c'
        draft.save()
        flash('Classification questions saved successfully!', 'success')
        return redirect(url_for('study_creation.step2c'))
    
    # Pre-populate from stored data if available
    stored_step2b = draft.get_step_data('2b') or {}
    if stored_step2b and stored_step2b.get('questions'):
        num_questions = len(stored_step2b['questions'])
        questions_data = stored_step2b['questions']
    else:
        num_questions = 2
        questions_data = []
    
    return render_template('study_creation/step2b.html', 
                         num_questions=num_questions, questions_data=questions_data, current_step='2b', draft=draft)

@study_creation_bp.route('/step2c', methods=['GET', 'POST'])
@login_required
def step2c():
    """Step 2c: IPED Parameters."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('2c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2b'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('2c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2b'))
    
    form = Step2cIPEDParametersForm()
    
    # Pre-populate from DB if available; otherwise set sensible defaults
    stored_step2c = draft.get_step_data('2c') or {}
    if request.method == 'GET':
        if stored_step2c:
            form.num_elements.data = stored_step2c.get('num_elements')
            form.tasks_per_consumer.data = stored_step2c.get('tasks_per_consumer')
            form.number_of_respondents.data = stored_step2c.get('number_of_respondents')
            form.min_active_elements.data = stored_step2c.get('min_active_elements')
            form.max_active_elements.data = stored_step2c.get('max_active_elements')
        else:
            # Set default values based on previous step elements count
            study_type = draft.get_step_data('1b').get('study_type', 'grid')
            if study_type == 'grid':
                step2a_data = draft.get_step_data('2a')
                if step2a_data:
                    form.num_elements.data = len(step2a_data.get('elements', []))
            else:  # layer study
                step2a_layer_data = draft.get_step_data('2a_layer')
                if step2a_layer_data:
                    total_elements = sum(len(cat.get('elements', [])) for cat in step2a_layer_data.get('categories', []))
                    form.num_elements.data = total_elements
    
    if form.validate_on_submit():
        draft.update_step_data('2c', {
            'num_elements': form.num_elements.data,
            'tasks_per_consumer': form.tasks_per_consumer.data,
            'number_of_respondents': form.number_of_respondents.data,
            'min_active_elements': form.min_active_elements.data,
            'max_active_elements': form.max_active_elements.data,
            'total_tasks': form.tasks_per_consumer.data * form.number_of_respondents.data
        })
        draft.current_step = '3a'
        draft.save()
        flash('IPED parameters saved successfully!', 'success')
        return redirect(url_for('study_creation.step3a'))
    
    return render_template('study_creation/step2c.html', form=form, current_step='2c', draft=draft)

@study_creation_bp.route('/step3a', methods=['GET', 'POST'])
@login_required
def step3a():
    """Step 3a: IPED Task Matrix Generation."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('3a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2c'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('3a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2c'))
    
    # Get study type to determine functionality
    study_type = draft.get_step_data('1b').get('study_type', 'grid')
    
    form = Step3aTaskGenerationForm()
    
    # Pre-populate 3a state if stored
    stored_step3a = draft.get_step_data('3a') or {}
    if request.method == 'GET' and stored_step3a:
        if hasattr(form, 'regenerate_matrix'):
            form.regenerate_matrix.data = stored_step3a.get('regenerate_matrix', False)
    
    if form.validate_on_submit() or not draft.get_step_data('3a'):
        if study_type == 'grid':
            # Generate or regenerate task matrix for grid studies
            try:
                print(f"DEBUG: Starting task generation for grid study")
                
                # Create temporary study object to generate tasks
                temp_study = Study()
                step2c_data = draft.get_step_data('2c')
                
                print(f"DEBUG: Step 2c data: {step2c_data}")
                
                if not step2c_data:
                    flash('IPED parameters not found. Please complete step 2c first.', 'error')
                    return render_template('study_creation/step3a.html', 
                                        form=form, tasks_matrix={}, 
                                        step2c_data={},
                                        matrix_summary={},
                                        current_step='3a', draft=draft,
                                        study_type=study_type)
                
                # Set IPED parameters
                temp_study.iped_parameters = IPEDParameters(
                    num_elements=step2c_data['num_elements'],
                    tasks_per_consumer=step2c_data['tasks_per_consumer'],
                    number_of_respondents=step2c_data['number_of_respondents'],
                    min_active_elements=step2c_data['min_active_elements'],
                    max_active_elements=step2c_data['max_active_elements'],
                    total_tasks=step2c_data['total_tasks']
                )
                
                print(f"DEBUG: IPED parameters set: {temp_study.iped_parameters}")
                
                # Get elements from step2a data
                step2a_data = draft.get_step_data('2a')
                print(f"DEBUG: Step 2a data: {step2a_data}")
                
                if step2a_data and 'elements' in step2a_data:
                    temp_study.elements = []
                    for i, element_data in enumerate(step2a_data['elements']):
                        print(f"DEBUG: Processing element {i}: {element_data}")
                        element = StudyElement(
                            name=element_data.get('name', ''),
                            description=element_data.get('description', ''),
                            element_type=element_data.get('element_type', 'image'),
                            content=element_data.get('content', ''),
                            alt_text=element_data.get('alt_text', '')
                        )
                        print(f"DEBUG: Created element: {element}")
                        print(f"DEBUG: Element content: {element.content}")
                        temp_study.elements.append(element)
                    
                    print(f"DEBUG: Created {len(temp_study.elements)} elements")
                    print(f"DEBUG: All elements: {temp_study.elements}")
                else:
                    print(f"DEBUG: No step2a data or no elements found")
                    print(f"DEBUG: step2a_data: {step2a_data}")
                
                # Generate task matrix
                print(f"DEBUG: Calling generate_tasks()")
                tasks_matrix = temp_study.generate_tasks()
                print(f"DEBUG: Task matrix generated successfully: {len(tasks_matrix)} respondents")
                
                draft.update_step_data('3a', {
                    'tasks_matrix': tasks_matrix,
                    'generated_at': datetime.utcnow().isoformat(),
                    'regenerate_matrix': bool(getattr(form, 'regenerate_matrix', False) and form.regenerate_matrix.data)
                })
                draft.current_step = '3b'
                draft.save()
                
                flash('Task matrix generated successfully!', 'success')
                return redirect(url_for('study_creation.step3b'))
                
            except Exception as e:
                error_msg = f'Error generating task matrix: {str(e)}'
                print(f"DEBUG: Task generation error: {e}")
                print(f"DEBUG: Error type: {type(e)}")
                import traceback
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                flash(error_msg, 'error')
        else:
            # Layer studies not implemented yet
            flash('Task matrix generation for layer studies is not implemented yet.', 'warning')
            return render_template('study_creation/step3a.html', 
                                form=form, tasks_matrix={}, 
                                step2c_data={},
                                matrix_summary={},
                                current_step='3a', draft=draft,
                                study_type=study_type)
    
    # Show task matrix preview if available
    tasks_matrix = stored_step3a.get('tasks_matrix', {}) if stored_step3a else {}
    
    # Get step2c data for pre-population
    step2c_data = draft.get_step_data('2c') or {}
    
    # Calculate matrix summary statistics
    matrix_summary = {}
    if tasks_matrix:
        total_tasks = sum(len(tasks) for tasks in tasks_matrix.values())
        total_respondents = len(tasks_matrix)
        tasks_per_respondent = total_tasks // total_respondents if total_respondents > 0 else 0
        
        # Get elements per task from step2c data
        min_elements = step2c_data.get('min_active_elements', 0)
        max_elements = step2c_data.get('max_active_elements', 0)
        elements_per_task = f"{min_elements}-{max_elements}" if min_elements and max_elements else "-"
        
        matrix_summary = {
            'total_tasks': total_tasks,
            'total_respondents': total_respondents,
            'tasks_per_respondent': tasks_per_respondent,
            'elements_per_task': elements_per_task
        }
    
    return render_template('study_creation/step3a.html', 
                         form=form, tasks_matrix=tasks_matrix, 
                         step2c_data=step2c_data,
                         matrix_summary=matrix_summary,
                         current_step='3a', draft=draft,
                         study_type=study_type)

@study_creation_bp.route('/step3b', methods=['GET', 'POST'])
@login_required
def step3b():
    """Step 3b: Study Preview & Launch."""
    draft = get_study_draft()
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        if not draft.can_access_step('3b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step3a'))
    else:
        # For POST requests (submitting), use can_proceed_to_step
        if not draft.can_proceed_to_step('3b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step3a'))
    
    form = Step3bLaunchForm()
    
    # Pre-populate from stored step3b data
    stored_step3b = draft.get_step_data('3b') or {}
    if request.method == 'GET' and stored_step3b:
        if hasattr(form, 'launch_study'):
            form.launch_study.data = stored_step3b.get('launch_study', False)
    
    if form.validate_on_submit():
        print(f"DEBUG: Form validated successfully")
        print(f"DEBUG: launch_study checkbox value: {form.launch_study.data}")
        
        # Check if user has confirmed they want to launch
        if not form.launch_study.data:
            flash('Please check the confirmation checkbox to launch your study.', 'warning')
            return render_template('study_creation/step3b.html', 
                                 form=form, study_data=preview_data, current_step='3b', draft=draft)
        
        # Persist current 3b state in draft
        draft.update_step_data('3b', {
            'launch_study': True
        })
        draft.save()
        print(f"DEBUG: Draft saved with step3b data")
        try:
            # Create the study
            study = Study(
                title=draft.get_step_data('1a')['title'],
                background=draft.get_step_data('1a')['background'],
                language=draft.get_step_data('1a')['language'],
                main_question=draft.get_step_data('1b')['main_question'],
                orientation_text=draft.get_step_data('1b')['orientation_text'],
                study_type=draft.get_step_data('1b')['study_type'],
                creator=current_user,
                share_token=uuid.uuid4().hex,
                status='active'
            )
            
            # Set rating scale
            step1c_data = draft.get_step_data('1c')
            study.rating_scale = RatingScale(
                min_value=step1c_data['min_value'],
                max_value=step1c_data['max_value'],
                min_label=step1c_data['min_label'],
                max_label=step1c_data['max_label'],
                middle_label=step1c_data['middle_label']
            )
            
            # Set study elements based on study type
            study_type = draft.get_step_data('1b').get('study_type', 'grid')
            
            if study_type == 'grid':
                # Grid study - traditional elements
                elements = []
                step2a_data = draft.get_step_data('2a')
                if step2a_data and 'elements' in step2a_data:
                    for i, element_data in enumerate(step2a_data['elements']):
                        element = StudyElement(
                            element_id=f"E{i+1}",
                            name=element_data['name'],
                            description=element_data.get('description', ''),
                            element_type=element_data['element_type'],
                            content=element_data['content'],
                            alt_text=element_data.get('alt_text', '')
                        )
                        elements.append(element)
                study.elements = elements
            else:
                # Layer study - categorized elements
                step2a_layer_data = draft.get_step_data('2a_layer')
                if step2a_layer_data.get('categories'):
                    from models.study import LayerCategory
                    layer_categories = []
                    for category_data in step2a_layer_data['categories']:
                        category_elements = []
                        for j, element_data in enumerate(category_data['elements']):
                            element = StudyElement(
                                element_id=f"{category_data['category_id']}{j+1}",
                                name=element_data['name'],
                                description=element_data.get('description', ''),
                                element_type=element_data['element_type'],
                                content=element_data['content'],
                                alt_text=element_data.get('alt_text', '')
                            )
                            category_elements.append(element)
                        
                        category = LayerCategory(
                            category_id=category_data['category_id'],
                            category_name=category_data['category_name'],
                            elements=category_elements,
                            order=category_data['order']
                        )
                        layer_categories.append(category)
                    study.layer_categories = layer_categories
            
            # Set classification questions
            step2b_data = draft.get_step_data('2b')
            print(f"DEBUG: Step2b data: {step2b_data}")
            
            if step2b_data and step2b_data.get('questions'):
                questions = []
                for question_data in step2b_data['questions']:
                    # Clean up any old question_type fields that might exist
                    if 'question_type' in question_data:
                        del question_data['question_type']
                    
                    # Ensure all required fields are present
                    if not question_data.get('question_id') or not question_data.get('question_text'):
                        print(f"DEBUG: Skipping invalid question data: {question_data}")
                        continue
                    
                    question = ClassificationQuestion(
                        question_id=question_data['question_id'],
                        question_text=question_data['question_text'],
                        answer_options=question_data.get('answer_options', []),
                        is_required=question_data['is_required'],
                        order=question_data['order']
                    )
                    questions.append(question)
                    print(f"DEBUG: Created question: {question.question_id} - {question.question_text}")
                
                study.classification_questions = questions
                print(f"DEBUG: Set {len(questions)} classification questions")
            
            # Set IPED parameters
            step2c_data = draft.get_step_data('2c')
            study.iped_parameters = IPEDParameters(
                num_elements=step2c_data['num_elements'],
                tasks_per_consumer=step2c_data['tasks_per_consumer'],
                number_of_respondents=step2c_data['number_of_respondents'],
                min_active_elements=step2c_data['min_active_elements'],
                max_active_elements=step2c_data['max_active_elements'],
                total_tasks=step2c_data['total_tasks']
            )
            
            # Set generated tasks
            step3a_data = draft.get_step_data('3a')
            print(f"DEBUG: Step3a data: {step3a_data}")
            
            if not step3a_data:
                flash('Step 3a data not found. Please go back to step 3a and generate the task matrix first.', 'error')
                return render_template('study_creation/step3b.html', 
                                     form=form, study_data=preview_data, current_step='3b', draft=draft)
            
            if 'tasks_matrix' not in step3a_data:
                flash('Task matrix not found in step 3a data. Please go back to step 3a and generate the task matrix first.', 'error')
                return render_template('study_creation/step3b.html', 
                                     form=form, study_data=preview_data, current_step='3b', draft=draft)
            
            study.tasks = step3a_data['tasks_matrix']
            print(f"DEBUG: Tasks matrix set successfully")
            
            # Generate share URL
            study.generate_share_url(request.host_url.rstrip('/'))
            
            # Save study
            study.save()
            print(f"DEBUG: Study saved with ID: {study._id}")
            
            # Update user's studies list
            current_user.studies.append(study)
            current_user.save()
            print(f"DEBUG: User studies list updated")
            
            # Mark draft as complete and delete it
            draft.mark_complete()
            draft.delete()
            print(f"DEBUG: Draft marked complete and deleted")
            
            flash('Study created successfully!', 'success')
            print(f"DEBUG: Redirecting to study detail page: {study._id}")
            return redirect(url_for('dashboard.study_detail', study_id=study._id))
            
        except Exception as e:
            print(f"DEBUG: Exception occurred during study creation: {str(e)}")
            print(f"DEBUG: Exception type: {type(e).__name__}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            flash(f'Error creating study: {str(e)}', 'error')
    
    # Debug form validation
    if request.method == 'POST':
        print(f"DEBUG: POST request received")
        print(f"DEBUG: Form validation errors: {form.errors}")
        print(f"DEBUG: Form data: {form.data}")
        
        # Debug all step data
        print(f"DEBUG: All step data available:")
        print(f"DEBUG: Step1a: {draft.get_step_data('1a')}")
        print(f"DEBUG: Step1b: {draft.get_step_data('1b')}")
        print(f"DEBUG: Step1c: {draft.get_step_data('1c')}")
        print(f"DEBUG: Step2a: {draft.get_step_data('2a')}")
        print(f"DEBUG: Step2b: {draft.get_step_data('2b')}")
        print(f"DEBUG: Step2c: {draft.get_step_data('2c')}")
        print(f"DEBUG: Step3a: {draft.get_step_data('3a')}")
        print(f"DEBUG: Step3b: {draft.get_step_data('3b')}")
    
    # Prepare study preview data
    preview_data = {
        'step1a': draft.get_step_data('1a'),
        'step1b': draft.get_step_data('1b'),
        'step1c': draft.get_step_data('1c'),
        'step1c_layer': draft.get_step_data('1c_layer'),
        'step2a': draft.get_step_data('2a'),
        'step2a_layer': draft.get_step_data('2a_layer'),
        'step2b': draft.get_step_data('2b'),
        'step2c': draft.get_step_data('2c'),
        'step3a': draft.get_step_data('3a')
    }
    
    # Debug: Print the data structure
    print(f"DEBUG: Step3b preview data structure:")
    print(f"DEBUG: Step2a data: {preview_data['step2a']}")
    if preview_data['step2a']:
        print(f"DEBUG: Step2a elements: {preview_data['step2a'].get('elements', [])}")
        if 'elements' in preview_data['step2a']:
            for i, elem in enumerate(preview_data['step2a']['elements']):
                print(f"DEBUG: Element {i}: {elem}")
    
    return render_template('study_creation/step3b.html', 
                         form=form, study_data=preview_data, current_step='3b', draft=draft)

@study_creation_bp.route('/reset')
@login_required
def reset():
    """Reset study creation draft."""
    draft = StudyDraft.objects(user=current_user, is_complete=False).order_by('-created_at').first()
    if draft:
        draft.delete()
    flash('Study creation draft reset. You can start over.', 'info')
    return redirect(url_for('study_creation.step1a'))

@study_creation_bp.route('/debug-draft')
@login_required
def debug_draft():
    """Debug route to check draft data."""
    draft = get_study_draft()
    if not draft:
        return "No draft found"
    
    debug_info = {
        'draft_id': str(draft._id),
        'current_step': draft.current_step,
        'step1a_data': draft.step1a_data,
        'step1b_data': draft.step1b_data,
        'step1c_data': draft.step1c_data,
        'step1c_layer_data': draft.step1c_layer_data,
        'step2a_data': draft.step2a_data,
        'step2a_layer_data': draft.step2a_layer_data,
        'step2b_data': draft.step2b_data,
        'step2c_data': draft.step2c_data,
        'step3a_data': draft.step3a_data,
        'step3b_data': draft.step3b_data,
        'step1a_complete': draft.is_step_complete('1a'),
        'step1b_complete': draft.is_step_complete('1b'),
        'step1c_complete': draft.is_step_complete('1c'),
        'step1c_layer_complete': draft.is_step_complete('1c_layer'),
        'step2a_complete': draft.is_step_complete('2a'),
        'step2a_layer_complete': draft.is_step_complete('2a_layer'),
        'step2b_complete': draft.is_step_complete('2b'),
        'step2c_complete': draft.is_step_complete('2c'),
        'step3a_complete': draft.is_step_complete('3a'),
        'step3b_complete': draft.is_step_complete('3b'),
    }
    
    return f"""
    <h1>Draft Debug Info</h1>
    <pre>{debug_info}</pre>
    
    <h2>Raw Data</h2>
    <pre>step1c_layer_data: {draft.step1c_layer_data}</pre>
    <pre>step2a_layer_data: {draft.step2a_layer_data}</pre>
    
    <h2>Completion Checks</h2>
    <pre>1c_layer complete: {draft.is_step_complete('1c_layer')}</pre>
    <pre>2a_layer complete: {draft.is_step_complete('2a_layer')}</pre>
    """
