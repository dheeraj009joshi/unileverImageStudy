from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import uuid
import json
from datetime import datetime
import time
from models.study import Study, RatingScale, StudyElement, ClassificationQuestion, IPEDParameters, LayerImage, StudyLayer, GridCategory
from models.study_draft import StudyDraft
from models.user import User
from forms.study import (
    Step1aBasicDetailsForm, Step1bStudyTypeForm, Step1cRatingScaleForm,
    Step2cIPEDParametersForm, Step3aTaskGenerationForm, Step3bLaunchForm,
    LayerConfigForm, LayerIPEDForm,GridConfigForm,GridIPEDForm
)
from utils.azure_storage import upload_to_azure, upload_multiple_files_to_azure, upload_layer_images_to_azure, is_valid_image_file, get_file_size_mb
from utils.task_generation import generate_grid_tasks_v2, generate_layer_tasks_v2
import math
import base64
import io
import mimetypes
import json

study_creation_bp = Blueprint('study_creation', __name__, url_prefix='/study/create')

def get_study_draft():
    """Get or create study creation draft in database."""
    start_time = time.time()
    print(f"⏱️  [PERF] Starting get_study_draft() at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    # Try to get existing draft
    db_start = time.time()
    draft = StudyDraft.objects(user=current_user, is_complete=False).order_by('-created_at').first()
    db_duration = time.time() - db_start
    print(f"⏱️  [PERF] Database query took {db_duration:.3f}s")
    
    if not draft:
        # Create new draft
        create_start = time.time()
        draft = StudyDraft(user=current_user, current_step='1a')
        draft.save()
        create_duration = time.time() - create_start
        print(f"⏱️  [PERF] Draft creation took {create_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] get_study_draft() total: {total_duration:.3f}s")
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
    start_time = time.time()
    print(f"⏱️  [PERF] Index route started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    redirect_start = time.time()
    result = redirect(url_for('study_creation.step1a'))
    redirect_duration = time.time() - redirect_start
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Index route total: {total_duration:.3f}s (redirect: {redirect_duration:.3f}s)")
    return result

@study_creation_bp.route('/<step_id>')
@login_required
def navigate_to_step(step_id):
    """Navigate to a specific step if accessible."""
    start_time = time.time()
    print(f"⏱️  [PERF] Navigate to step {step_id} started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    # Check if step is accessible (step1a is always accessible)
    access_start = time.time()
    if step_id != '1a' and not draft.can_access_step(step_id):
        flash('You cannot access this step yet. Please complete previous steps first.', 'warning')
        return redirect(url_for('study_creation.index'))
    access_duration = time.time() - access_start
    print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    
    # Redirect to the appropriate step route
    redirect_start = time.time()
    if step_id == '1a':
        result = redirect(url_for('study_creation.step1a'))
    elif step_id == '1b':
        result = redirect(url_for('study_creation.step1b'))
    elif step_id == '1c':
        result = redirect(url_for('study_creation.step1c'))
    elif step_id == 'layer_config':
        result = redirect(url_for('study_creation.layer_config'))
    elif step_id == 'grid_config':
        result = redirect(url_for('study_creation.grid_config'))
    elif step_id == 'grid_iped':
        result = redirect(url_for('study_creation.grid_iped'))
    elif step_id == '2a':
        result = redirect(url_for('study_creation.step2a'))
    elif step_id == '2b':
        result = redirect(url_for('study_creation.step2b'))
    elif step_id == '2c':
        result = redirect(url_for('study_creation.step2c'))
    elif step_id == '3a':
        result = redirect(url_for('study_creation.step3a'))
    elif step_id == '3b':
        result = redirect(url_for('study_creation.step3b'))
    elif step_id == 'layer_iped':
        result = redirect(url_for('study_creation.layer_iped'))
    else:
        flash('Invalid step specified.', 'error')
        result = redirect(url_for('study_creation.index'))
    
    redirect_duration = time.time() - redirect_start
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Navigate to step {step_id} total: {total_duration:.3f}s (redirect: {redirect_duration:.3f}s)")
    return result

@study_creation_bp.route('/step1a', methods=['GET', 'POST'])
@login_required
def step1a():
    """Step 1a: Basic Study Details."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step1a started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    # Step1a is always accessible - no validation needed
    
    form_start = time.time()
    form = Step1aBasicDetailsForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    if form.validate_on_submit():
        validation_start = time.time()
        draft.update_step_data('1a', {
            'title': form.title.data,
            'background': form.background.data,
            'language': form.language.data,
            'terms_accepted': form.terms_accepted.data
        })
        draft.current_step = '1b'
        draft.save()
        validation_duration = time.time() - validation_start
        print(f"⏱️  [PERF] Form validation and save took {validation_duration:.3f}s")
        
        flash('Basic details saved successfully!', 'success')
        return redirect(url_for('study_creation.step1b'))
    
    # Pre-populate form if data exists
    populate_start = time.time()
    step_data = draft.get_step_data('1a')
    if step_data:
        form.title.data = step_data.get('title', '')
        form.background.data = step_data.get('background', '')
        form.language.data = step_data.get('language', 'en')
        form.terms_accepted.data = step_data.get('terms_accepted', False)
    populate_duration = time.time() - populate_start
    print(f"⏱️  [PERF] Form population took {populate_duration:.3f}s")
    
    render_start = time.time()
    result = render_template('study_creation/step1a.html', form=form, current_step='1a', draft=draft)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Step1a total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/step1b', methods=['GET', 'POST'])
@login_required
def step1b():
    """Step 1b: Study Type & Main Question."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step1b started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        access_start = time.time()
        if not draft.can_access_step('1b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.index'))
        access_duration = time.time() - access_start
        print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    else:
        # For POST requests (submitting), use can_proceed_to_step
        proceed_start = time.time()
        if not draft.can_proceed_to_step('1b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.index'))
        proceed_duration = time.time() - proceed_start
        print(f"⏱️  [PERF] Step proceed check took {proceed_duration:.3f}s")
    
    form_start = time.time()
    form = Step1bStudyTypeForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    if form.validate_on_submit():
        validation_start = time.time()
        study_type = form.study_type.data
        draft.update_step_data('1b', {
            'study_type': study_type,
            'main_question': form.main_question.data,
            'orientation_text': form.orientation_text.data
        })
        
        # Both study types go to step1c (Rating Scale) - it's common for both
        draft.current_step = '1c'
        draft.save()
        validation_duration = time.time() - validation_start
        print(f"⏱️  [PERF] Form validation and save took {validation_duration:.3f}s")
        
        flash('Study type and questions saved successfully!', 'success')
        return redirect(url_for('study_creation.step1c'))
    
    # Pre-populate form if data exists
    populate_start = time.time()
    step_data = draft.get_step_data('1b')
    if step_data:
        form.study_type.data = step_data.get('study_type', 'image')
        form.main_question.data = step_data.get('main_question', '')
        form.orientation_text.data = step_data.get('orientation_text', '')
    populate_duration = time.time() - populate_start
    print(f"⏱️  [PERF] Form population took {populate_duration:.3f}s")
    
    render_start = time.time()
    result = render_template('study_creation/step1b.html', form=form, current_step='1b', draft=draft)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Step1b total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/step1c', methods=['GET', 'POST'])
@login_required
def step1c():
    """Step 1c: Rating Scale Configuration."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step1c started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        access_start = time.time()
        if not draft.can_access_step('1c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.index'))
        access_duration = time.time() - access_start
        print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    else:
        # For POST requests (submitting), use can_proceed_to_step
        proceed_start = time.time()
        if not draft.can_proceed_to_step('1c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.index'))
        proceed_duration = time.time() - proceed_start
        print(f"⏱️  [PERF] Step proceed check took {proceed_duration:.3f}s")
    
    form_start = time.time()
    form = Step1cRatingScaleForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    if form.validate_on_submit():
        validation_start = time.time()
        draft.update_step_data('1c', {
            'min_value': form.min_value.data,
            'max_value': form.max_value.data,
            'min_label': form.min_label.data,
            'max_label': form.max_label.data,
            'middle_label': form.middle_label.data
        })
        draft.current_step = '2b'
        draft.save()
        validation_duration = time.time() - validation_start
        print(f"⏱️  [PERF] Form validation and save took {validation_duration:.3f}s")
        
        flash('Rating scale configuration saved successfully!', 'success')
        return redirect(url_for('study_creation.step2b'))
    
    # Pre-populate form if data exists
    populate_start = time.time()
    step_data = draft.get_step_data('1c')
    if step_data:
        form.min_value.data = step_data.get('min_value', 1)
        form.max_value.data = step_data.get('max_value', 5)
        form.min_label.data = step_data.get('min_label', '')
        form.max_label.data = step_data.get('max_label', '')
        form.middle_label.data = step_data.get('middle_label', '')
    populate_duration = time.time() - populate_start
    print(f"⏱️  [PERF] Form population took {populate_duration:.3f}s")
    
    render_start = time.time()
    result = render_template('study_creation/step1c.html', form=form, current_step='1c', draft=draft)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Step1c total: {total_duration:.3f}s")
    return result

# REMOVED: step1c_layer route - not needed for current layer study flow

@study_creation_bp.route('/step2a', methods=['GET', 'POST'])
@login_required
def step2a():
    """Step 2a: Study Elements Setup."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step2a started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        access_start = time.time()
        if not draft.can_access_step('2a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2b'))
        access_duration = time.time() - access_start
        print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    else:
        # For POST requests (submitting), use can_proceed_to_step
        proceed_start = time.time()
        if not draft.can_proceed_to_step('2a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2b'))
        proceed_duration = time.time() - proceed_start
        print(f"⏱️  [PERF] Step proceed check took {proceed_duration:.3f}s")
    
    study_type_start = time.time()
    study_type = draft.get_step_data('1b').get('study_type', 'grid')
    study_type_duration = time.time() - study_type_start
    print(f"⏱️  [PERF] Study type retrieval took {study_type_duration:.3f}s")
    
    if request.method == 'POST':
        try:
            # Check request size before processing
            content_length = request.content_length
            if content_length and content_length > 200 * 1024 * 1024:  # 200MB limit
                flash('Request too large. Please reduce the number of elements or file sizes.', 'error')
                return render_template('study_creation/step2a.html', 
                                    study_type=study_type, num_elements=4, 
                                    elements_data=[], current_step='2a', draft=draft)
            
            # Handle dynamic form submission
            elements_data = []
            files_to_upload = []
            base64_conversions = []
            
            # Ultra-fast first pass: collect all elements and files simultaneously
            print(f"⚡ Starting ultra-fast form processing for {len(request.form)} form fields")
            form_start_time = time.time()
            
            i = 0
            while True:
                element_name = request.form.get(f'element_{i}_name')
                if not element_name:
                    break
                
                element_data = {
                    'element_id': f"E{i+1}",
                    'name': element_name,
                    'description': request.form.get(f'element_{i}_description', ''),
                    'alt_text': request.form.get(f'element_{i}_alt_text', ''),
                    'element_type': 'image'
                }
                
                # Check if this element has a new file to upload
                file = request.files.get(f'element_{i}_image_file')
                current_image = request.form.get(f'element_{i}_current_image', '')
                
                if file and file.filename:
                    # New file uploaded - add to batch upload list (no processing delay)
                    print(f"⚡ Queuing file {i+1}: {file.filename}")
                    files_to_upload.append((i, file, file.filename))
                    element_data['_needs_upload'] = True
                elif current_image:
                    # Check if current_image is base64 data and convert to Azure if needed
                    if current_image.startswith('data:image'):
                        print(f"⚡ Converting base64 for element {i+1}")
                        # Ultra-fast base64 conversion
                        import base64
                        import io
                        import mimetypes
                        
                        # Extract base64 data and determine file type
                        header, encoded = current_image.split(",", 1)
                        image_data = base64.b64decode(encoded)
                        
                        # Determine file extension from MIME type
                        mime_type = header.split(':')[1].split(';')[0]
                        extension = mimetypes.guess_extension(mime_type) or '.png'
                        
                        # Create a proper file-like object
                        image_file = io.BytesIO(image_data)
                        image_file.name = f"element_{i+1}_converted{extension}"
                        
                        # Ensure the file pointer is at the beginning
                        image_file.seek(0)
                        
                        files_to_upload.append((i, image_file, image_file.name))
                        element_data['_needs_upload'] = True
                    else:
                        # No new file, but existing Azure URL - keep the existing URL
                        element_data['content'] = current_image
                        print(f"⚡ Using existing URL for element {i+1}")
                        element_data['_needs_upload'] = False
                else:
                    # No image at all - this is required for all elements
                    flash(f'Image is required for element {i+1}. Please upload an image or ensure the element has an existing image.', 'error')
                    return render_template('study_creation/step2a.html', 
                                        study_type=study_type, num_elements=4, 
                                        elements_data=elements_data, current_step='2a', draft=draft)
                
                elements_data.append(element_data)
                i += 1
            
            form_duration = time.time() - form_start_time
            print(f"⚡ Form processing completed in {form_duration:.3f} seconds")
            
            # Ultra-fast batch upload all files in parallel
            if files_to_upload:
                print(f"🚀 Starting ULTRA-FAST batch upload of {len(files_to_upload)} files")
                upload_start_time = time.time()
                
                # Use optimized multiprocessing with more workers for speed
                max_workers = min(current_app.config.get('AZURE_UPLOAD_MAX_WORKERS', 8), len(files_to_upload))
                print(f"⚡ Using {max_workers} parallel workers for maximum speed")
                
                upload_results = upload_multiple_files_to_azure(files_to_upload, max_workers=max_workers)
                
                upload_duration = time.time() - upload_start_time
                print(f"⚡ ULTRA-FAST upload completed in {upload_duration:.2f} seconds")
                
                # Performance validation
                if upload_duration > 2.0:  # Should be under 2 seconds for 8 files
                    print(f"⚠️  Upload took {upload_duration:.2f}s - investigating performance...")
                else:
                    print(f"🎯 Excellent performance! {upload_duration:.2f}s for {len(files_to_upload)} files")
                
                # Process upload results
                for element_index, azure_url, error_msg in upload_results:
                    if error_msg:
                        flash(f'Upload failed for element {element_index + 1}: {error_msg}', 'error')
                        return render_template('study_creation/step2a.html', 
                                            study_type=study_type, num_elements=4, 
                                            elements_data=elements_data, current_step='2a', draft=draft)
                    
                    # Update element data with Azure URL
                    elements_data[element_index]['content'] = azure_url
                    elements_data[element_index]['_needs_upload'] = False
                    print(f"DEBUG: Successfully uploaded image for element {element_index + 1} to Azure: {azure_url}")
            else:
                print("DEBUG: No new files to upload")
            
            # Validate we have at least 4 elements
            if len(elements_data) < 4:
                flash('You need at least 4 elements for a grid study. Please upload more images.', 'error')
                return render_template('study_creation/step2a.html', 
                                    study_type=study_type, num_elements=4, 
                                    elements_data=elements_data, current_step='2a', draft=draft)
            
            # Validate that all elements have Azure URLs and clean up temporary fields
            for elem in elements_data:
                # Remove temporary upload tracking field
                elem.pop('_needs_upload', None)
                
                # Ensure content is a valid Azure URL
                if not elem.get('content', '').startswith('http'):
                    flash(f'Element {elem.get("element_id", "Unknown")} does not have a valid Azure URL. Please try again.', 'error')
                    return render_template('study_creation/step2a.html', 
                                        study_type=study_type, num_elements=4, 
                                        elements_data=elements_data, current_step='2a', draft=draft)
            
            # Ultra-fast database save
            print(f"⚡ Starting ultra-fast database save for {len(elements_data)} elements")
            db_start_time = time.time()
            
            if study_type == 'grid':
                # For grid studies, save as categories with a single default category
                categories_data = [{
                    'category_id': 'default_category',
                    'name': 'Default Category',
                    'description': 'Default category for grid elements',
                    'elements': elements_data,
                    'order': 0
                }]
                draft.update_step_data('2a', {
                    'categories': categories_data,
                    'elements': elements_data,  # Keep for backward compatibility
                    'study_type': study_type,
                    'num_elements': len(elements_data)
                })
            else:
                    # For layer studies, save as regular elements
                draft.update_step_data('2a', {
                    'elements': elements_data,
                    'study_type': study_type,
                            'num_elements': len(elements_data)
                })
            
            db_duration = time.time() - db_start_time
            print(f"⚡ Database save completed in {db_duration:.3f} seconds")
            
            # Redirect based on study type
            if study_type == 'grid':
                draft.current_step = 'grid_config'  # Go to grid category configuration for grid studies
                draft.save()
                flash(f'Study elements saved successfully! Created {len(elements_data)} elements.', 'success')
                return redirect(url_for('study_creation.grid_config'))
            else:  # layer study
                draft.current_step = 'layer_config'  # Go to layer configuration for layer studies
                draft.save()
                flash(f'Study elements saved successfully! Created {len(elements_data)} elements.', 'success')
                return redirect(url_for('study_creation.layer_config'))
            
        except Exception as e:
            print(f"ERROR in step2a: {str(e)}")
            flash(f'An error occurred while saving elements: {str(e)}', 'error')
            return render_template('study_creation/step2a.html', 
                                study_type=study_type, num_elements=4, 
                                elements_data=[], current_step='2a', draft=draft)
    
    # Get number of elements from form or previous data or default
    if request.args.get('num_elements'):
        num_elements = int(request.args.get('num_elements'))
    else:
        # Try to get from existing step2a data
        existing_start = time.time()
        existing_data = draft.get_step_data('2a')
        if existing_data and 'elements' in existing_data:
            # Use the stored elements count
            num_elements = existing_data.get('num_elements', len(existing_data['elements']))
        else:
            num_elements = 4
        existing_duration = time.time() - existing_start
        print(f"⏱️  [PERF] Existing data retrieval took {existing_duration:.3f}s")
    
    # Get existing elements data
    data_start = time.time()
    elements_data = draft.get_step_data('2a').get('elements', []) if draft.get_step_data('2a') else []
    data_duration = time.time() - data_start
    print(f"⏱️  [PERF] Elements data retrieval took {data_duration:.3f}s")
    
    # Debug logging
    print(f"DEBUG: num_elements = {num_elements}")
    print(f"DEBUG: elements_data length = {len(elements_data) if elements_data else 0}")
    print(f"DEBUG: existing_data = {draft.get_step_data('2a')}")
    
    render_start = time.time()
    result = render_template('study_creation/step2a.html', 
                         study_type=study_type, num_elements=num_elements, 
                         elements_data=elements_data, current_step='2a', draft=draft)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Step2a template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Step2a total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/step2b', methods=['GET', 'POST'])
@login_required
def step2b():
    """Step 2b: Classification Questions."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step2b started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    # Previous step is always step1c (rating scale) for both study types
    previous_step = 'step1c'
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        access_start = time.time()
        if not draft.can_access_step('2b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for(f'study_creation.{previous_step}'))
        access_duration = time.time() - access_start
        print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    else:
        # For POST requests (submitting), use can_proceed_to_step
        proceed_start = time.time()
        if not draft.can_proceed_to_step('2b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for(f'study_creation.{previous_step}'))
        proceed_duration = time.time() - proceed_start
        print(f"⏱️  [PERF] Step proceed check took {proceed_duration:.3f}s")
    
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
        
        # Redirect based on study type
        study_type = draft.get_step_data('1b').get('study_type', 'grid')
        if study_type == 'grid':
            draft.current_step = 'grid_config'
            draft.save()
            flash('Classification questions saved successfully!', 'success')
            return redirect(url_for('study_creation.grid_config'))
        elif study_type == 'layer':
            draft.current_step = 'layer_config'
            draft.save()
            flash('Classification questions saved successfully!', 'success')
            return redirect(url_for('study_creation.layer_config'))
        else:  # layer study
            draft.current_step = 'layer_config'
            draft.save()
            flash('Classification questions saved successfully!', 'success')
            return redirect(url_for('study_creation.layer_config'))
    
    # Pre-populate from stored data if available
    stored_step2b = draft.get_step_data('2b') or {}
    if stored_step2b and stored_step2b.get('questions'):
        num_questions = len(stored_step2b['questions'])
        questions_data = stored_step2b['questions']
    else:
        num_questions = 2
        questions_data = []
    
    render_start = time.time()
    result = render_template('study_creation/step2b.html', 
                         num_questions=num_questions, questions_data=questions_data, current_step='2b', draft=draft)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Step2b template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Step2b total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/step2c', methods=['GET', 'POST'])
@login_required
def step2c():
    """Step 2c: IPED Parameters Configuration."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step2c started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        access_start = time.time()
        if not draft.can_access_step('2c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2a'))
        access_duration = time.time() - access_start
        print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    else:
        # For POST requests (submitting), use can_proceed_to_step
        proceed_start = time.time()
        if not draft.can_proceed_to_step('2c'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step2a'))
        proceed_duration = time.time() - proceed_start
        print(f"⏱️  [PERF] Step proceed check took {proceed_duration:.3f}s")
    
    # Get study type to determine functionality
    study_type = draft.get_step_data('1b').get('study_type', 'grid')
    
    if study_type == 'layer':
        # For layer studies, redirect to the new unified layer_config page
        return redirect(url_for('study_creation.layer_config'))
    
    # Grid study logic
    form_start = time.time()
    form = Step2cIPEDParametersForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    template = 'study_creation/step2c.html'
    
    stored_step2c = draft.get_step_data('2c') or {}
    print(f"DEBUG: Step2c - stored_step2c: {stored_step2c}")
    print(f"DEBUG: Step2c - request method: {request.method}")
    
    if request.method == 'GET':
        print(f"DEBUG: Step2c - GET request, checking data")
        if stored_step2c:
            print(f"DEBUG: Step2c - Found stored data: {stored_step2c}")
            # Pre-populate with stored data
            form.number_of_respondents.data = stored_step2c.get('number_of_respondents')
            print(f"DEBUG: Step2c - Set form data to: {form.number_of_respondents.data}")
            
        else:
            print(f"DEBUG: Step2c - No stored data, checking step2a")
            # Set default values based on previous step elements count
            step2a_data = draft.get_step_data('2a')
            print(f"DEBUG: Step2c - step2a_data: {step2a_data}")
            if step2a_data:
                print(f"DEBUG: Step2c - Found step2a data, setting default")
                # Set a reasonable default for number of respondents
                form.number_of_respondents.data = 20  # Default to 20 respondents
                
                    
                # Also store this in the draft so it persists
                draft.update_step_data('2c', {
                            'number_of_respondents': 20,
                            'auto_populated': True
                        })
                draft.save()
                print(f"DEBUG: Step2c - Saved default data to draft")
            else:
                print(f"DEBUG: Step2c - No step2a data found")
    
    print(f"DEBUG: Step2c - Final form data: {form.number_of_respondents.data}")
    
    if form.validate_on_submit():
        # Get grid configuration data (new grid flow) or step2a data (legacy grid flow)
        grid_config_data = draft.get_step_data('grid_config')
        step2a_data = draft.get_step_data('2a')
        
        if grid_config_data and 'categories' in grid_config_data:
            # New grid flow: use categories from grid_config
            categories = grid_config_data['categories']
            category_info = {}
            total_elements = 0
            
            for category in categories:
                category_name = category.get('category_name', f"category_{len(category_info)+1}")
                elements = category.get('elements', [])
                category_info[category_name] = [f"element_{i+1}" for i in range(len(elements))]
                total_elements += len(elements)
            
            print(f"DEBUG: Using grid_config data - {len(category_info)} categories, {total_elements} total elements")
        elif step2a_data and 'elements' in step2a_data:
            # Legacy grid flow: use elements from step2a
            elements = step2a_data['elements']
            total_elements = len(elements)
            category_info = {"All": [f"element_{i+1}" for i in range(total_elements)]}
            print(f"DEBUG: Using step2a data - {total_elements} elements")
        else:
            # No data available
            total_elements = 0
            category_info = {}
            print(f"DEBUG: No grid data found - grid_config: {grid_config_data}, step2a: {step2a_data}")
        
        # Get calculated tasks per consumer from form (if available)
        calculated_tasks = request.form.get('calculated_tasks_per_consumer')
        if calculated_tasks and calculated_tasks.isdigit():
            tasks_per_consumer = int(calculated_tasks)
        else:
            # Use advanced algorithm from latest grid task generation
            if total_elements > 0 and category_info:
                from utils.task_generation import plan_T_E_auto
                
                # Plan using the same algorithm as actual task generation
                try:
                    T, E, A_map, avg_k, A_min_used = plan_T_E_auto(
                        category_info=category_info, 
                        study_mode="grid", 
                        max_active_per_row=min(4, len(category_info))  # GRID_MAX_ACTIVE = 4
                    )
                    tasks_per_consumer = T
                    print(f"DEBUG: Advanced algorithm calculated tasks_per_consumer: {tasks_per_consumer}")
                except Exception as e:
                    print(f"DEBUG: Advanced algorithm failed ({e}), falling back to simple calculation")
                    # Fallback to simple calculation
                    if total_elements <= 8:
                        K = 2
                    elif total_elements <= 16:
                        K = 3
                    else:
                        K = 4
                    max_tasks = math.comb(total_elements, K) if total_elements >= K else 0
                    tasks_per_consumer = min(24, max(1, math.floor(max_tasks / 2)))
            else:
                # No elements available, use default
                tasks_per_consumer = 8
                print(f"DEBUG: No elements available, using default tasks_per_consumer: {tasks_per_consumer}")
        
        # Grid study parameters
        step2c_data = {
            'num_elements': total_elements,
            'tasks_per_consumer': tasks_per_consumer,
            'number_of_respondents': form.number_of_respondents.data,
            'exposure_tolerance_cv': 1.0,  # Default from script
            'seed': None,  # Optional, will use None if not provided
            'total_tasks': tasks_per_consumer * form.number_of_respondents.data
        }
        
        draft.update_step_data('2c', step2c_data)
        draft.current_step = '3a'
        draft.save()
        flash('IPED parameters saved successfully!', 'success')
        return redirect(url_for('study_creation.step3a'))
    
    # Calculate tasks_per_consumer for template display
    calculated_tasks_per_consumer = None
    if request.method == 'GET':
        # Get grid configuration data (new grid flow) or step2a data (legacy grid flow)
        grid_config_data = draft.get_step_data('grid_config')
        step2a_data = draft.get_step_data('2a')
        
        if grid_config_data and 'categories' in grid_config_data:
            # New grid flow: use categories from grid_config
            categories = grid_config_data['categories']
            category_info = {}
            total_elements = 0
            
            for category in categories:
                category_name = category.get('category_name', f"category_{len(category_info)+1}")
                elements = category.get('elements', [])
                category_info[category_name] = [f"element_{i+1}" for i in range(len(elements))]
                total_elements += len(elements)
            
            print(f"DEBUG: Template - Using grid_config data - {len(category_info)} categories, {total_elements} total elements")
        elif step2a_data and 'elements' in step2a_data:
            # Legacy grid flow: use elements from step2a
            elements = step2a_data['elements']
            total_elements = len(elements)
            category_info = {"All": [f"element_{i+1}" for i in range(total_elements)]}
            print(f"DEBUG: Template - Using step2a data - {total_elements} elements")
        else:
            total_elements = 0
            category_info = {}
            print(f"DEBUG: Template - No grid data found")
        
        if total_elements > 0 and category_info:
            try:
                from utils.task_generation import plan_T_E_auto
                T, E, A_map, avg_k, A_min_used = plan_T_E_auto(
                    category_info=category_info, 
                    study_mode="grid", 
                    max_active_per_row=min(4, len(category_info))
                )
                calculated_tasks_per_consumer = T
                print(f"DEBUG: Template - Advanced algorithm calculated tasks_per_consumer: {calculated_tasks_per_consumer}")
            except Exception as e:
                print(f"DEBUG: Template - Advanced algorithm failed ({e}), using simple calculation")
                # Fallback to simple calculation
                if total_elements <= 8:
                    K = 2
                elif total_elements <= 16:
                    K = 3
                else:
                    K = 4
                max_tasks = math.comb(total_elements, K) if total_elements >= K else 0
                calculated_tasks_per_consumer = min(24, max(1, math.floor(max_tasks / 2)))
    
    render_start = time.time()
    result = render_template(template, form=form, current_step='2c', draft=draft, study_type=study_type, 
                           calculated_tasks_per_consumer=calculated_tasks_per_consumer)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Step2c template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Step2c total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/step3a', methods=['GET', 'POST'])
@login_required
def step3a():
    """Step 3a: Show appropriate task generation page based on study type."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step3a started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    # Get study type to determine which previous step to check
    study_type = draft.get_step_data('1b').get('study_type', 'grid')
    if study_type == 'layer':
        previous_step = 'layer_iped'
    elif study_type == 'grid':
        previous_step = 'grid_iped'  # Grid studies use grid_iped for IPED
    else:
        previous_step = 'step2c'
    
    if request.method == 'GET':
        print(f"DEBUG: Checking access to step3a for {study_type} study")
        print(f"DEBUG: Can access step3a: {draft.can_access_step('3a')}")
        if not draft.can_access_step('3a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for(f'study_creation.{previous_step}'))
    else:
        print(f"DEBUG: Checking if can proceed to step3a for {study_type} study")
        print(f"DEBUG: Can proceed to step3a: {draft.can_proceed_to_step('3a')}")
        if not draft.can_proceed_to_step('3a'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for(f'study_creation.{previous_step}'))
    
    # Get study type to determine which template to show
    study_type = draft.get_step_data('1b').get('study_type', 'grid')
    
    form_start = time.time()
    form = Step3aTaskGenerationForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    # Handle form submission for task generation
    if form.validate_on_submit():
        try:
            if study_type == 'grid':
                # Grid study task generation
                print(f"DEBUG: Starting task generation for grid study")
                
                # Get grid IPED data
                grid_iped_data = draft.get_step_data('grid_iped')
                print(f"DEBUG: Grid IPED data: {grid_iped_data}")
                
                if not grid_iped_data:
                    flash('IPED parameters not found. Please complete grid IPED step first.', 'error')
                    return render_template('study_creation/step3a_grid.html', 
                                        form=form, tasks_matrix={}, 
                                        grid_iped_data={},
                                        matrix_summary={},
                                        current_step='3a', draft=draft)
                
                # Get grid configuration data
                grid_config_data = draft.get_step_data('grid_config')
                print(f"DEBUG: Grid config data: {grid_config_data}")
                
                if not grid_config_data:
                    flash('Grid configuration not found. Please complete grid configuration step first.', 'error')
                    return render_template('study_creation/step3a_grid.html', 
                                        form=form, tasks_matrix={}, 
                                        grid_iped_data={},
                                        matrix_summary={},
                                        current_step='3a', draft=draft)
                
                # Generate task matrix using new category-based approach
                print(f"DEBUG: Calling generate_grid_tasks_v2 from utils")
                from utils.task_generation import generate_grid_tasks_v2
                
                task_generation_start = time.time()
                print(f"🔄 Starting task generation at {time.strftime('%H:%M:%S', time.localtime(task_generation_start))}")
                grid_result = generate_grid_tasks_v2(
                    categories_data=grid_config_data['categories'],
                    number_of_respondents=grid_iped_data['number_of_respondents'],
                    exposure_tolerance_cv=grid_iped_data.get('exposure_tolerance_cv', 1.0),
                    seed=grid_iped_data.get('seed')
                )
                tasks_matrix = grid_result['tasks']
                task_generation_duration = time.time() - task_generation_start
                print(f"⏱️ Task generation completed in {task_generation_duration:.2f} seconds")
                
                print(f"DEBUG: Task matrix generated successfully: {len(tasks_matrix)} respondents")
                
                # Save grid study task matrix WITH METADATA (like layer)
                draft.update_step_data('3a_grid', {
                    'tasks_matrix': {
                        'tasks': tasks_matrix,
                        'metadata': grid_result.get('metadata', {})
                    },
                    'generated_at': datetime.utcnow().isoformat(),
                    'regenerate_matrix': bool(getattr(form, 'regenerate_matrix', False) and form.regenerate_matrix.data),
                    'step_completed': True
                })
                
                draft.current_step = '3b'
                draft.save()
                
                print(f"DEBUG: Step 3a marked as complete for grid study")
                print(f"DEBUG: Draft saved with current_step: {draft.current_step}")
                
                flash('Task matrix generated successfully!', 'success')
                return redirect(url_for('study_creation.step3b'))
                
            else:
                # Layer study task generation
                print(f"DEBUG: Starting task generation for layer study")
                
                # Check for new layer structure
                layer_config_data = draft.get_step_data('layer_config')
                
                if not layer_config_data or 'layers' not in layer_config_data:
                    flash('Layer configuration not found. Please complete the layer configuration step first.', 'error')
                    return render_template('study_creation/step3a_layer.html', 
                                        form=form, tasks_matrix={}, 
                                        layer_config_data=layer_config_data or {},
                                        matrix_summary={},
                                        current_step='3a', draft=draft)
                
                print(f"DEBUG: Using new layer structure with {len(layer_config_data['layers'])} layers")
                
                # Get IPED parameters from layer_iped_data
                layer_iped_data = draft.get_step_data('layer_iped')
                if not layer_iped_data or 'number_of_respondents' not in layer_iped_data:
                    flash('IPED parameters not found. Please complete the IPED parameters step first.', 'error')
                    return render_template('study_creation/step3a_layer.html', 
                                        form=form, tasks_matrix={}, 
                                        layer_config_data=layer_config_data or {},
                                        matrix_summary={},
                                        current_step='3a', draft=draft)
                
                from utils.task_generation import generate_layer_tasks_v2
                
                task_generation_start = time.time()
                print(f"🔄 Starting layer task generation at {time.strftime('%H:%M:%S', time.localtime(task_generation_start))}")
                result = generate_layer_tasks_v2(
                    layers_data=layer_config_data['layers'],
                    number_of_respondents=layer_iped_data['number_of_respondents'],
                    exposure_tolerance_pct=2.0,  # Fixed as per original script
                    seed=None  # Not used in original logic
                )
                task_generation_duration = time.time() - task_generation_start
                print(f"⏱️ Layer task generation completed in {task_generation_duration:.2f} seconds")
                
                tasks_matrix = result['tasks']
                metadata = result['metadata']
                print(f"DEBUG: Layer task matrix generated successfully: {len(tasks_matrix)} respondents")
                print(f"DEBUG: Metadata: {metadata}")
                print(f"DEBUG: tasks_per_consumer from metadata: {metadata.get('tasks_per_consumer', 'NOT_FOUND')}")
                
                # Save layer study task matrix WITH METADATA
                draft.update_step_data('3a_layer', {
                    'tasks_matrix': {
                        'tasks': tasks_matrix,
                        'metadata': metadata
                    },
                    'generated_at': datetime.utcnow().isoformat(),
                    'regenerate_matrix': bool(getattr(form, 'regenerate_matrix', False) and form.regenerate_matrix.data),
                    'step_completed': True
                })
                
                draft.current_step = '3b'
                draft.save()
                
                print(f"DEBUG: Step 3a marked as complete for layer study")
                print(f"DEBUG: Draft saved with current_step: {draft.current_step}")
                
                flash('Task matrix generated successfully!', 'success')
                return redirect(url_for('study_creation.step3b'))
                
            # Mark step 3a as complete by ensuring data is properly saved
                # Layer study task matrix saving is handled above in the layer section
                
        except Exception as e:
                error_msg = f'Error generating task matrix: {str(e)}'
                print(f"DEBUG: Task generation error: {e}")
                print(f"DEBUG: Error type: {type(e)}")
                import traceback
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                flash(error_msg, 'error')
    
    # GET request - show appropriate template with existing data
    if study_type == 'grid':
        # Get grid study data
        stored_step3a = draft.get_step_data('3a_grid') or {}
        tasks_matrix_data = stored_step3a.get('tasks_matrix', {})
        
        # Handle new structure where tasks_matrix contains both 'tasks' and 'metadata'
        if isinstance(tasks_matrix_data, dict) and 'tasks' in tasks_matrix_data:
            tasks_matrix = tasks_matrix_data['tasks']
            metadata = tasks_matrix_data.get('metadata', {})
            print(f"DEBUG: Grid study - Using new structure with metadata: {metadata}")
        else:
            # Fallback for old structure
            tasks_matrix = tasks_matrix_data
            metadata = {}
            print(f"DEBUG: Grid study - Using old structure (no metadata)")
        
        # Get grid IPED data for display
        grid_iped_data = draft.get_step_data('grid_iped') or {}
        
        # Ensure grid_iped_data is properly structured
        if not isinstance(grid_iped_data, dict):
            print(f"WARNING: grid_iped_data is not a dict: {type(grid_iped_data)} = {grid_iped_data}")
            grid_iped_data = {}
        
        # Set default values for any missing keys and ensure all values are JSON serializable
        grid_iped_data.setdefault('number_of_respondents', 100)
        grid_iped_data.setdefault('tasks_per_consumer', 8)
        grid_iped_data.setdefault('exposure_tolerance_cv', 1.0)
        grid_iped_data.setdefault('seed', None)
        
        # Ensure all values are JSON serializable (replace Undefined with None)
        for key, value in grid_iped_data.items():
            if value is None or value == 'Undefined' or str(value) == 'Undefined':
                grid_iped_data[key] = None
                print(f"WARNING: Replaced undefined value for {key}: {value}")
        
        # Calculate matrix summary for display
        matrix_summary = {}
        if tasks_matrix and isinstance(tasks_matrix, (dict, list)):
            matrix_summary['total_respondents'] = len(tasks_matrix)
            try:
                matrix_summary['total_tasks'] = sum(len(respondent_tasks) for respondent_tasks in tasks_matrix.values() if isinstance(respondent_tasks, list))
                if matrix_summary['total_respondents'] > 0:
                    matrix_summary['tasks_per_respondent'] = matrix_summary['total_tasks'] // matrix_summary['total_respondents']
                    # Calculate elements per task for grid studies
                    if tasks_matrix and any(tasks_matrix.values()):
                        first_respondent_tasks = next(iter(tasks_matrix.values()))
                        if first_respondent_tasks:
                            first_task = first_respondent_tasks[0]
                            print(f"DEBUG: Grid study - First task structure: {type(first_task)}")
                            print(f"DEBUG: Grid study - First task data: {first_task}")
                            
                            # Count active elements (excluding _content entries)
                            if hasattr(first_task, 'elements_shown'):
                                print(f"DEBUG: Grid study - Using elements_shown attribute")
                                active_elements = sum(1 for element, is_active in first_task.elements_shown.items() 
                                                if is_active and not element.endswith('_content'))
                                matrix_summary['elements_per_task'] = active_elements
                                print(f"DEBUG: Grid study - Active elements counted: {active_elements}")
                            elif isinstance(first_task, dict) and 'elements_shown' in first_task:
                                print(f"DEBUG: Grid study - Using elements_shown dict key")
                                active_elements = sum(1 for element, is_active in first_task['elements_shown'].items() 
                                                if is_active and not element.endswith('_content'))
                                matrix_summary['elements_per_task'] = active_elements
                                print(f"DEBUG: Grid study - Active elements counted: {active_elements}")
                            else:
                                print(f"DEBUG: Grid study - No elements_shown found, available keys: {list(first_task.keys()) if isinstance(first_task, dict) else 'N/A'}")
                                matrix_summary['elements_per_task'] = 0
                        else:
                            matrix_summary['elements_per_task'] = 0
                    else:
                        matrix_summary['elements_per_task'] = 0
            except Exception as e:
                print(f"ERROR: Failed to calculate matrix summary: {e}")
                matrix_summary = {
                    'total_respondents': 0,
                    'total_tasks': 0,
                    'tasks_per_respondent': 0,
                    'elements_per_task': 0
                }
        else:
            # Set default values when no tasks matrix exists
            matrix_summary = {
                'total_respondents': 0,
                'total_tasks': 0,
                'tasks_per_respondent': 0,
                'elements_per_task': 0
            }
        
        render_start = time.time()
        result = render_template('study_creation/step3a_grid.html', 
                             form=form, tasks_matrix=tasks_matrix, 
                             grid_iped_data=grid_iped_data,
                             matrix_summary=matrix_summary,
                             current_step='3a', draft=draft)
        render_duration = time.time() - render_start
        print(f"⏱️  [PERF] Step3a_grid template rendering took {render_duration:.3f}s")
        
        total_duration = time.time() - start_time
        print(f"⏱️  [PERF] Step3a total: {total_duration:.3f}s")
        return result
    else:
        # Get layer study data
        stored_step3a = draft.get_step_data('3a_layer') or {}
        tasks_matrix_data = stored_step3a.get('tasks_matrix', {})
        
        # Handle new structure where tasks_matrix contains both 'tasks' and 'metadata'
        if isinstance(tasks_matrix_data, dict) and 'tasks' in tasks_matrix_data:
            tasks_matrix = tasks_matrix_data['tasks']
            metadata = tasks_matrix_data.get('metadata', {})
            print(f"DEBUG: Layer study - Using new structure with metadata: {metadata}")
        else:
            # Fallback for old structure
            tasks_matrix = tasks_matrix_data
            metadata = {}
            print(f"DEBUG: Layer study - Using old structure (no metadata)")
        
        # Calculate matrix summary for display
        matrix_summary = {}
        if tasks_matrix:
            matrix_summary['total_respondents'] = len(tasks_matrix)
            matrix_summary['total_tasks'] = sum(len(respondent_tasks) for respondent_tasks in tasks_matrix.values())
            if matrix_summary['total_respondents'] > 0:
                matrix_summary['tasks_per_respondent'] = matrix_summary['total_tasks'] // matrix_summary['total_respondents']
                # Calculate elements per task for layer studies
                if tasks_matrix and any(tasks_matrix.values()):
                    first_respondent_tasks = next(iter(tasks_matrix.values()))
                    if first_respondent_tasks:
                        first_task = first_respondent_tasks[0]
                        print(f"DEBUG: First task structure: {type(first_task)}")
                        print(f"DEBUG: First task attributes: {dir(first_task)}")
                        
                        # For layer studies, count active layers from elements_shown_content
                        print(f"DEBUG: First task data: {first_task}")
                        print(f"DEBUG: First task type: {type(first_task)}")
                        
                        # Check if it's a BaseDict and access data properly
                        if isinstance(first_task, dict) or hasattr(first_task, 'get'):
                            # Use dictionary access method
                            elements_shown_content = first_task.get('elements_shown_content', {})
                            print(f"DEBUG: Using dictionary access for layer study")
                            print(f"DEBUG: elements_shown_content: {elements_shown_content}")
                            
                            # Count layers that have content (active layers)
                            active_layers = 0
                            for element_name, content in elements_shown_content.items():
                                print(f"DEBUG: Processing element {element_name}: {content}")
                                if content and isinstance(content, dict) and content.get('url'):
                                    active_layers += 1
                                    print(f"DEBUG: Active layer found: {element_name} with URL: {content.get('url')}")
                                else:
                                    print(f"DEBUG: Inactive layer: {element_name} - content: {content}")
                            matrix_summary['elements_per_task'] = active_layers
                            print(f"DEBUG: Active layers counted: {active_layers}")
                        else:
                            print(f"DEBUG: No valid data structure found")
                            print(f"DEBUG: Available attributes: {dir(first_task)}")
                            matrix_summary['elements_per_task'] = 0
                    else:
                        matrix_summary['elements_per_task'] = 0
                else:
                    matrix_summary['elements_per_task'] = 0
        else:
            # Set default values when no tasks matrix exists
            matrix_summary = {
                'total_respondents': 0,
                'total_tasks': 0,
                'tasks_per_respondent': 0,
                'elements_per_task': 0
            }
        
        # Get layer IPED data with defensive checks
        layer_iped_data = draft.get_step_data('layer_iped') or {}
        
        # Ensure layer_iped_data is properly structured and JSON serializable
        if not isinstance(layer_iped_data, dict):
            print(f"WARNING: layer_iped_data is not a dict: {type(layer_iped_data)} = {layer_iped_data}")
            layer_iped_data = {}
        
        # Ensure all values are JSON serializable (replace Undefined with None)
        for key, value in layer_iped_data.items():
            if value is None or value == 'Undefined' or str(value) == 'Undefined':
                layer_iped_data[key] = None
                print(f"WARNING: Replaced undefined value for {key}: {value}")
        
        render_start = time.time()
        # Get layer config data for default background
        layer_config_data = draft.get_step_data('layer_config') or {}
        print(f"DEBUG: layer_config_data retrieved: {layer_config_data}")
        if layer_config_data:
            print(f"DEBUG: layer_config_data keys: {list(layer_config_data.keys())}")
            if 'default_background' in layer_config_data:
                print(f"DEBUG: default_background: {layer_config_data['default_background']}")
            else:
                print("DEBUG: No default_background key found in layer_config_data")
        
        result = render_template('study_creation/step3a_layer.html', 
                             form=form, tasks_matrix=tasks_matrix, 
                             layer_iped_data=layer_iped_data,
                             layer_config_data=layer_config_data,
                             matrix_summary=matrix_summary,
                             current_step='3a', draft=draft)
        render_duration = time.time() - render_start
        print(f"⏱️  [PERF] Step3a_layer template rendering took {render_duration:.3f}s")
        
        total_duration = time.time() - start_time
        print(f"⏱️  [PERF] Step3a total: {total_duration:.3f}s")
        return result





@study_creation_bp.route('/step3b', methods=['GET', 'POST'])
@login_required
def step3b():
    """Step 3b: Study Preview & Launch."""
    start_time = time.time()
    print(f"⏱️  [PERF] Step3b started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if request.method == 'GET':
        # For GET requests (viewing/navigating), use can_access_step
        access_start = time.time()
        if not draft.can_access_step('3b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step3a'))
        access_duration = time.time() - access_start
        print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    else:
        # For POST requests (submitting), use can_proceed_to_step
        proceed_start = time.time()
        if not draft.can_proceed_to_step('3b'):
            flash('Please complete previous steps first.', 'warning')
            return redirect(url_for('study_creation.step3a'))
        proceed_duration = time.time() - proceed_start
        print(f"⏱️  [PERF] Step proceed check took {proceed_duration:.3f}s")
    
    form_start = time.time()
    form = Step3bLaunchForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
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
                # Grid study - new category-based structure
                grid_categories = []
                grid_config_data = draft.get_step_data('grid_config')
                
                if grid_config_data and 'categories' in grid_config_data:
                    for i, category_data in enumerate(grid_config_data['categories']):
                        category = GridCategory(
                            category_id=category_data.get('category_id', str(uuid.uuid4())),
                            name=category_data.get('category_name', f'Category {i+1}'),
                            description=category_data.get('category_description', ''),
                            order=category_data.get('order', i)
                        )
                        
                        # Add elements to this category
                        category_elements = []
                        for j, element_data in enumerate(category_data['elements']):
                            element = StudyElement(
                                element_id=element_data.get('element_id', str(uuid.uuid4())),
                                name=element_data['name'],
                                description=element_data.get('description', ''),
                                element_type=element_data.get('element_type', 'image'),
                                content=element_data['content'],
                                alt_text=element_data.get('alt_text', '')
                            )
                            category_elements.append(element)
                        
                        category.elements = category_elements
                        grid_categories.append(category)
                
                study.grid_categories = grid_categories
                
                # Keep legacy elements for backward compatibility if they exist
                elements = []
                step2a_data = draft.get_step_data('2a')
                if step2a_data and 'elements' in step2a_data:
                    for i, element_data in enumerate(step2a_data['elements']):
                        element = StudyElement(
                            element_id=str(uuid.uuid4()),
                            name=element_data['name'],
                            description=element_data.get('description', ''),
                            element_type=element_data['element_type'],
                            content=element_data['content'],
                            alt_text=element_data.get('alt_text', '')
                        )
                        elements.append(element)
                study.elements = elements
                
                # Ensure study_layers is empty for grid studies
                study.study_layers = []
            else:
                # Layer study - new unified layer structure
                layer_config_data = draft.get_step_data('layer_config')
                print(f"DEBUG: Layer config data: {layer_config_data}")
                
                if layer_config_data and 'layers' in layer_config_data:
                    # Convert new layer structure to StudyLayer format
                    study_layers = []
                    for layer_idx, layer_data in enumerate(layer_config_data['layers']):
                        print(f"DEBUG: Processing layer {layer_idx}: {layer_data}")
                        
                        # Convert images to LayerImage format
                        layer_images = []
                        for i, image_data in enumerate(layer_data['images']):
                            print(f"DEBUG: Processing image {i}: {image_data}")
                            print(f"DEBUG: Image ID length: {len(str(image_data['id']))}")
                            print(f"DEBUG: Image ID: {image_data['id']}")
                            
                            # Ensure all required fields are present and properly formatted
                            if not image_data.get('id') or not image_data.get('name') or not image_data.get('url'):
                                print(f"DEBUG: Skipping invalid image data: {image_data}")
                                continue
                            
                            # Truncate fields if they're too long
                            image_id = str(image_data['id'])[:100]  # Limit to 100 chars
                            image_name = str(image_data['name'])[:100]  # Limit to 100 chars
                            image_url = str(image_data['url'])
                            image_alt = str(image_data.get('alt', ''))[:200]  # Limit to 200 chars
                            
                            print(f"DEBUG: Creating LayerImage with:")
                            print(f"  - image_id: {image_id} (length: {len(image_id)})")
                            print(f"  - name: {image_name} (length: {len(image_name)})")
                            print(f"  - url: {image_url[:50]}... (length: {len(image_url)})")
                            print(f"  - alt_text: {image_alt} (length: {len(image_alt)})")
                            
                            layer_image = LayerImage(
                                image_id=image_id,
                                name=image_name,
                                url=image_url,
                                alt_text=image_alt,
                                order=i
                            )
                            layer_images.append(layer_image)
                        
                        # Validate and format layer data
                        if not layer_data.get('layer_id') or not layer_data.get('name'):
                            print(f"DEBUG: Skipping invalid layer data: {layer_data}")
                            continue
                        
                        # Truncate fields if they're too long
                        layer_id = str(layer_data['layer_id'])[:100]  # Limit to 100 chars
                        layer_name = str(layer_data['name'])[:100]  # Limit to 100 chars
                        layer_description = str(layer_data.get('description', ''))[:500]  # Limit to 500 chars
                        
                        print(f"DEBUG: Creating StudyLayer with:")
                        print(f"  - layer_id: {layer_id} (length: {len(layer_id)})")
                        print(f"  - name: {layer_name} (length: {len(layer_name)})")
                        print(f"  - description: {layer_description[:50]}... (length: {len(layer_description)})")
                        print(f"  - z_index: {layer_data['z_index']}")
                        print(f"  - order: {layer_data['order']}")
                        print(f"  - images count: {len(layer_images)}")
                        
                        # Create StudyLayer
                        study_layer = StudyLayer(
                            layer_id=layer_id,
                            name=layer_name,
                            description=layer_description,
                            z_index=layer_data['z_index'],
                            images=layer_images,
                            order=layer_data['order']
                        )
                        study_layers.append(study_layer)
                    
                    # Store layers in the proper study_layers field
                    study.study_layers = study_layers
                    # Ensure elements is empty for layer studies
                    study.elements = []
                    
                    # Save default background if provided
                    if layer_config_data.get('default_background'):
                        study.default_background = layer_config_data['default_background']
                        print(f"✅ Default background saved to study: {layer_config_data['default_background']['name']}")
                    else:
                        print("📤 No default background provided for layer study")
            
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
            
            # Get step3a_data first to access task generation results
            if study_type == 'grid':
                step3a_data = draft.get_step_data('3a_grid')
            else:
                step3a_data = draft.get_step_data('3a_layer')
            
            print(f"DEBUG: Step3a data for {study_type} study: {step3a_data}")
            
            # Set IPED parameters based on study type
            if study_type == 'grid':
                # Grid study - use grid_iped data
                grid_iped_data = draft.get_step_data('grid_iped')
                
                # Calculate total elements from grid categories
                total_elements = 0
                if grid_config_data and 'categories' in grid_config_data:
                    total_elements = sum(len(category['elements']) for category in grid_config_data['categories'])
                
                # Use ACTUAL tasks_per_consumer from task generation result if available
                if step3a_data and 'tasks_matrix' in step3a_data and 'metadata' in step3a_data['tasks_matrix']:
                    actual_tasks_per_consumer = step3a_data['tasks_matrix']['metadata']['tasks_per_consumer']
                    print(f"DEBUG: Found metadata in step3a_data: {step3a_data['tasks_matrix']['metadata']}")
                    print(f"DEBUG: Using ACTUAL tasks_per_consumer from metadata: {actual_tasks_per_consumer}")
                    print(f"DEBUG: This replaces the configured value: {grid_iped_data.get('tasks_per_consumer', 8)}")
                else:
                    actual_tasks_per_consumer = grid_iped_data.get('tasks_per_consumer', 8)
                    print(f"DEBUG: WARNING - No metadata found, using fallback tasks_per_consumer: {actual_tasks_per_consumer}")
                    print(f"DEBUG: step3a_data keys: {list(step3a_data.keys()) if step3a_data else 'None'}")
                    if step3a_data and 'tasks_matrix' in step3a_data:
                        print(f"DEBUG: tasks_matrix keys: {list(step3a_data['tasks_matrix'].keys()) if isinstance(step3a_data['tasks_matrix'], dict) else 'Not a dict'}")
                
                total_tasks = actual_tasks_per_consumer * grid_iped_data['number_of_respondents']
                
                study.iped_parameters = IPEDParameters(
                    num_elements=total_elements,
                    tasks_per_consumer=actual_tasks_per_consumer,
                    number_of_respondents=grid_iped_data['number_of_respondents'],
                    exposure_tolerance_cv=grid_iped_data.get('exposure_tolerance_cv', 1.0),
                    total_tasks=total_tasks
                )
                
                print(f"✅ SAVED: IPED Parameters set with ACTUAL tasks_per_consumer: {actual_tasks_per_consumer}")
                print(f"✅ SAVED: Total tasks: {total_tasks} = {actual_tasks_per_consumer} × {grid_iped_data['number_of_respondents']}")
            else:
                # Layer study - use layer_iped data and calculate from layer_config
                layer_iped_data = draft.get_step_data('layer_iped')
                layer_config_data = draft.get_step_data('layer_config')
                
                # Use ACTUAL tasks_per_consumer from task generation result if available
                if step3a_data and 'tasks_matrix' in step3a_data and 'metadata' in step3a_data['tasks_matrix']:
                    actual_tasks_per_consumer = step3a_data['tasks_matrix']['metadata']['tasks_per_consumer']
                    print(f"DEBUG: Found metadata in step3a_data for layer study: {step3a_data['tasks_matrix']['metadata']}")
                    print(f"DEBUG: Using ACTUAL tasks_per_consumer from metadata: {actual_tasks_per_consumer}")
                    tasks_per_consumer = actual_tasks_per_consumer
                else:
                    # Fallback to original logic if no metadata available
                    if layer_config_data and 'layers' in layer_config_data:
                        uniqueness_capacity = 1
                        for layer in layer_config_data['layers']:
                            uniqueness_capacity *= len(layer['images'])
                        tasks_per_consumer = min(24, uniqueness_capacity)
                        print(f"DEBUG: WARNING - No metadata found for layer study, using fallback: {tasks_per_consumer}")
                    else:
                        tasks_per_consumer = 24  # Default fallback
                        print(f"DEBUG: WARNING - No layer config or metadata, using default: {tasks_per_consumer}")
                
                total_tasks = tasks_per_consumer * layer_iped_data['number_of_respondents']
                
                study.iped_parameters = IPEDParameters(
                    number_of_respondents=layer_iped_data['number_of_respondents'],
                    exposure_tolerance_pct=2.0,  # Fixed as per original script
                    total_tasks=total_tasks,
                    tasks_per_consumer=tasks_per_consumer  # Save tasks per consumer
                )
                
                print(f"✅ SAVED: Layer Study IPED Parameters set with ACTUAL tasks_per_consumer: {tasks_per_consumer}")
                print(f"✅ SAVED: Total tasks: {total_tasks} = {tasks_per_consumer} × {layer_iped_data['number_of_respondents']}")
            
            # Set generated tasks based on study type (step3a_data already retrieved above)
            
            if not step3a_data:
                flash('Step 3a data not found. Please go back to step 3a and generate the task matrix first.', 'error')
                return render_template('study_creation/step3b.html', 
                                     form=form, study_data=preview_data, current_step='3b', draft=draft)
            
            if 'tasks_matrix' not in step3a_data:
                flash('Task matrix not found in step 3a data. Please go back to step 3a and generate the task matrix first.', 'error')
                return render_template('study_creation/step3b.html', 
                                     form=form, study_data=preview_data, current_step='3b', draft=draft)
            
            # Extract the tasks from the tasks_matrix (which contains both 'tasks' and 'metadata')
            print(f"DEBUG: step3a_data['tasks_matrix'] type: {type(step3a_data['tasks_matrix'])}")
            print(f"DEBUG: step3a_data['tasks_matrix'] keys: {list(step3a_data['tasks_matrix'].keys()) if isinstance(step3a_data['tasks_matrix'], dict) else 'Not a dict'}")
            
            if isinstance(step3a_data['tasks_matrix'], dict) and 'tasks' in step3a_data['tasks_matrix']:
                study.tasks = step3a_data['tasks_matrix']['tasks']
                print(f"DEBUG: Tasks extracted from tasks_matrix and set successfully")
                print(f"DEBUG: study.tasks type: {type(study.tasks)}")
                print(f"DEBUG: study.tasks keys: {list(study.tasks.keys()) if isinstance(study.tasks, dict) else 'Not a dict'}")
                if isinstance(study.tasks, dict) and '0' in study.tasks:
                    print(f"DEBUG: Respondent 0 has {len(study.tasks['0'])} tasks")
            else:
                # Fallback for old format
                study.tasks = step3a_data['tasks_matrix']
                print(f"DEBUG: Tasks matrix set directly (legacy format)")
                
            # Generate share URL
            study.generate_share_url(request.host_url.rstrip('/'))
            
            # Save study
            study.save()
            print(f"DEBUG: Study saved with ID: {study._id}")
            
            # Verify the saved values
            print(f"🔍 VERIFICATION: Study IPED Parameters after save:")
            print(f"  - tasks_per_consumer: {study.iped_parameters.tasks_per_consumer}")
            print(f"  - number_of_respondents: {study.iped_parameters.number_of_respondents}")
            print(f"  - total_tasks: {study.iped_parameters.total_tasks}")
            print(f"  - num_elements: {study.iped_parameters.num_elements}")
            
            # Also verify tasks structure
            if hasattr(study, 'tasks') and study.tasks:
                first_respondent_tasks = study.tasks.get('0', [])
                actual_tasks_count = len(first_respondent_tasks) if first_respondent_tasks else 0
                print(f"🔍 VERIFICATION: Actual tasks per consumer in study.tasks: {actual_tasks_count}")
                if actual_tasks_count != study.iped_parameters.tasks_per_consumer:
                    print(f"⚠️  MISMATCH: IPED says {study.iped_parameters.tasks_per_consumer} but actual tasks show {actual_tasks_count}")
                else:
                    print(f"✅ MATCH: IPED and actual tasks both show {actual_tasks_count} tasks per consumer")
            
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
        'step2a': draft.get_step_data('2a'),
        'layer_config': draft.get_step_data('layer_config'),  # Layer configuration data
        'layer_iped': draft.get_step_data('layer_iped'),  # Layer IPED parameters
        'grid_config': draft.get_step_data('grid_config'),  # Grid configuration data
        'grid_iped': draft.get_step_data('grid_iped'),  # Grid IPED parameters
        'step2b': draft.get_step_data('2b'),
        'step2c': draft.get_step_data('2c'),
        'step3a': draft.get_step_data('3a')
    }
    
    # Get step3a_data for both layer and grid studies to access task generation metadata
    study_type = preview_data['step1b'].get('study_type', 'grid') if preview_data['step1b'] else 'grid'
    if study_type == 'grid':
        step3a_data = draft.get_step_data('3a_grid')
    else:
        step3a_data = draft.get_step_data('3a_layer')
    
    # Calculate IPED parameters for layer studies
    if preview_data['step1b'] and preview_data['step1b'].get('study_type') == 'layer':
        layer_config_data = preview_data['layer_config']
        layer_iped_data = preview_data['layer_iped']
        
        if layer_config_data and 'layers' in layer_config_data and layer_iped_data:
            # Calculate parameters from layer configuration
            total_layers = len(layer_config_data['layers'])
            total_images = sum(len(layer.get('images', [])) for layer in layer_config_data['layers'])
            
            # Calculate uniqueness capacity (product of images per layer)
            uniqueness_capacity = 1
            for layer in layer_config_data['layers']:
                layer_images = len(layer.get('images', []))
                if layer_images > 0:
                    uniqueness_capacity *= layer_images
            
            # Use ACTUAL tasks_per_consumer from task generation metadata if available
            if step3a_data and 'tasks_matrix' in step3a_data and 'metadata' in step3a_data['tasks_matrix']:
                tasks_per_consumer = step3a_data['tasks_matrix']['metadata']['tasks_per_consumer']
                print(f"DEBUG: Using ACTUAL tasks_per_consumer from layer task metadata: {tasks_per_consumer}")
            else:
                # Fallback to calculated value if metadata not available
                tasks_per_consumer = 24  # Default
                if uniqueness_capacity < 24:
                    tasks_per_consumer = uniqueness_capacity
                print(f"DEBUG: Using fallback tasks_per_consumer for layer: {tasks_per_consumer}")
            
            # Calculate total tasks using ACTUAL tasks_per_consumer
            total_tasks = tasks_per_consumer * layer_iped_data.get('number_of_respondents', 0)
            
            # Add calculated IPED parameters to preview data
            preview_data['layer_iped_calculated'] = {
                'total_layers': total_layers,
                'total_images': total_images,
                'tasks_per_consumer': tasks_per_consumer,
                'uniqueness_capacity': uniqueness_capacity,
                'number_of_respondents': layer_iped_data.get('number_of_respondents', 0),
                'total_tasks': total_tasks
            }
    
    # Calculate IPED parameters for grid studies
    if preview_data['step1b'] and preview_data['step1b'].get('study_type') == 'grid':
        grid_config_data = preview_data['grid_config']
        grid_iped_data = preview_data['grid_iped']
        
        if grid_config_data and 'categories' in grid_config_data and grid_iped_data:
            # Calculate parameters from grid configuration
            total_categories = len(grid_config_data['categories'])
            total_elements = sum(len(category.get('elements', [])) for category in grid_config_data['categories'])
            
            # Use ACTUAL tasks_per_consumer from task generation metadata if available
            if step3a_data and 'tasks_matrix' in step3a_data and 'metadata' in step3a_data['tasks_matrix']:
                tasks_per_consumer = step3a_data['tasks_matrix']['metadata']['tasks_per_consumer']
                print(f"DEBUG: Using ACTUAL tasks_per_consumer from grid task metadata: {tasks_per_consumer}")
            else:
                # Fallback to configured value if metadata not available
                tasks_per_consumer = grid_iped_data.get('tasks_per_consumer', 8)
                print(f"DEBUG: Using fallback tasks_per_consumer for grid: {tasks_per_consumer}")
            
            # Calculate total tasks using ACTUAL tasks_per_consumer
            total_tasks = tasks_per_consumer * grid_iped_data.get('number_of_respondents', 0)
            
            # Add calculated IPED parameters to preview data
            preview_data['grid_iped_calculated'] = {
                'total_categories': total_categories,
                'total_elements': total_elements,
                'tasks_per_consumer': tasks_per_consumer,
                'number_of_respondents': grid_iped_data.get('number_of_respondents', 0),
                'total_tasks': total_tasks
            }
    
    # Debug: Print the data structure
    print(f"DEBUG: Step3b preview data structure:")
    print(f"DEBUG: Step2a data: {preview_data['step2a']}")
    print(f"DEBUG: Grid config data: {preview_data['grid_config']}")
    print(f"DEBUG: Layer IPED calculated: {preview_data.get('layer_iped_calculated')}")
    print(f"DEBUG: Grid IPED calculated: {preview_data.get('grid_iped_calculated')}")
    print(f"DEBUG: Step3a data available: {step3a_data is not None}")
    if step3a_data:
        print(f"DEBUG: Step3a data keys: {list(step3a_data.keys())}")
        if 'tasks_matrix' in step3a_data and 'metadata' in step3a_data['tasks_matrix']:
            print(f"DEBUG: Task metadata: {step3a_data['tasks_matrix']['metadata']}")
    if preview_data['step2a']:
        print(f"DEBUG: Step2a elements: {preview_data['step2a'].get('elements', [])}")
        if 'elements' in preview_data['step2a']:
            for i, elem in enumerate(preview_data['step2a']['elements']):
                print(f"DEBUG: Element {i}: {elem}")
    if preview_data['grid_config']:
        print(f"DEBUG: Grid config categories: {preview_data['grid_config'].get('categories', [])}")
        if 'categories' in preview_data['grid_config']:
            for i, cat in enumerate(preview_data['grid_config']['categories']):
                print(f"DEBUG: Category {i}: {cat}")
    
    render_start = time.time()
    result = render_template('study_creation/step3b.html', 
                         form=form, study_data=preview_data, current_step='3b', draft=draft)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Step3b template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Step3b total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/layer-config', methods=['GET', 'POST'])
@login_required
def layer_config():
    """Layer configuration page for layer studies."""
    start_time = time.time()
    print(f"⏱️  [PERF] Layer config started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if not draft:
        flash('No active study draft found. Please start creating a study.', 'error')
        return redirect(url_for('study_creation.step1a'))
    
    # Check if user can access this step
    access_start = time.time()
    if not draft.can_access_step('layer_config'):
        flash('Please complete the previous steps first.', 'error')
        return redirect(url_for('study_creation.step2b'))
    access_duration = time.time() - access_start
    print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    
    form_start = time.time()
    form = LayerConfigForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    if request.method == 'POST':
        try:
            # Process layer data from the form
            layers_data = []
            layer_index = 0
            
            # Parse the form data to extract layer information
            while True:
                layer_id = request.form.get(f'layer_{layer_index}_id')
                if not layer_id:
                    break
                
                layer_name = request.form.get(f'layer_{layer_index}_name', f'Layer_{layer_index + 1}')
                layer_description = request.form.get(f'layer_{layer_index}_description', '')
                layer_order = int(request.form.get(f'layer_{layer_index}_order', layer_index))
                layer_z_index = int(request.form.get(f'layer_{layer_index}_z_index', layer_index))
                
                # Get images data for this layer
                layer_images_data = request.form.get(f'layer_{layer_index}_images_data', '[]')
                try:
                    layer_images = json.loads(layer_images_data)
                except json.JSONDecodeError:
                    layer_images = []
                
                # Only add layer if it has images
                if layer_images:
                    print(f"✅ Adding layer '{layer_name}' with {len(layer_images)} images")
                    layers_data.append({
                        'layer_id': layer_id,
                        'name': layer_name,
                        'description': layer_description,
                        'order': layer_order,
                        'z_index': layer_z_index,
                        'images': layer_images
                    })
                else:
                    print(f"⚠️ Skipping layer '{layer_name}' - no images found")
                
                layer_index += 1
            
            # Validate we have at least one layer with images
            if not layers_data:
                flash('Please add at least one layer with images.', 'error')
                return render_template('study_creation/layer_config.html', form=form, draft=draft)
            
            # Extract all images that need to be uploaded to Azure
            images_to_upload = []
            processed_layers = []
            
            # Check if all images already have Azure URLs (from frontend batch upload)
            all_images_have_azure_urls = True
            for layer in layers_data:
                for image in layer.get('images', []):
                    if image.get('url', '').startswith('data:image'):
                        all_images_have_azure_urls = False
                        break
                if not all_images_have_azure_urls:
                    break
            
            print(f"🔍 All images have Azure URLs: {all_images_have_azure_urls}")
            
            print(f"🚀 Starting ULTRA-FAST layer image processing for {len(layers_data)} layers")
            image_processing_start = time.time()
            
            for layer in layers_data:
                # Validate layer data has required fields
                if not layer.get('layer_id') or not layer.get('name'):
                    print(f"⚠️ Skipping invalid layer data: {layer}")
                    continue
                
                processed_layer = layer.copy()
                processed_images = []
                print(f"🔍 Processing layer '{layer['name']}' with {len(layer['images'])} original images")
                
                for image in layer['images']:
                    # Validate image data has required fields
                    if not image.get('id') or not image.get('name') or not image.get('url'):
                        print(f"⚠️ Skipping invalid image data: {image}")
                        continue
                    
                    # Check if this image needs to be uploaded to Azure
                    print(f"🔍 Checking image URL: {image['url'][:50]}...")
                    if not all_images_have_azure_urls and image['url'].startswith('data:image'):
                        # This is a base64 image that needs Azure upload
                        print(f"⚡ Queuing base64 image for Azure upload: {image['name']}")
                        
                        # Extract base64 data and determine file type
                        header, encoded = image['url'].split(",", 1)
                        image_data = base64.b64decode(encoded)
                        
                        # Determine file extension from MIME type
                        mime_type = header.split(':')[1].split(';')[0]
                        extension = mimetypes.guess_extension(mime_type) or '.png'
                        
                        # Create a proper file-like object
                        image_file = io.BytesIO(image_data)
                        image_file.name = f"{image['id']}{extension}"
                        image_file.seek(0)
                        
                        # Add to upload queue with metadata
                        images_to_upload.append({
                            'image_id': image['id'],
                            'file': image_file,
                            'filename': image_file.name,
                            'layer_id': layer['layer_id'],
                            'image_index': len(processed_images)
                        })
                        
                        # Mark this image as needing upload
                        image['_needs_upload'] = True
                    else:
                        # This is already an Azure URL (from batch upload), keep it
                        print(f"⚡ Using existing Azure URL for image: {image['name']}")
                        image['_needs_upload'] = False
                    
                    processed_images.append(image)
                
                processed_layer['images'] = processed_images
                processed_layers.append(processed_layer)
                print(f"✅ Layer '{layer['name']}' processed with {len(processed_images)} final images")
            
            image_processing_duration = time.time() - image_processing_start
            print(f"⚡ Image processing completed in {image_processing_duration:.3f}s")
            
            # Upload images to Azure if needed
            print(f"🔍 Total images queued for Azure upload: {len(images_to_upload)}")
            if images_to_upload and not all_images_have_azure_urls:
                print(f"🚀 Starting ULTRA-FAST Azure upload for {len(images_to_upload)} layer images")
                upload_start_time = time.time()
                
                # Use optimized multiprocessing with more workers for speed
                max_workers = min(current_app.config.get('AZURE_UPLOAD_MAX_WORKERS', 8), len(images_to_upload))
                print(f"⚡ Using {max_workers} parallel workers for maximum speed")
                
                # Prepare files for multiprocessing upload
                files_to_upload = [(item['image_id'], item['file'], item['filename']) for item in images_to_upload]
                
                # Upload to Azure using multiprocessing
                upload_results = upload_multiple_files_to_azure(files_to_upload, max_workers=max_workers)
                
                upload_duration = time.time() - upload_start_time
                print(f"⚡ ULTRA-FAST Azure upload completed in {upload_duration:.2f} seconds")
                
                # Performance validation
                if upload_duration > 2.0:  # Should be under 2 seconds for 8 images
                    print(f"⚠️  Upload took {upload_duration:.2f}s - investigating performance...")
                else:
                    print(f"🎯 Excellent performance! {upload_duration:.2f}s for {len(images_to_upload)} images")
                
                # Update processed layers with Azure URLs
                for item in images_to_upload:
                    # Find the corresponding upload result
                    azure_url = None
                    error_msg = None
                    for result_image_id, result_azure_url, result_error_msg in upload_results:
                        if result_image_id == item['image_id']:
                            azure_url = result_azure_url
                            error_msg = result_error_msg
                            break
                    
                    if error_msg:
                        flash(f'Upload failed for image {item["image_id"]}: {error_msg}', 'error')
                        return render_template('study_creation/layer_config.html', form=form, draft=draft)
                    
                    # Update the image URL in the processed layer
                    # Find the correct layer by ID
                    target_layer = None
                    for layer in processed_layers:
                        if layer['layer_id'] == item['layer_id']:
                            target_layer = layer
                            break
                    
                    if target_layer and item['image_index'] < len(target_layer['images']):
                        image = target_layer['images'][item['image_index']]
                        image['url'] = azure_url
                        image.pop('_needs_upload', None)  # Clean up temporary field
                        print(f"✅ Successfully uploaded image {item['image_id']} to Azure: {azure_url[:50]}...")
                    else:
                        print(f"⚠️  Warning: Could not find layer {item['layer_id']} or image index {item['image_index']}")
            elif all_images_have_azure_urls:
                print("✅ All images already have Azure URLs from frontend batch upload - skipping upload")
            else:
                print("✅ No new images to upload - all images already have Azure URLs")
            
            # Validate that all images now have Azure URLs
            invalid_images = validate_image_urls(processed_layers)
            if invalid_images:
                error_msg = f"Found {len(invalid_images)} images with invalid URLs. Please ensure all images are uploaded to Azure."
                current_app.logger.error(error_msg)
                for img in invalid_images:
                    current_app.logger.error(f"  - {img['layer']}: {img['image']} ({img['url_type']})")
                flash(error_msg, 'error')
                return render_template('study_creation/layer_config.html', form=form, draft=draft)
            
            print(f"✅ All {sum(len(layer['images']) for layer in processed_layers)} images validated - all have Azure URLs")
            
            # Handle default background upload if provided
            default_background_data = None
            if 'default_background' in request.files:
                background_file = request.files['default_background']
                if background_file and background_file.filename != '':
                    print(f"📤 Processing default background: {background_file.filename}")
                    
                    # Upload background to Azure
                    from utils.azure_storage import upload_to_azure
                    background_url = upload_to_azure(background_file)
                    
                    # Get file size without consuming the file content
                    current_pos = background_file.tell()
                    background_file.seek(0, 2)  # Seek to end
                    file_size = background_file.tell()
                    background_file.seek(current_pos)  # Reset to original position
                    
                    # Create background data structure
                    default_background_data = {
                        'url': background_url,
                        'name': background_file.filename,
                        'size': file_size,
                        'content_type': background_file.content_type
                    }
                    
                    print(f"✅ Default background uploaded successfully: {background_url}")
                else:
                    print("📤 No default background file provided")
            else:
                print("📤 No default_background field in request")
            
            # Save layer configuration with Azure URLs and default background
            layer_config_data = {
                'layers': processed_layers,
                'default_background': default_background_data
            }
            
            # Log the data being saved
            current_app.logger.info("=" * 80)
            current_app.logger.info("SAVING LAYER CONFIGURATION TO DRAFT")
            current_app.logger.info("=" * 80)
            current_app.logger.info(f"Total layers: {len(processed_layers)}")
            
            for i, layer in enumerate(processed_layers):
                current_app.logger.info(f"Layer {i+1}: {layer['name']}")
                current_app.logger.info(f"  - ID: {layer['layer_id']}")
                current_app.logger.info(f"  - Description: {layer['description']}")
                current_app.logger.info(f"  - Order: {layer['order']}")
                current_app.logger.info(f"  - Z-Index: {layer['z_index']}")
                current_app.logger.info(f"  - Images: {len(layer['images'])}")
                
                for j, image in enumerate(layer['images']):
                    current_app.logger.info(f"    Image {j+1}: {image['name']}")
                    current_app.logger.info(f"      - URL: {image['url'][:50]}..." if len(image['url']) > 50 else f"      - URL: {image['url']}")
                    current_app.logger.info(f"      - Alt: {image['alt']}")
            
            current_app.logger.info("=" * 80)
            
            # Save to draft
            print(f"⚡ Starting ultra-fast database save for {len(processed_layers)} layers")
            db_start_time = time.time()
            
            draft.update_step_data('layer_config', layer_config_data)
            draft.current_step = 'layer_iped'
            draft.save()
            
            db_duration = time.time() - db_start_time
            print(f"⚡ Database save completed in {db_duration:.3f} seconds")
            
            current_app.logger.info("Layer configuration saved to draft successfully!")
            current_app.logger.info(f"Current step updated to: {draft.current_step}")
            current_app.logger.info("=" * 80)
            
            flash('Layer configuration saved successfully!', 'success')
            return redirect(url_for('study_creation.layer_iped'))
            
        except Exception as e:
            import traceback
            print(f"❌ Error saving layer configuration: {str(e)}")
            print(f"❌ Full traceback:")
            traceback.print_exc()
            flash(f'Error saving layer configuration: {str(e)}', 'error')
            return render_template('study_creation/layer_config.html', form=form, draft=draft)
    
    # GET request - show form with existing data
    layer_config_data = draft.get_step_data('layer_config')
    
    render_start = time.time()
    result = render_template('study_creation/layer_config.html', form=form, draft=draft, layer_config_data=layer_config_data)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Layer config template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Layer config total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    """Upload image to Azure Blob Storage."""
    start_time = time.time()
    print(f"⏱️  [PERF] Upload image started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    try:
        current_app.logger.info(f'Upload request received: {request.files}')
        current_app.logger.info(f'Request content type: {request.content_type}')
        current_app.logger.info(f'Request headers: {dict(request.headers)}')
        
        if 'image' not in request.files:
            current_app.logger.error('No image file in request.files')
            return jsonify({'success': False, 'error': 'No image file provided'})
        
        file = request.files['image']
        current_app.logger.info(f'File received: {file.filename}, size: {file.content_length if hasattr(file, "content_length") else "unknown"}')
        
        if file.filename == '':
            current_app.logger.error('Empty filename')
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Validate file type
        if not file or not allowed_file(file.filename):
            current_app.logger.error(f'Invalid file type: {file.filename}')
            return jsonify({'success': False, 'error': 'Invalid file type'})
        
        current_app.logger.info('File validation passed, uploading to Azure...')
        
        # Upload to Azure
        from utils.azure_storage import upload_to_azure
        azure_url = upload_to_azure(file)
        
        if azure_url:
            current_app.logger.info(f'Upload successful: {azure_url}')
            return jsonify({'success': True, 'url': azure_url})
        else:
            current_app.logger.error('Azure upload returned None')
            return jsonify({'success': False, 'error': 'Failed to upload to Azure'})
            
    except Exception as e:
        current_app.logger.error(f'Image upload error: {str(e)}')
        current_app.logger.error(f'Error type: {type(e)}')
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return jsonify({'success': False, 'error': str(e)})

def allowed_file(filename):
    """Check if file extension is allowed."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_azure_url(url):
    """Check if a URL is a valid Azure Blob Storage URL."""
    if not url:
        return False
    return url.startswith('http') and ('blob.core.windows.net' in url or 'azure' in url)

def validate_image_urls(layers_data):
    """Validate that all images in layers have Azure URLs, not base64 data."""
    invalid_images = []
    
    for layer in layers_data:
        for image in layer.get('images', []):
            if not is_azure_url(image.get('url')):
                invalid_images.append({
                    'layer': layer.get('name', 'Unknown'),
                    'image': image.get('name', 'Unknown'),
                    'url_type': 'base64' if image.get('url', '').startswith('data:') else 'invalid'
                })
    
    return invalid_images

@study_creation_bp.route('/upload-layer-images', methods=['POST'])
@login_required
def upload_layer_images():
    """Batch upload layer images to Azure Blob Storage using multiprocessing."""
    start_time = time.time()
    print(f"⏱️  [PERF] Layer image batch upload started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    try:
        current_app.logger.info(f'Layer image batch upload request received')
        
        # Get the JSON data containing image information
        data = request.get_json()
        if not data or 'images' not in data:
            return jsonify({'success': False, 'error': 'No image data provided'}), 400
        
        images_data = data['images']
        if not images_data:
            return jsonify({'success': False, 'error': 'Empty images array'}), 400
        
        current_app.logger.info(f'Processing {len(images_data)} layer images for batch upload')
        
        # Prepare data for multiprocessing upload
        files_to_upload = []
        for img_data in images_data:
            image_id = img_data.get('id')
            file_data = img_data.get('file_data')  # Base64 encoded file data
            
            if not image_id or not file_data:
                continue
            
            try:
                # Convert base64 to file object
                import base64
                import io
                import mimetypes
                
                # Extract base64 data and determine file type
                if file_data.startswith('data:'):
                    header, encoded = file_data.split(",", 1)
                    image_data = base64.b64decode(encoded)
                    
                    # Determine file extension from MIME type
                    mime_type = header.split(':')[1].split(';')[0]
                    extension = mimetypes.guess_extension(mime_type) or '.png'
                else:
                    # Assume it's already base64 encoded
                    image_data = base64.b64decode(file_data)
                    extension = '.png'
                
                # Create a proper file-like object
                image_file = io.BytesIO(image_data)
                image_file.name = f"{image_id}{extension}"
                
                # Ensure the file pointer is at the beginning
                image_file.seek(0)
                
                files_to_upload.append((image_id, image_file, image_file.name))
                
            except Exception as e:
                current_app.logger.error(f'Error processing image {image_id}: {str(e)}')
                continue
        
        if not files_to_upload:
            return jsonify({'success': False, 'error': 'No valid images to upload'}), 400
        
        current_app.logger.info(f'Starting multiprocessing upload for {len(files_to_upload)} layer images')
        
        # Use the new multiprocessing upload function
        upload_results = upload_layer_images_to_azure(files_to_upload)
        
        # Process results
        results = {}
        for image_id, azure_url, error_msg in upload_results:
            if error_msg:
                results[image_id] = {'success': False, 'error': error_msg}
            else:
                results[image_id] = {'success': True, 'url': azure_url}
        
        # Count successes and failures
        success_count = sum(1 for r in results.values() if r['success'])
        total_count = len(results)
        
        current_app.logger.info(f'Layer image batch upload completed: {success_count}/{total_count} successful')
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total': total_count,
                'successful': success_count,
                'failed': total_count - success_count
            }
        })
        
    except Exception as e:
        current_app.logger.error(f'Layer image batch upload error: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@study_creation_bp.route('/layer-iped', methods=['GET', 'POST'])
@login_required
def layer_iped():
    """IPED parameters configuration for layer studies after layers are configured."""
    start_time = time.time()
    print(f"⏱️  [PERF] Layer IPED started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if not draft:
        flash('No active study draft found. Please start creating a study.', 'error')
        return redirect(url_for('study_creation.step1a'))
    
    # Check if user can access this step
    access_start = time.time()
    if not draft.can_access_step('layer_iped'):
        flash('Please complete the previous steps first.', 'error')
        return redirect(url_for('study_creation.step2b'))
    access_duration = time.time() - access_start
    print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    
    form_start = time.time()
    form = LayerIPEDForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                # Save IPED parameters to layer_iped_data field
                # Only save number_of_respondents since other parameters are fixed
                layer_iped_data = {
                    'number_of_respondents': form.number_of_respondents.data,
                    'exposure_tolerance_pct': 2.0,  # Fixed as per original script
                    'seed': None  # Not used in original logic
                }
                draft.update_step_data('layer_iped', layer_iped_data)
                draft.current_step = '3a'
                draft.save()
                
                flash('IPED parameters saved successfully!', 'success')
                return redirect(url_for('study_creation.step3a'))
                
            except Exception as e:
                flash(f'Error saving IPED parameters: {str(e)}', 'error')
                return render_template('study_creation/layer_iped.html', form=form, draft=draft)
    
    # GET request - show form with existing data
    layer_config_data = draft.get_step_data('layer_config') or {}
    
    # Log the data being loaded
    current_app.logger.info("=" * 80)
    current_app.logger.info("LOADING LAYER CONFIGURATION FROM DRAFT")
    current_app.logger.info("=" * 80)
    current_app.logger.info(f"Layer config data: {layer_config_data}")
    
    if layer_config_data and 'layers' in layer_config_data:
        current_app.logger.info(f"Total layers found: {len(layer_config_data['layers'])}")
        for i, layer in enumerate(layer_config_data['layers']):
            current_app.logger.info(f"Layer {i+1}: {layer.get('name', 'Unknown')}")
            current_app.logger.info(f"  - Images: {len(layer.get('images', []))}")
    else:
        current_app.logger.warning("No layer configuration data found!")
    
    current_app.logger.info("=" * 80)
    
    render_start = time.time()
    result = render_template('study_creation/layer_iped.html', form=form, draft=draft, layer_config_data=layer_config_data)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Layer IPED template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Layer IPED total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/calculate-layer-parameters')
@login_required
def calculate_layer_parameters():
    """Calculate layer study parameters based on current layer configuration."""
    try:
        draft = get_study_draft()
        if not draft:
            return jsonify({'error': 'No active study draft found'}), 404
        
        layer_config_data = draft.get_step_data('layer_config') or {}
        
        if not layer_config_data or 'layers' not in layer_config_data:
            return jsonify({
                'total_layers': 0,
                'total_images': 0,
                'tasks_per_consumer': 0,
                'uniqueness_capacity': 0,
                'message': 'No layers configured yet'
            })
        
        layers = layer_config_data['layers']
        total_layers = len(layers)
        total_images = sum(len(layer.get('images', [])) for layer in layers)
        
        # Calculate uniqueness capacity (product of images per layer)
        uniqueness_capacity = 1
        for layer in layers:
            layer_images = len(layer.get('images', []))
            if layer_images > 0:
                uniqueness_capacity *= layer_images
        
        # Calculate tasks per consumer based on original algorithm
        tasks_per_consumer = 24  # Default
        if uniqueness_capacity < 24:
            tasks_per_consumer = uniqueness_capacity
        
        return jsonify({
            'total_layers': total_layers,
            'total_images': total_images,
            'tasks_per_consumer': tasks_per_consumer,
            'uniqueness_capacity': uniqueness_capacity,
            'message': 'Parameters calculated successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f'Error calculating layer parameters: {str(e)}')
        return jsonify({'error': str(e)}), 500

@study_creation_bp.route('/reset')
@login_required
def reset():
    """Reset study creation draft."""
    start_time = time.time()
    print(f"⏱️  [PERF] Reset started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = StudyDraft.objects(user=current_user, is_complete=False).order_by('-created_at').first()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if draft:
        delete_start = time.time()
        draft.delete()
        delete_duration = time.time() - delete_start
        print(f"⏱️  [PERF] Draft deletion took {delete_duration:.3f}s")
    
    flash('Study creation draft reset. You can start over.', 'info')
    return redirect(url_for('study_creation.step1a'))

@study_creation_bp.route('/update-study-counters')
@login_required
def update_study_counters():
    """Update response counters for all studies based on actual StudyResponse objects."""
    start_time = time.time()
    print(f"⏱️  [PERF] Study counters update started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    try:
        from models.study import Study
        
        studies = Study.objects.all()
        updated_count = 0
        
        for study in studies:
            try:
                counters = study.update_response_counters()
                if counters:
                    updated_count += 1
                    print(f"✅ Updated study '{study.title}' counters: {counters}")
            except Exception as e:
                print(f"⚠️  Error updating study '{study.title}': {str(e)}")
                continue
        
        total_duration = time.time() - start_time
        print(f"⏱️  [PERF] Study counters update total: {total_duration:.3f}s")
        
        return f"Updated response counters for {updated_count}/{len(studies)} studies in {total_duration:.2f}s"
        
    except Exception as e:
        print(f"Error during counters update: {str(e)}")
        return f"Error: {str(e)}"

@study_creation_bp.route('/cleanup-base64-images')
@login_required
def cleanup_base64_images():
    """Clean up any existing base64 images in the database and convert them to Azure URLs."""
    start_time = time.time()
    print(f"⏱️  [PERF] Base64 cleanup started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    try:
        draft = get_study_draft()
        if not draft:
            return "No draft found"
        
        layer_config_data = draft.get_step_data('layer_config')
        if not layer_config_data or 'layers' not in layer_config_data:
            return "No layer configuration found"
        
        layers = layer_config_data['layers']
        base64_images = []
        
        # Find all base64 images
        for layer in layers:
            for image in layer.get('images', []):
                if image.get('url', '').startswith('data:image'):
                    base64_images.append({
                        'layer_id': layer['layer_id'],
                        'layer_name': layer['name'],
                        'image_id': image['id'],
                        'image_name': image['name'],
                        'base64_data': image['url']
                    })
        
        if not base64_images:
            return f"No base64 images found. All {sum(len(layer.get('images', [])) for layer in layers)} images are already Azure URLs."
        
        print(f"Found {len(base64_images)} base64 images to convert")
        
        # Convert base64 images to Azure URLs
        files_to_upload = []
        for img in base64_images:
            try:
                # Extract base64 data
                header, encoded = img['base64_data'].split(",", 1)
                image_data = base64.b64decode(encoded)
                
                # Determine file extension
                mime_type = header.split(':')[1].split(';')[0]
                extension = mimetypes.guess_extension(mime_type) or '.png'
                
                # Create file object
                image_file = io.BytesIO(image_data)
                image_file.name = f"{img['image_id']}{extension}"
                image_file.seek(0)
                
                files_to_upload.append((img['image_id'], image_file, image_file.name))
                
            except Exception as e:
                print(f"Error processing image {img['image_id']}: {str(e)}")
                continue
        
        if files_to_upload:
            print(f"Uploading {len(files_to_upload)} images to Azure...")
            
            # Upload to Azure using multiprocessing
            max_workers = min(current_app.config.get('AZURE_UPLOAD_MAX_WORKERS', 8), len(files_to_upload))
            upload_results = upload_multiple_files_to_azure(files_to_upload, max_workers=max_workers)
            
            # Update database with Azure URLs
            for img in base64_images:
                # Find corresponding upload result
                azure_url = None
                for result_id, result_url, result_error in upload_results:
                    if result_id == img['image_id']:
                        azure_url = result_url
                        break
                
                if azure_url:
                    # Update the image URL in the database
                    for layer in layers:
                        if layer['layer_id'] == img['layer_id']:
                            for image in layer['images']:
                                if image['id'] == img['image_id']:
                                    image['url'] = azure_url
                                    print(f"✅ Updated {img['image_name']} with Azure URL: {azure_url[:50]}...")
                                    break
                            break
            
            # Save updated data
            draft.update_step_data('layer_config', {'layers': layers})
            draft.save()
            
            print(f"✅ Successfully converted {len(base64_images)} base64 images to Azure URLs")
        
        total_duration = time.time() - start_time
        print(f"⏱️  [PERF] Base64 cleanup total: {total_duration:.3f}s")
        
        return f"Cleanup completed! Converted {len(base64_images)} base64 images to Azure URLs in {total_duration:.2f}s"
        
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
        return f"Error: {str(e)}"

@study_creation_bp.route('/grid-config', methods=['GET', 'POST'])
@login_required
def grid_config():
    """Grid configuration page for grid studies."""
    start_time = time.time()
    print(f"⏱️  [PERF] Grid config started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if not draft:
        flash('No active study draft found. Please start creating a study.', 'error')
        return redirect(url_for('study_creation.step1a'))
    
    # Check if user can access this step
    access_start = time.time()
    if not draft.can_access_step('grid_config'):
        flash('Please complete the previous steps first.', 'error')
        return redirect(url_for('study_creation.step2b'))
    access_duration = time.time() - access_start
    print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    
    form_start = time.time()
    form = GridConfigForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    if request.method == 'POST':
        try:
            # Get categories data from JSON
            categories_data_json = request.form.get('categories_data')
            if not categories_data_json:
                flash('No categories data received.', 'error')
                return render_template('study_creation/grid_config.html', 
                                    form=form, categories_data=[], 
                                    current_step='grid_config', draft=draft)
            
            categories_data = json.loads(categories_data_json)
            
            if not categories_data or len(categories_data) < 2:
                flash('Please add at least 2 categories.', 'error')
                return render_template('study_creation/grid_config.html', 
                                    form=form, categories_data=categories_data, 
                                    current_step='grid_config', draft=draft)
            
            if len(categories_data) > 12:
                flash('Maximum 12 categories allowed.', 'error')
                return render_template('study_creation/grid_config.html', 
                                    form=form, categories_data=categories_data, 
                                    current_step='grid_config', draft=draft)
            
            # Check if files are already uploaded
            files_already_uploaded = request.form.get('files_already_uploaded') == 'true'
            
            if not files_already_uploaded:
                # Process uploaded files (legacy mode)
                uploaded_files = {}
                for key, file in request.files.items():
                    if file and file.filename:
                        uploaded_files[key] = file
                
                # Upload files and update content URLs
                from utils.azure_storage import upload_to_azure
                for category_index, category in enumerate(categories_data):
                    for element_index, element in enumerate(category['elements']):
                        if element.get('file'):  # New element with file
                            file_key = f'category_{category_index}_element_{element_index}_file'
                            if file_key in uploaded_files:
                                try:
                                    element_content = upload_to_azure(uploaded_files[file_key])
                                    element['content'] = element_content
                                    print(f"✅ Uploaded element: {element['name']} -> {element_content}")
                                except Exception as e:
                                    print(f"❌ Error uploading element file: {str(e)}")
                                    flash(f'Error uploading element file: {str(e)}', 'error')
                                    continue
                            else:
                                # File not found, remove this element
                                print(f"⚠️  File not found for element: {element['name']}")
                                category['elements'].remove(element)
                                continue
                        
                        # Clean up the element data (remove file object)
                        if 'file' in element:
                            del element['file']
            else:
                # Files are already uploaded, just clean up the data
                print("📁 Files already uploaded, skipping upload process")
                for category in categories_data:
                    print(f"📂 Processing category: {category.get('category_name', 'Unknown')}")
                    for element in category['elements']:
                        print(f"  🔗 Element: {element.get('name', 'Unknown')} -> Content: {element.get('content', 'None')}")
                        if 'file' in element:
                            del element['file']
            
            # Remove empty categories
            categories_data = [cat for cat in categories_data if cat['elements']]
            
            if len(categories_data) < 2:
                flash('Please add at least 2 categories with elements.', 'error')
                return render_template('study_creation/grid_config.html', 
                                    form=form, categories_data=categories_data, 
                                    current_step='grid_config', draft=draft)
            
            # Save grid configuration data
            draft.update_step_data('grid_config', {'categories': categories_data})
            draft.current_step = 'grid_iped'
            draft.save()
            
            flash(f'Grid configuration saved successfully! Created {len(categories_data)} categories.', 'success')
            return redirect(url_for('study_creation.grid_iped'))
            
        except Exception as e:
            print(f"ERROR in grid_config: {str(e)}")
            flash(f'An error occurred while saving grid configuration: {str(e)}', 'error')
            return render_template('study_creation/grid_config.html', 
                                form=form, categories_data=[], 
                                current_step='grid_config', draft=draft)
    
    # GET request - show the form
    # Get existing grid configuration data
    grid_config_data = draft.get_step_data('grid_config')
    categories_data = grid_config_data.get('categories', []) if grid_config_data else []
    
    render_start = time.time()
    result = render_template('study_creation/grid_config.html', 
                           form=form, categories_data=categories_data,
                           current_step='grid_config', draft=draft)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Grid config template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Grid config total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/grid-iped', methods=['GET', 'POST'])
@login_required
def grid_iped():
    """IPED parameters configuration for grid studies after categories are configured."""
    start_time = time.time()
    print(f"⏱️  [PERF] Grid IPED started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if not draft:
        flash('No active study draft found. Please start creating a study.', 'error')
        return redirect(url_for('study_creation.step1a'))
    
    # Check if user can access this step
    access_start = time.time()
    if not draft.can_access_step('grid_iped'):
        flash('Please complete the previous steps first.', 'error')
        return redirect(url_for('study_creation.grid_config'))
    access_duration = time.time() - access_start
    print(f"⏱️  [PERF] Step access check took {access_duration:.3f}s")
    
    form_start = time.time()
    form = GridIPEDForm()
    form_duration = time.time() - form_start
    print(f"⏱️  [PERF] Form creation took {form_duration:.3f}s")
    
    if request.method == 'POST':
        try:
            # Process IPED parameters
            number_of_respondents = int(request.form.get('number_of_respondents', 100))
            
            # Get grid configuration data first (needed for both cases)
            grid_config_data = draft.get_step_data('grid_config')
            categories_data = grid_config_data.get('categories', []) if grid_config_data else []
            
            if not categories_data:
                flash('No grid categories found. Please configure categories first.', 'error')
                return redirect(url_for('study_creation.grid_config'))
            
            # Calculate total elements across all categories
            total_elements = sum(len(cat.get('elements', [])) for cat in categories_data)
            
            # Get calculated tasks_per_consumer from form (if provided)
            calculated_tasks = request.form.get('calculated_tasks_per_consumer')
            if calculated_tasks and calculated_tasks.isdigit():
                tasks_per_consumer = int(calculated_tasks)
                print(f"DEBUG: Grid IPED - Using calculated value from form: {tasks_per_consumer}")
            else:
                # Use advanced algorithm from latest grid task generation
                category_info = {}
                for category in categories_data:
                    category_name = category.get('category_name', f"category_{len(category_info)+1}")
                    elements = category.get('elements', [])
                    category_info[category_name] = [f"element_{i+1}" for i in range(len(elements))]
                
                try:
                    from utils.task_generation import plan_T_E_auto
                    T, E, A_map, avg_k, A_min_used = plan_T_E_auto(
                        category_info=category_info, 
                        study_mode="grid", 
                        max_active_per_row=min(4, len(category_info))  # GRID_MAX_ACTIVE = 4
                    )
                    tasks_per_consumer = T
                    print(f"DEBUG: Grid IPED - Advanced algorithm calculated tasks_per_consumer: {tasks_per_consumer}")
                except Exception as e:
                    print(f"DEBUG: Grid IPED - Advanced algorithm failed ({e}), using fallback calculation")
                    # Fallback to simple calculation
                    tasks_per_consumer = max(8, min(24, total_elements * 2))  # 2 tasks per element, min 8, max 24
            
            # Save IPED parameters
            iped_data = {
                'number_of_respondents': number_of_respondents,
                'tasks_per_consumer': tasks_per_consumer,
                'total_elements': total_elements,
                'exposure_tolerance_cv': 1.0,  # Fixed at 1.0% for grid studies
                'seed': None  # Optional
            }
            
            draft.update_step_data('grid_iped', iped_data)
            draft.current_step = '3a'
            draft.save()
            
            flash(f'IPED parameters saved successfully! Tasks per consumer: {tasks_per_consumer}', 'success')
            return redirect(url_for('study_creation.step3a'))
            
        except Exception as e:
            print(f"ERROR in grid_iped: {str(e)}")
            flash(f'An error occurred while saving IPED parameters: {str(e)}', 'error')
            return render_template('study_creation/grid_iped.html', 
                                form=form, current_step='grid_iped', draft=draft)
    
    # GET request - show the form
    # Get existing IPED data
    grid_iped_data = draft.get_step_data('grid_iped')
    if grid_iped_data:
        form.number_of_respondents.data = grid_iped_data.get('number_of_respondents', 100)
    
    # Calculate and show current values for display
    grid_config_data = draft.get_step_data('grid_config')
    calculated_values = {}
    
    if grid_config_data and 'categories' in grid_config_data:
        categories_data = grid_config_data.get('categories', [])
        total_elements = sum(len(cat.get('elements', [])) for cat in categories_data)
        
        # Use advanced algorithm to calculate tasks_per_consumer for display
        category_info = {}
        for category in categories_data:
            category_name = category.get('category_name', f"category_{len(category_info)+1}")
            elements = category.get('elements', [])
            category_info[category_name] = [f"element_{i+1}" for i in range(len(elements))]
        
        try:
            from utils.task_generation import plan_T_E_auto
            T, E, A_map, avg_k, A_min_used = plan_T_E_auto(
                category_info=category_info, 
                study_mode="grid", 
                max_active_per_row=min(4, len(category_info))
            )
            calculated_tasks_per_consumer = T
            print(f"DEBUG: Grid IPED GET - Advanced algorithm calculated tasks_per_consumer: {calculated_tasks_per_consumer}")
        except Exception as e:
            print(f"DEBUG: Grid IPED GET - Advanced algorithm failed ({e}), using fallback")
            calculated_tasks_per_consumer = max(8, min(24, total_elements * 2))
        
        calculated_values = {
            'total_elements': total_elements,
            'tasks_per_consumer': calculated_tasks_per_consumer,
            'total_categories': len(categories_data)
        }
    
    render_start = time.time()
    result = render_template('study_creation/grid_iped.html', 
                           form=form, current_step='grid_iped', draft=draft,
                           calculated_values=calculated_values)
    render_duration = time.time() - render_start
    print(f"⏱️  [PERF] Grid IPED template rendering took {render_duration:.3f}s")
    
    total_duration = time.time() - start_time
    print(f"⏱️  [PERF] Grid IPED total: {total_duration:.3f}s")
    return result

@study_creation_bp.route('/debug-draft')
@login_required
def debug_draft():
    """Debug route to check draft data."""
    start_time = time.time()
    print(f"⏱️  [PERF] Debug draft started at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    draft_start = time.time()
    draft = get_study_draft()
    draft_duration = time.time() - draft_start
    print(f"⏱️  [PERF] Draft retrieval took {draft_duration:.3f}s")
    
    if not draft:
        return "No draft found"
    
    debug_info = {
        'draft_id': str(draft._id),
        'current_step': draft.current_step,
        'step1a_data': draft.step1a_data,
        'step1b_data': draft.step1b_data,
        'step1c_data': draft.step1c_data,
        'step2a_data': draft.step2a_data,
        'layer_config_data': draft.layer_config_data,  # Layer configuration data
        'layer_iped_data': draft.layer_iped_data,  # Layer IPED data
        'step2b_data': draft.step2b_data,
        'step2c_data': draft.step2c_data,
        'step3a_data': draft.step3a_data,
        'step3b_data': draft.step3b_data,
        'step1a_complete': draft.is_step_complete('1a'),
        'step1b_complete': draft.is_step_complete('1b'),
        'step1c_complete': draft.is_step_complete('1c'),
        'step2a_complete': draft.is_step_complete('2a'),
        'layer_config_complete': draft.is_step_complete('layer_config'),
        'step2b_complete': draft.is_step_complete('2b'),
        'step2c_complete': draft.is_step_complete('2c'),
        'step3a_complete': draft.is_step_complete('3a'),
        'step3b_complete': draft.is_step_complete('3b'),
    }
    
    return f"""
    <h1>Draft Debug Info</h1>
    <pre>{debug_info}</pre>
    
    <h2>Raw Data</h2>
    <pre>layer_config_data: {draft.layer_config_data}</pre>
    <pre>layer_iped_data: {draft.layer_iped_data}</pre>
    
    <h2>Completion Checks</h2>
    <pre>layer_config complete: {draft.is_step_complete('layer_config')}</pre>
    <pre>layer_iped complete: {draft.is_step_complete('layer_iped')}</pre>
    """

@study_creation_bp.route('/upload-immediate', methods=['POST'])
@login_required
def upload_immediate():
    """Handle immediate file uploads for grid category elements."""
    try:
        print(f"📤 Immediate upload request received")
        print(f"📤 Files in request: {list(request.files.keys())}")
        print(f"📤 Form data: {list(request.form.keys())}")
        
        if 'file' not in request.files:
            print("❌ No file in request")
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            print("❌ Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        print(f"📤 Uploading file: {file.filename}")
        
        # Upload to Azure
        from utils.azure_storage import upload_to_azure
        file_url = upload_to_azure(file)
        
        print(f"✅ Upload successful: {file_url}")
        return jsonify({'url': file_url, 'success': True})
        
    except Exception as e:
        print(f"❌ Error in immediate upload: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
