from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models.study import Study
from models.response import StudyResponse
from datetime import datetime, timezone
import uuid
import json

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
        
        # Initialize session for this study (but don't create response yet)
        session['study_id'] = str(study_id)
        session['current_step'] = 'welcome'
        session['study_data'] = {
            'personal_info': {},
            'classification_answers': [],
            'task_ratings': []
        }
        
        return render_template('study_participation/welcome.html', study=study)
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error starting study: {str(e)}', 'error')
        return redirect(url_for('index'))

@study_participation.route('/study/<study_id>/participate')
def participate(study_id):
    """Direct participation link - redirects to welcome"""
    return redirect(url_for('study_participation.welcome', study_id=study_id))

@study_participation.route('/participate/<share_token>')
def participate_by_token(share_token):
    """Access study participation by share token"""
    try:
        study = Study.objects.get(share_token=share_token)
        
        if study.status != 'active':
            return render_template('study_participation/study_inactive.html', study=study)
        
        # Redirect to welcome page with study ID
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
            # Get form data
            birth_date = request.form.get('birth_date')
            gender = request.form.get('gender')
            
            # Validate required fields
            if not birth_date or not gender:
                flash('Please fill in all required fields.', 'error')
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
            
            # Create StudyResponse object now that user has actually started
            try:
                # Calculate respondent ID based on total responses
                respondent_id = study.total_responses
                
                # Get total tasks from IPED parameters
                total_tasks = 0
                if hasattr(study, 'iped_parameters') and study.iped_parameters:
                    total_tasks = study.iped_parameters.tasks_per_consumer
                    print(f"IPED tasks per consumer: {total_tasks}")
                else:
                    print("Warning: No IPED parameters found, using default")
                    total_tasks = 25  # Default fallback
                
                # Create new response object
                session_id = str(uuid.uuid4())
                response = StudyResponse(
                    _id=str(uuid.uuid4()),
                    study=study,
                    session_id=session_id,
                    respondent_id=respondent_id,
                    total_tasks_assigned=total_tasks,
                    completed_tasks_count=0,
                    session_start_time=datetime.utcnow(),
                    is_completed=False,
                    classification_answers=[],
                    personal_info=personal_info_data,
                    total_study_duration=0.0,
                    last_activity=datetime.utcnow()
                )
                response.save()
                
                # Update study total_responses
                study.total_responses += 1
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
                flash('Error creating study response. Please try again.', 'error')
                return render_template('study_participation/personal_info.html', study=study)
            
            # Redirect to classification questions
            return redirect(url_for('study_participation.classification', study_id=study_id))
        
        # Get today's date for max date validation
        today_date = datetime.utcnow().strftime('%Y-%m-%d')
        return render_template('study_participation/personal_info.html', study=study, today_date=today_date)
        
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
            
            # Redirect to first task
            return redirect(url_for('study_participation.task', study_id=study_id, task_number=1))
        
        return render_template('study_participation/classification.html', study=study)
        
    except Study.DoesNotExist:
        flash('Study not found.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('study_participation.personal_info', study_id=study_id))

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
        
        print(f"Task route - Session data: {session.get('study_data')}")
        print(f"Task route - Response ID: {session.get('response_id')}")
        
        # Get tasks from study - check if tasks exist
        if not hasattr(study, 'tasks') or not study.tasks:
            # Try to generate tasks if they don't exist
            try:
                if hasattr(study, 'generate_tasks'):
                    study.generate_tasks()
                    study.save()
                else:
                    flash('Study tasks not configured properly.', 'error')
                    return redirect(url_for('study_participation.welcome', study_id=study_id))
            except Exception as e:
                flash(f'Error generating tasks: {str(e)}', 'error')
                return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Check if tasks were generated
        if not hasattr(study, 'tasks') or not study.tasks:
            flash('Study tasks could not be generated.', 'error')
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
        # Get total tasks from IPED parameters
        total_tasks = study.iped_parameters.tasks_per_consumer 
        
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

@study_participation.route('/study/<study_id>/task-complete', methods=['POST'])
def task_complete(study_id):
    """Handle task completion data from sessionStorage"""
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
        
        # Ensure session structure is valid
        if 'study_data' not in session:
            print("No study_data in session")
            return {'error': 'Invalid session state'}, 400
        
        if 'task_ratings' not in session['study_data']:
            session['study_data']['task_ratings'] = []
            print("Initialized task_ratings in session")
        
        # Store task data in session
        if 'study_data' not in session:
            session['study_data'] = {}
        if 'task_ratings' not in session['study_data']:
            session['study_data']['task_ratings'] = []
        
        # Create new task rating data
        new_task_rating = {
            'task_number': data.get('task_number'),
            'rating': data.get('rating'),
            'timestamp': data.get('timestamp'),
            'task_start_time': data.get('task_start_time'),
            'task_end_time': data.get('task_end_time'),
            'task_duration_seconds': data.get('task_duration_seconds'),
            'task_data': data.get('task_data', {})
        }
        
        # Append to existing ratings
        session['study_data']['task_ratings'].append(new_task_rating)
        
        # Mark session as modified (CRITICAL for Flask sessions)
        session.modified = True
        
        print(f"Task {data.get('task_number')} completed with duration: {data.get('task_duration_seconds')} seconds")
        print(f"Updated session task_ratings: {session['study_data']['task_ratings']}")
        
        # Update StudyResponse object if it exists
        if 'response_id' in session:
            try:
                response = StudyResponse.objects.get(_id=session['response_id'])
                response.last_activity = datetime.utcnow()
                response.save()
                print(f"Updated task completion for response: {response._id}")
            except StudyResponse.DoesNotExist:
                print(f"Response not found: {session['response_id']}")
            except Exception as e:
                print(f"Error updating response: {str(e)}")
        else:
            print("No response_id in session")
        
        return {'success': True, 'message': 'Task data stored'}
        
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
        
        # Check if all data is available
        study_data = session.get('study_data', {})
        if not (study_data.get('personal_info') and 
                study_data.get('classification_answers') and 
                study_data.get('task_ratings')):
            print(f"Missing required data in session: {study_data}")
            print(f"Session keys: {list(session.keys())}")
            return redirect(url_for('study_participation.welcome', study_id=study_id))
        
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
                response.is_completed = True
                response.total_study_duration = total_time
                response.last_activity = completion_time
                response.completed_tasks_count = len(study_data['task_ratings'])
                
                print(f"Updated response fields - Tasks count: {response.completed_tasks_count}")
                
                # Add completed tasks with proper timing data from JavaScript
                print(f"\n--- ADDING COMPLETED TASKS ---")
                for i, task_rating in enumerate(study_data['task_ratings']):
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
                    
                    task_data = {
                        'task_id': f"task_{task_rating['task_number']}",
                        'respondent_id': session['respondent_id'],
                        'task_index': task_rating['task_number'] - 1,
                        'elements_shown_in_task': task_rating['task_data'].get('elements_shown', {}),
                        'task_start_time': task_start_time,
                        'task_completion_time': task_completion_time,
                        'task_duration_seconds': task_duration,
                        'rating_given': task_rating['rating'],
                        'rating_timestamp': safe_datetime_parse(task_rating['timestamp'])
                    }
                    
                    print(f"  Adding task data: {task_data}")
                    response.add_completed_task(task_data)
                    print(f"  Task added successfully")
                
                print(f"\n--- SAVING RESPONSE ---")
                response.update_completion_percentage()
                print(f"Completion percentage: {response.completion_percentage}")
                
                response.save()
                print(f"Response saved successfully!")
                
                print(f"Completed response: {response._id}")
                
                # Clear session data
                session.pop('study_data', None)
                session.pop('study_id', None)
                session.pop('current_step', None)
                session.pop('response_id', None)
                session.pop('session_id', None)
                session.pop('respondent_id', None)
                
                print(f"Session cleared successfully")
                
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
