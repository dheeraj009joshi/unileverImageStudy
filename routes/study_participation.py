from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models.study import Study
from models.response import StudyResponse
from datetime import datetime, timezone
import uuid
import json

def serialize_study_for_preloading(study):
    """Serialize study data for image preloading, handling MongoEngine objects"""
    try:
        print(f"🔍 Serializing study {study._id} for preloading...")
        print(f"🔍 Study type: {getattr(study, 'study_type', 'unknown')}")
        print(f"🔍 Has elements: {hasattr(study, 'elements')}")
        print(f"🔍 Has study_layers: {hasattr(study, 'study_layers')}")
        
        # Create a serializable version of the study data
        study_data = {
            'study_type': str(getattr(study, 'study_type', 'unknown')),
            'elements': [],
            'study_layers': []
        }
        
        # Serialize elements for grid studies
        if hasattr(study, 'elements') and study.elements:
            print(f"🔍 Found {len(study.elements)} elements to serialize")
            for element in study.elements:
                try:
                    element_data = {
                        'name': str(getattr(element, 'name', '')),
                        'description': str(getattr(element, 'description', '')),
                        'alt_text': str(getattr(element, 'alt_text', '')),
                        'element_type': str(getattr(element, 'element_type', '')),
                        'content': str(getattr(element, 'content', '')),
                        'image': None
                    }
                    
                    # For grid studies, the image URL is in the 'content' field
                    if hasattr(element, 'content') and element.content:
                        try:
                            # content field contains the file path/URL
                            element_data['image'] = {
                                'url': str(element.content),
                                'filename': str(getattr(element, 'name', ''))
                            }
                        except Exception as img_error:
                            print(f"Error serializing element content: {img_error}")
                            element_data['image'] = None
                    
                    study_data['elements'].append(element_data)
                except Exception as elem_error:
                    print(f"Error serializing element: {elem_error}")
                    continue
        
        # Serialize study_layers for layer studies
        if hasattr(study, 'study_layers') and study.study_layers:
            print(f"🔍 Found {len(study.study_layers)} study layers to serialize")
            for layer in study.study_layers:
                try:
                    layer_data = {
                        'name': str(getattr(layer, 'name', '')),
                        'z_index': int(getattr(layer, 'z_index', 0)),
                        'images': []
                    }
                    
                    if hasattr(layer, 'images') and layer.images:
                        for image in layer.images:
                            try:
                                image_data = {
                                    'name': str(getattr(image, 'name', '')),
                                    'url': str(getattr(image, 'url', '')),
                                    'alt_text': str(getattr(image, 'alt_text', '')),
                                    'order': int(getattr(image, 'order', 0)),
                                    'image_id': str(getattr(image, 'image_id', '')) if hasattr(image, 'image_id') else None
                                }
                                layer_data['images'].append(image_data)
                            except Exception as img_error:
                                print(f"Error serializing layer image: {img_error}")
                                continue
                    
                    study_data['study_layers'].append(layer_data)
                except Exception as layer_error:
                    print(f"Error serializing layer: {layer_error}")
                    continue
        
        # Ensure all values are JSON serializable
        def make_json_safe(obj):
            if obj is None:
                return None
            elif isinstance(obj, (str, int, float, bool)):
                return obj
            elif isinstance(obj, (list, tuple)):
                return [make_json_safe(item) for item in obj]
            elif isinstance(obj, dict):
                return {str(k): make_json_safe(v) for k, v in obj.items()}
            else:
                return str(obj)
        
        study_data = make_json_safe(study_data)
        print(f"🔍 Serialization complete - Elements: {len(study_data['elements'])}, Layers: {len(study_data['study_layers'])}")
        return study_data
        
    except Exception as e:
        print(f"Error serializing study data: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        # Return minimal data to prevent errors
        return {
            'study_type': 'unknown',
            'elements': [],
            'study_layers': []
        }

study_participation = Blueprint('study_participation', __name__)

def safe_datetime_parse(datetime_string):
    """Parse datetime string and ensure timezone-naive format for MongoDB."""
    try:
        dt = datetime.fromisoformat(datetime_string)
        # Convert to UTC timezone-naive for consistent MongoDB storage
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception as e:
        print(f"Error parsing datetime {datetime_string}: {e}")
        return datetime.utcnow()

@study_participation.route('/study/<study_id>/welcome')
def welcome(study_id):
    """Welcome page for study participation"""
    try:
        study = Study.objects.get(_id=study_id)
        
        if study.status != 'active':
            return render_template('study_participation/study_inactive.html', study=study)
        
        # Capture rid parameter for Cint integration
        rid = request.args.get('rid') or request.args.get('RID')
        
        # Initialize session for this study (but don't create response yet)
        session['study_id'] = str(study_id)
        session['current_step'] = 'welcome'
        session['study_data'] = {
            'personal_info': {},
            'classification_answers': [],
            'task_ratings': []
        }
        
        # Store rid in session if provided (for Cint integration)
        if rid:
            session['rid'] = rid
            print(f"Cint RID captured: {rid}")
        
        # Serialize study data for image preloading
        try:
            serialized_study_data = serialize_study_for_preloading(study)
            print(f"DEBUG: Serialized study data for {study_id}: {type(serialized_study_data)}")
            print(f"DEBUG: Study type: {serialized_study_data.get('study_type', 'unknown')}")
            print(f"DEBUG: Elements count: {len(serialized_study_data.get('elements', []))}")
            print(f"DEBUG: Study layers count: {len(serialized_study_data.get('study_layers', []))}")
        except Exception as e:
            print(f"ERROR: Failed to serialize study data for {study_id}: {e}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            # Provide fallback data
            serialized_study_data = {
                'study_type': getattr(study, 'study_type', 'unknown'),
                'elements': [],
                'study_layers': []
            }
        
        return render_template('study_participation/welcome.html', 
                             study=study, 
                             serialized_study_data=serialized_study_data)
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error starting study: {str(e)}', 'error')
        return redirect(url_for('index'))

@study_participation.route('/study/<study_id>/participate')
def participate(study_id):
    """Direct participation link - redirects to welcome"""
    # Capture rid parameter for Cint integration and pass it along
    rid = request.args.get('rid')
    
    if rid:
        return redirect(url_for('study_participation.welcome', study_id=study_id, rid=rid))
    else:
        return redirect(url_for('study_participation.welcome', study_id=study_id))

@study_participation.route('/study/<study_id>/debug-data')
def debug_study_data(study_id):
    """Debug route to check study data serialization"""
    try:
        study = Study.objects.get(_id=study_id)
        serialized_study_data = serialize_study_for_preloading(study)
        
        return {
            'study_id': str(study_id),
            'study_title': study.title,
            'study_type': study.study_type,
            'serialized_data': serialized_study_data,
            'serialized_type': str(type(serialized_study_data)),
            'has_elements': len(serialized_study_data.get('elements', [])) > 0,
            'has_layers': len(serialized_study_data.get('study_layers', [])) > 0
        }
    except Exception as e:
        return {'error': str(e), 'study_id': str(study_id)}

@study_participation.route('/participate/<share_token>')
def participate_by_token(share_token):
    """Access study participation by share token"""
    try:
        study = Study.objects.get(share_token=share_token)
        
        if study.status != 'active':
            return render_template('study_participation/study_inactive.html', study=study)
        
        # Capture rid parameter for Cint integration and pass it along
        rid = request.args.get('rid')
        
        # Redirect to welcome page with study ID, preserving rid parameter
        if rid:
            return redirect(url_for('study_participation.welcome', study_id=str(study._id), rid=rid))
        else:
            return redirect(url_for('study_participation.welcome', study_id=str(study._id)))
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error accessing study: {str(e)}', 'error')
        return redirect(url_for('index'))

@study_participation.route('/study/<study_id>/personal-info', methods=['GET', 'POST'])
def personal_info(study_id):
    """Personal information collection page"""
    try:
        study = Study.objects.get(_id=study_id)
        
        if study.status != 'active':
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        if request.method == 'POST':
            # Debug: Check study object before processing
            print(f"DEBUG: Processing POST request for study {study_id}")
            print(f"DEBUG: Study type: {study.study_type}")
            print(f"DEBUG: Study has study_layers: {hasattr(study, 'study_layers')}")
            if hasattr(study, 'study_layers'):
                print(f"DEBUG: Study layers count: {len(study.study_layers) if study.study_layers else 0}")
            print(f"DEBUG: Study has elements: {hasattr(study, 'elements')}")
            if hasattr(study, 'elements'):
                print(f"DEBUG: Study elements count: {len(study.elements) if study.elements else 0}")
            print(f"DEBUG: Study has IPED parameters: {hasattr(study, 'iped_parameters')}")
            if hasattr(study, 'iped_parameters') and study.iped_parameters:
                print(f"DEBUG: IPED parameters: {study.iped_parameters}")
            
            # Get form data
            birth_date = request.form.get('birth_date')
            gender = request.form.get('gender')
            
            # Validate required fields
            if not birth_date or not gender:
                
                return render_template('study_participation/personal_info.html', study=study)
            
            # Calculate age from birth date
            try:
                birth_date_obj = datetime.strptime(birth_date, '%Y-%m-%d')
                age = (datetime.utcnow() - birth_date_obj).days // 365
                if age < 13 or age > 120:
                    flash('Please enter a valid age between 13 and 120.', 'error')
                    return render_template('study_participation/personal_info.html', study=study)
            except ValueError:
                flash('Please enter a valid birth date.', 'error')
                return render_template('study_participation/personal_info.html', study=study)
            
            # Store in session
            if 'study_data' not in session:
                session['study_data'] = {}
            personal_info_data = {
                'birth_date': birth_date,
                'age': age,
                'gender': gender
            }
            session['study_data']['personal_info'] = personal_info_data
            session['current_step'] = 'personal_info'
            
            # Mark session as modified (CRITICAL for Flask sessions)
            session.modified = True
            
            print(f"Personal info stored in session: {personal_info_data}")
            print(f"Current session data: {session.get('study_data')}")
            print(f"Session ID: {session.get('_id', 'No session ID')}")
            print(f"Session modified flag: {session.modified}")
            
            # Create StudyResponse object now that user has actually started
            try:
                # Validate study object before proceeding
                try:
                    study.validate()
                    print("DEBUG: Study validation passed")
                except Exception as validation_error:
                    print(f"DEBUG: Study validation failed: {validation_error}")
                    # Continue anyway, but log the issue
                
                # Calculate respondent ID based on total responses
                respondent_id = study.total_responses
                
                # Get total tasks from IPED parameters
                total_tasks = 0
                if hasattr(study, 'iped_parameters') and study.iped_parameters:
                    # Handle both grid and layer study IPED parameters
                    if study.study_type == 'grid':
                        total_tasks = getattr(study.iped_parameters, 'tasks_per_consumer', 25)
                    elif study.study_type == 'layer':
                        # For layer studies, calculate from layer configuration
                        if hasattr(study, 'study_layers') and study.study_layers:
                            # Calculate tasks per consumer based on layer configuration
                            uniqueness_capacity = 1
                            for layer in study.study_layers:
                                uniqueness_capacity *= len(layer.images)
                            total_tasks = min(24, uniqueness_capacity)  # Cap at 24 tasks
                        else:
                            total_tasks = getattr(study.iped_parameters, 'tasks_per_consumer', 16)
                    else:
                        total_tasks = getattr(study.iped_parameters, 'tasks_per_consumer', 25)
                    
                    print(f"IPED tasks per consumer for {study.study_type} study: {total_tasks}")
                else:
                    print("Warning: No IPED parameters found, using default")
                    if study.study_type == 'layer':
                        total_tasks = 16  # Default for layer studies
                    else:
                        total_tasks = 25  # Default for grid studies
                
                # Create new response object
                session_id = str(uuid.uuid4())
                
                # Get Cint RID from session if available
                cint_rid = session.get('rid')
                
                # Initialize all required fields with proper defaults
                response_data = {
                    'study': study,
                    'session_id': session_id,
                    'respondent_id': respondent_id,
                    'total_tasks_assigned': total_tasks,
                    'completed_tasks_count': 0,
                    'session_start_time': datetime.utcnow(),
                    'is_completed': False,
                    'classification_answers': [],
                    'personal_info': personal_info_data,
                    'total_study_duration': 0.0,
                    'last_activity': datetime.utcnow(),
                    'completed_tasks': [],  # Initialize empty list
                    'current_task_index': 0,  # Start at first task
                    'completion_percentage': 0.0,  # Start at 0%
                    'is_abandoned': True  # Default to abandoned until completed
                }
                
                # Add Cint RID if available
                if cint_rid:
                    response_data['cint_rid'] = cint_rid
                    print(f"Storing Cint RID in response: {cint_rid}")
                
                print(f"Creating StudyResponse with data: {response_data}")
                
                response = StudyResponse(**response_data)
                response.save()
                
                # Update study response counters
                study.total_responses += 1
                study.abandoned_responses += 1  # Increment abandoned count since response starts as abandoned
                study.save()
                
                # Store in session
                session['response_id'] = str(response._id)
                session['session_id'] = session_id
                session['respondent_id'] = respondent_id
                
                # Mark session as modified (CRITICAL for Flask sessions)
                session.modified = True
                
                print(f"Created new response: {response._id} with respondent_id: {respondent_id}")
                print(f"Study total_responses updated to: {study.total_responses}")
                
            except Exception as e:
                print(f"Error creating response: {str(e)}")
                print(f"Error type: {type(e).__name__}")
                import traceback
                print(f"Full traceback: {traceback.format_exc()}")
                
                # More specific error message based on error type
                if 'validation' in str(e).lower():
                    flash('Data validation error. Please check your input and try again.', 'error')
                elif 'duplicate' in str(e).lower():
                    flash('Session already exists. Please refresh and try again.', 'error')
                else:
                    flash(f'Error creating study response: {str(e)}. Please try again.', 'error')
                
                return render_template('study_participation/personal_info.html', study=study)
            
            # Redirect to classification questions
            return redirect(url_for('study_participation.classification', study_id=study_id))
        
        # Get today's date for max date validation
        today_date = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Serialize study data for image preloading
        serialized_study_data = serialize_study_for_preloading(study)
        
        return render_template('study_participation/personal_info.html', 
                             study=study, 
                             today_date=today_date,
                             serialized_study_data=serialized_study_data)
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('study_participation.welcome', study_id=study_id))

@study_participation.route('/study/<study_id>/classification', methods=['GET', 'POST'])
def classification(study_id):
    """Classification questions page"""
    try:
        study = Study.objects.get(_id=study_id)
        
        if study.status != 'active':
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Check if personal info is completed
        if not session.get('study_data', {}).get('personal_info'):
            return redirect(url_for('study_participation.personal_info', study_id=study_id))
        
        if request.method == 'POST':
            # Get classification answers
            answers = []
            for question in study.classification_questions:
                answer = request.form.get(f'classification_{question.question_id}')
                if answer:
                    answers.append({
                        'question_id': question.question_id,
                        'question_text': question.question_text,
                        'answer': answer,
                        'answer_timestamp': datetime.utcnow().isoformat(),
                        'time_spent_seconds': 0.0  # Will be calculated from frontend
                    })
            
            # Store in session
            if 'study_data' not in session:
                session['study_data'] = {}
            session['study_data']['classification_answers'] = answers
            session['current_step'] = 'classification'
            
            # Mark session as modified (CRITICAL for Flask sessions)
            session.modified = True
            
            print(f"Classification answers stored in session: {answers}")
            print(f"Current session data: {session.get('study_data')}")
            
            # Update StudyResponse object if it exists
            if 'response_id' in session:
                try:
                    response = StudyResponse.objects.get(_id=session['response_id'])
                    # Convert to ClassificationAnswer objects
                    from models.response import ClassificationAnswer
                    classification_answers = []
                    for answer_data in answers:
                        classification_answer = ClassificationAnswer(
                            question_id=answer_data['question_id'],
                            question_text=answer_data['question_text'],
                            answer=answer_data['answer'],
                            answer_timestamp=safe_datetime_parse(answer_data['answer_timestamp']),
                            time_spent_seconds=answer_data['time_spent_seconds']
                        )
                        classification_answers.append(classification_answer)
                    
                    response.classification_answers = classification_answers
                    response.last_activity = datetime.utcnow()
                    response.save()
                    print(f"Updated classification answers for response: {response._id}")
                except StudyResponse.DoesNotExist:
                    print(f"Response not found: {session['response_id']}")
                except Exception as e:
                    print(f"Error updating response: {str(e)}")
            else:
                print("No response_id in session")
            
            # Redirect to lightning-fast tasks interface
            return redirect(url_for('study_participation.load_all_tasks', study_id=study_id))
        
        # Serialize study data for image preloading
        serialized_study_data = serialize_study_for_preloading(study)
        
        return render_template('study_participation/classification.html', 
                             study=study,
                             serialized_study_data=serialized_study_data)
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('study_participation.personal_info', study_id=study_id))

@study_participation.route('/study/<study_id>/tasks', methods=['GET'])
def load_all_tasks(study_id):
    """Load all tasks for a study at once - for lightning-fast task flow"""
    try:
        study = Study.objects.get(_id=study_id)
        
        if study.status != 'active':
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Check if previous steps are completed
        if not session.get('study_data', {}).get('personal_info'):
            return redirect(url_for('study_participation.personal_info', study_id=study_id))
        if not session.get('study_data', {}).get('classification_answers'):
            return redirect(url_for('study_participation.classification', study_id=study_id))
        
        # Ensure study_data structure is complete
        if 'study_data' not in session:
            session['study_data'] = {}
        if 'task_ratings' not in session['study_data']:
            session['study_data']['task_ratings'] = []
        
        # Get total tasks from IPED parameters
        total_tasks = 0
        if hasattr(study, 'iped_parameters') and study.iped_parameters:
            if study.study_type == 'grid':
                total_tasks = getattr(study.iped_parameters, 'tasks_per_consumer', 25)
            elif study.study_type == 'layer':
                total_final_tasks = getattr(study.iped_parameters, 'total_tasks', 16)
                totalusers = getattr(study.iped_parameters, 'number_of_respondents', 16)
                total_tasks = total_final_tasks / totalusers
            else:
                total_tasks = getattr(study.iped_parameters, 'tasks_per_consumer', 25)
        else:
            # Default fallback
            if study.study_type == 'layer':
                total_tasks = 16
            else:
                total_tasks = 25
        
        # Generate tasks if they don't exist
        if not hasattr(study, 'tasks') or not study.tasks:
            try:
                from utils.task_generation import generate_grid_tasks, generate_layer_tasks_v2
                
                if study.study_type == 'grid':
                    result = generate_grid_tasks(
                        num_elements=study.iped_parameters.num_elements,
                        tasks_per_consumer=study.iped_parameters.tasks_per_consumer,
                        number_of_respondents=study.iped_parameters.number_of_respondents,
                        exposure_tolerance_cv=getattr(study.iped_parameters, 'exposure_tolerance_cv', 1.0),
                        seed=getattr(study.iped_parameters, 'seed', None),
                        elements=study.elements
                    )
                    study.tasks = result['tasks']
                elif study.study_type == 'layer':
                    if not hasattr(study, 'study_layers') or not study.study_layers:
                        flash('Layer study configuration not found.', 'error')
                        return redirect(url_for('study_participation.welcome', study_id=study_id))
                    
                    result = generate_layer_tasks_v2(
                        layers_data=study.study_layers,
                        number_of_respondents=study.iped_parameters.number_of_respondents,
                        exposure_tolerance_pct=getattr(study.iped_parameters, 'exposure_tolerance_pct', 2.0),
                        seed=getattr(study.iped_parameters, 'seed', None)
                    )
                    study.tasks = result['tasks']
                else:
                    flash('Study tasks not configured properly.', 'error')
                    return redirect(url_for('study_participation.welcome', study_id=study_id))
                
                study.save()
            except Exception as e:
                flash(f'Error generating tasks: {str(e)}', 'error')
                return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Get all tasks for respondent 0 (anonymous participation)
        respondent_tasks = study.tasks.get("0", [])
        if not respondent_tasks or len(respondent_tasks) != total_tasks:
            flash('Task data not found or incomplete.', 'error')
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Render the lightning-fast task interface with all tasks loaded
        return render_template('study_participation/tasks_lightning.html', 
                           study=study, 
                           total_tasks=total_tasks, 
                           all_tasks=respondent_tasks)
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('study_participation.welcome', study_id=study_id))

@study_participation.route('/study/<study_id>/task/<int:task_number>', methods=['GET', 'POST'])
def task(study_id, task_number):
    """Task interface page"""
    try:
        study = Study.objects.get(_id=study_id)
        
        if study.status != 'active':
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Check if previous steps are completed
        if not session.get('study_data', {}).get('personal_info'):
            return redirect(url_for('study_participation.personal_info', study_id=study_id))
        if not session.get('study_data', {}).get('classification_answers'):
            return redirect(url_for('study_participation.classification', study_id=study_id))
        
        # Ensure study_data structure is complete
        if 'study_data' not in session:
            session['study_data'] = {}
        if 'task_ratings' not in session['study_data']:
            session['study_data']['task_ratings'] = []
        
        # Get total tasks from IPED parameters first (before debugging)
        total_tasks = 0
        if hasattr(study, 'iped_parameters') and study.iped_parameters:
            if study.study_type == 'grid':
                total_tasks = getattr(study.iped_parameters, 'tasks_per_consumer', 25)
            elif study.study_type == 'layer':
                total_final_tasks=getattr(study.iped_parameters, 'total_tasks', 16)
                totalusers=getattr(study.iped_parameters, 'number_of_respondents', 16)
                total_tasks = total_final_tasks/totalusers
            else:
                total_tasks = getattr(study.iped_parameters, 'tasks_per_consumer', 25)
        else:
            # Default fallback if no IPED parameters
            if study.study_type == 'layer':
                total_tasks = 16
            else:
                total_tasks = 25

        print(f"Task route - Session data: {session.get('study_data')}")
        print(f"Task route - Response ID: {session.get('response_id')}")
        print(f"Task route - Study type: {study.study_type}")
        print(f"Task route - Study has tasks: {hasattr(study, 'tasks')}")
        if hasattr(study, 'tasks'):
            print(f"Task route - Tasks count: {len(study.tasks) if study.tasks else 0}")
        print(f"Task route - Study has IPED parameters: {hasattr(study, 'iped_parameters')}")
        if hasattr(study, 'iped_parameters') and study.iped_parameters:
            print(f"Task route - IPED parameters: {study.iped_parameters}")
        print(f"Task route - Total tasks calculated: {total_tasks}")
        
        # Get tasks from study - check if tasks exist
        if not hasattr(study, 'tasks') or not study.tasks:
            # Try to generate tasks if they don't exist
            try:
                from utils.task_generation import generate_grid_tasks, generate_layer_tasks_v2
                
                if study.study_type == 'grid':
                    # Generate grid study tasks
                    result = generate_grid_tasks(
                        num_elements=study.iped_parameters.num_elements,
                        tasks_per_consumer=study.iped_parameters.tasks_per_consumer,
                        number_of_respondents=study.iped_parameters.number_of_respondents,
                        exposure_tolerance_cv=getattr(study.iped_parameters, 'exposure_tolerance_cv', 1.0),
                        seed=getattr(study.iped_parameters, 'seed', None),
                        elements=study.elements
                    )
                    study.tasks = result['tasks']
                elif study.study_type == 'layer':
                    # Generate layer study tasks using new study_layers structure
                    if not hasattr(study, 'study_layers') or not study.study_layers:
                        flash('Layer study configuration not found.', 'error')
                        return redirect(url_for('study_participation.welcome', study_id=study_id))
                    
                    # Use the new layer tasks generation function
                    result = generate_layer_tasks_v2(
                        layers_data=study.study_layers,
                        number_of_respondents=study.iped_parameters.number_of_respondents,
                        exposure_tolerance_pct=getattr(study.iped_parameters, 'exposure_tolerance_pct', 2.0),
                        seed=getattr(study.iped_parameters, 'seed', None)
                    )
                    study.tasks = result['tasks']
                else:
                    flash('Study tasks not configured properly.', 'error')
                    return redirect(url_for('study_participation.welcome', study_id=study_id))
                
                study.save()
            except Exception as e:
                flash(f'Error generating tasks: {str(e)}', 'error')
                return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Check if tasks were generated
        if not hasattr(study, 'tasks') or not study.tasks:
            flash('Study tasks could not be generated.', 'error')
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # total_tasks is already calculated above 
        
        if task_number < 1 or task_number > total_tasks:
            flash('Invalid task number.', 'error')
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Get the specific task data - tasks are organized by respondent_id
        # For anonymous participation, we'll use respondent_id 0
        respondent_tasks = study.tasks.get("0", [])
        if not respondent_tasks or task_number > len(respondent_tasks):
            flash('Task data not found.', 'error')
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        current_task = respondent_tasks[task_number - 1]
        
        # For GET requests, just render the task page
        # For POST requests (if any), handle them the same way
        # The actual rating submission is now handled via JavaScript and sessionStorage
        
        return render_template('study_participation/task.html', 
                           study=study, task_number=task_number, 
                           total_tasks=total_tasks, current_task=current_task)
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('study_participation.welcome', study_id=study_id))

@study_participation.route('/study/<study_id>/submit-all-ratings', methods=['POST'])
def submit_all_ratings(study_id):
    """Submit all task ratings at once from lightning-fast task flow.

    Writes ratings directly to StudyResponse to avoid exceeding cookie size.
    """
    print(f"=== SUBMIT ALL RATINGS ROUTE CALLED ===")
    print(f"Study ID: {study_id}")
    
    try:
        study = Study.objects.get(_id=study_id)
        print(f"Study found: {study.title}")
        
        if study.status != 'active':
            print(f"Study not active: {study.status}")
            return {'error': 'Study not active'}, 400
        
        # Get all task ratings from request
        data = request.get_json()
        print(f"Request JSON data: {data}")
        
        if not data or 'task_ratings' not in data:
            print("No task_ratings data provided")
            return {'error': 'No task ratings provided'}, 400
        
        task_ratings = data['task_ratings']
        if not task_ratings or len(task_ratings) == 0:
            print("Empty task_ratings array")
            return {'error': 'No task ratings to submit'}, 400
        
        print(f"Processing {len(task_ratings)} task ratings")
        
        # Ensure we have a response to write to
        response_id = session.get('response_id')
        if not response_id:
            print("No response_id in session for bulk submit")
            return {'error': 'No active response session'}, 400
        
        try:
            response = StudyResponse.objects.get(_id=response_id)
        except StudyResponse.DoesNotExist:
            print(f"Response not found for id {response_id}")
            return {'error': 'Response not found'}, 404
        
        # Persist each rating directly to Mongo to avoid oversized cookies
        saved_count = 0
        for tr in task_ratings:
            try:
                if not tr or 'task_number' not in tr or 'rating' not in tr:
                    continue
                # Build CompletedTask data (mirror logic in completed())
                task_id = f"task_{tr['task_number']}"
                task_data_dict = tr.get('task_data', {})
                task_payload = {
                    'task_id': task_id,
                    'respondent_id': session.get('respondent_id', 0),
                    'task_index': int(tr['task_number']) - 1,
                    'elements_shown_in_task': task_data_dict.get('elements_shown', {}),
                    'elements_shown_content': task_data_dict.get('elements_shown_content', {}),
                    'task_type': task_data_dict.get('task_type', study.study_type),
                    'task_context': task_data_dict.get('task_context', {}),
                    'task_start_time': safe_datetime_parse(tr.get('task_start_time') or datetime.utcnow().isoformat()),
                    'task_completion_time': safe_datetime_parse(tr.get('task_end_time') or datetime.utcnow().isoformat()),
                    'task_duration_seconds': float(tr.get('task_duration_seconds', 0.0)),
                    'rating_given': int(tr['rating']),
                    'rating_timestamp': safe_datetime_parse(tr.get('timestamp') or datetime.utcnow().isoformat()),
                    'element_interactions': task_data_dict.get('element_interactions', [])
                }
                # De-duplicate by task_id if already added
                existing_idx = next((i for i, t in enumerate(response.completed_tasks) if t.task_id == task_id), None)
                if existing_idx is not None:
                    response.completed_tasks.pop(existing_idx)
                response.add_completed_task(task_payload)
                saved_count += 1
            except Exception as e:
                print(f"Failed to save task rating {tr}: {e}")
                continue
        
        response.last_activity = datetime.utcnow()
        response.save()
        print(f"Persisted {saved_count} ratings to response {response._id}")
        
        # Keep session small: do not store ratings array
        session.setdefault('study_data', {})
        session['study_data']['task_ratings_count'] = saved_count
        session.modified = True
        
        return {'success': True, 'message': f'Successfully saved {saved_count} task ratings'}
        
    except Study.DoesNotExist:
        print(f"Study not found: {study_id}")
        return {'error': 'Study not found'}, 404
    except Exception as e:
        print(f"Error submitting all ratings: {str(e)}")
        return {'error': f'Server error: {str(e)}'}, 500

@study_participation.route('/study/<study_id>/task-complete', methods=['POST'])
def task_complete(study_id):
    """Handle a single task completion.

    Writes directly to StudyResponse and avoids storing heavy payloads in the session.
    """
    print(f"=== TASK COMPLETE ROUTE CALLED ===")
    print(f"Study ID: {study_id}")
    print(f"Request method: {request.method}")
    print(f"Request URL: {request.url}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Session data: {session}")
    
    try:
        study = Study.objects.get(_id=study_id)
        print(f"Study found: {study.title}")
        
        if study.status != 'active':
            print(f"Study not active: {study.status}")
            return {'error': 'Study not active'}, 400
        
        # Get task data from request
        data = request.get_json()
        
        print(f"Request JSON data: {data}")
        
        if not data:
            print("No JSON data provided")
            return {'error': 'No data provided'}, 400
        
        # Validate required fields
        required_fields = ['task_number', 'rating', 'timestamp', 'task_start_time', 'task_end_time', 'task_duration_seconds']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            print(f"Missing required fields: {missing_fields}")
            return {'error': f'Missing required fields: {missing_fields}'}, 400
        
        # Persist directly to response
        response_id = session.get('response_id')
        if not response_id:
            print("No response_id in session for task-complete")
            return {'error': 'No active response session'}, 400
        
        try:
            response = StudyResponse.objects.get(_id=response_id)
        except StudyResponse.DoesNotExist:
            print(f"Response not found for id {response_id}")
            return {'error': 'Response not found'}, 404
        
        task_id = f"task_{data.get('task_number')}"
        task_data_dict = data.get('task_data', {})
        task_payload = {
            'task_id': task_id,
            'respondent_id': session.get('respondent_id', 0),
            'task_index': int(data.get('task_number')) - 1,
            'elements_shown_in_task': task_data_dict.get('elements_shown', {}),
            'elements_shown_content': task_data_dict.get('elements_shown_content', {}),
            'task_type': task_data_dict.get('task_type', study.study_type),
            'task_context': task_data_dict.get('task_context', {}),
            'task_start_time': safe_datetime_parse(data.get('task_start_time')),
            'task_completion_time': safe_datetime_parse(data.get('task_end_time')),
            'task_duration_seconds': float(data.get('task_duration_seconds', 0.0)),
            'rating_given': int(data.get('rating')),
            'rating_timestamp': safe_datetime_parse(data.get('timestamp')),
            'element_interactions': task_data_dict.get('element_interactions', [])
        }
        # De-duplicate by task_id
        existing_idx = next((i for i, t in enumerate(response.completed_tasks) if t.task_id == task_id), None)
        if existing_idx is not None:
            response.completed_tasks.pop(existing_idx)
        response.add_completed_task(task_payload)
        response.last_activity = datetime.utcnow()
        response.save()
        
        # Keep only a lightweight counter in session
        session.setdefault('study_data', {})
        prev = int(session['study_data'].get('task_ratings_count', 0))
        session['study_data']['task_ratings_count'] = max(prev, int(data.get('task_number', prev)))
        session.modified = True
        
        print(f"Task {data.get('task_number')} persisted to response {response._id}")
        return {'success': True, 'message': 'Task saved'}
        
    except Study.DoesNotExist:
        print(f"Study not found with ID: {study_id}")
        return {'error': 'Study not found'}, 404
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}, 500

@study_participation.route('/study/<study_id>/completed')
def completed(study_id):
    """Study completion page"""
    try:
        study = Study.objects.get(_id=study_id)
        
        # Prefer database state over session (session may be trimmed by cookie limits)
        study_data = session.get('study_data', {})
        if not (study_data.get('personal_info') and study_data.get('classification_answers')):
            print("Session missing PI/classification; proceeding using DB state")
        
        # Update existing StudyResponse object
        try:
            if 'response_id' in session:
                print(f"\n--- COMPLETING STUDY RESPONSE ---")
                print(f"Response ID: {session['response_id']}")
                print(f"Session data keys: {list(session.keys())}")
                print(f"Study data keys: {list(study_data.keys())}")
                
                response = StudyResponse.objects.get(_id=session['response_id'])
                print(f"Found response: {response._id}")
                
                # Calculate session timing
                completion_time = datetime.utcnow()
                
                # Use the session_start_time from the response object (set when response was created)
                start_time = response.session_start_time
                total_time = (completion_time - start_time).total_seconds()
                
                print(f"Session start time: {start_time}")
                print(f"Session end time: {completion_time}")
                print(f"Total session duration: {total_time} seconds")
                
                # Update response with completion data
                response.session_end_time = completion_time
                response.total_study_duration = total_time
                response.last_activity = completion_time
                # If tasks already saved via APIs, skip rebuilding from session
                if response.completed_tasks and len(response.completed_tasks) >= response.total_tasks_assigned:
                    print("All tasks already saved in DB; skipping rebuild from session")
                else:
                    # Fall back: add from any session buffer if present
                    buffered = study_data.get('task_ratings') or []
                    print(f"\n--- ADDING COMPLETED TASKS FROM SESSION BUFFER ({len(buffered)}) ---")
                    for i, task_rating in enumerate(buffered):
                        print(f"Processing task {i+1}/{len(study_data['task_ratings'])}: {task_rating['task_number']}")
                    
                        # Get task timing from JavaScript
                        task_start_time = None
                        task_completion_time = None
                        task_duration = 0.0
                    
                        # Use the actual task timestamps from JavaScript
                        try:
                            if 'task_start_time' in task_rating:
                                task_start_time = safe_datetime_parse(task_rating['task_start_time'])
                            if 'task_end_time' in task_rating:
                                task_completion_time = safe_datetime_parse(task_rating['task_end_time'])
                            if 'task_duration_seconds' in task_rating:
                                task_duration = float(task_rating['task_duration_seconds'])
                                
                            print(f"  Task {task_rating['task_number']}: Start={task_start_time}, End={task_completion_time}, Duration={task_duration}s")
                        except Exception as e:
                            print(f"  Error parsing task timestamps: {e}")
                            # Fallback values
                            task_start_time = completion_time
                            task_completion_time = completion_time
                            task_duration = 0.0
                    
                        # Extract comprehensive task data
                        task_data_dict = task_rating.get('task_data', {})
                        
                        task_data = {
                            'task_id': f"task_{task_rating['task_number']}",
                            'respondent_id': session['respondent_id'],
                            'task_index': task_rating['task_number'] - 1,
                            # Grid study data
                            'elements_shown_in_task': task_data_dict.get('elements_shown', {}),
                            # Layer study data
                            'elements_shown_content': task_data_dict.get('elements_shown_content', {}),
                            # Task metadata
                            'task_type': task_data_dict.get('task_type', study.study_type),
                            'task_context': task_data_dict.get('task_context', {}),
                            # Timing data
                            'task_start_time': task_start_time,
                            'task_completion_time': task_completion_time,
                            'task_duration_seconds': task_duration,
                            # Rating data
                            'rating_given': task_rating['rating'],
                            'rating_timestamp': safe_datetime_parse(task_rating['timestamp']),
                            # Element interactions (if available)
                            'element_interactions': task_data_dict.get('element_interactions', [])
                        }
                        
                        print(f"  📋 Comprehensive task data prepared:")
                        print(f"    - Elements shown: {len(task_data['elements_shown_in_task'])} items")
                        print(f"    - Elements shown content: {len(task_data['elements_shown_content'])} items")
                        print(f"    - Task type: {task_data['task_type']}")
                        print(f"    - Element interactions: {len(task_data['element_interactions'])} items")
                        
                        print(f"  Adding task data: {task_data}")
                        response.add_completed_task(task_data)
                        print(f"  Task added successfully")
                
                print(f"\n--- SAVING RESPONSE ---")
                response.update_completion_percentage()
                print(f"Completion percentage: {response.completion_percentage}")
                
                response.save()
                print(f"Response saved successfully!")
                
                print(f"Completed response: {response._id}")
                
                # Check for Cint RID before clearing session
                cint_rid = session.get('rid')
                
                # Clear session data
                session.pop('study_data', None)
                session.pop('study_id', None)
                session.pop('current_step', None)
                session.pop('response_id', None)
                session.pop('session_id', None)
                session.pop('respondent_id', None)
                session.pop('rid', None)  # Also clear the rid
                
                print(f"Session cleared successfully")
                
                # If Cint RID was provided, redirect to Cint callback
                if cint_rid:
                    cint_redirect_url = f"https://notch.insights.supply/cb?token=446a1929-7cfa-4ee3-9778-a9e9dae498ac&RID={cint_rid}"
                    print(f"Redirecting to Cint callback: {cint_redirect_url}")
                    return render_template('study_participation/cint_redirect.html', 
                                         study=study, 
                                         response=response, 
                                         redirect_url=cint_redirect_url)
                else:
                    # Normal completion page
                    return render_template('study_participation/completed.html', study=study, response=response)
            else:
                print("No response_id in session")
                flash('No response found. Please start the study again.', 'error')
                return redirect(url_for('study_participation.welcome', study_id=study_id))
            
        except Exception as e:
            print(f"\n--- ERROR IN COMPLETED ROUTE ---")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            import traceback
            print(f"Full traceback:")
            traceback.print_exc()
            flash(f'Error saving response: {str(e)}', 'error')
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('study_participation.welcome', study_id=study_id))

@study_participation.route('/study/<study_id>/inactive')
def study_inactive(study_id):
    """Study inactive page"""
    try:
        study = Study.objects.get(_id=study_id)
        return render_template('study_participation/study_inactive.html', study=study)
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
