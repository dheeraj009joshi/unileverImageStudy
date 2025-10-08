from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models.study import Study
from models.response import StudyResponse, TaskSession
from datetime import datetime, timedelta
import json
import csv
from io import StringIO

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard page with optimized queries."""
    # Single aggregation pipeline for all statistics and data
    pipeline = [
        {'$match': {'creator': current_user._id}},
        {'$group': {
            '_id': '$status',
            'count': {'$sum': 1},
            'studies': {'$push': {
                '_id': '$_id',
                'title': '$title',
                'status': '$status',
                'study_type': '$study_type',
                'created_at': '$created_at',
                'total_responses': '$total_responses',
                'completed_responses': '$completed_responses'
            }}
        }},
        {'$sort': {'_id': 1}}
    ]
    
    # Execute single aggregation query
    results = list(Study.objects.aggregate(*pipeline))
    
    # Process results efficiently
    status_data = {}
    total_studies = 0
    
    for result in results:
        status = result['_id']
        count = result['count']
        studies = result['studies']
        status_data[status] = {'count': count, 'studies': studies}
        total_studies += count
    
    # Get recent activity efficiently (only for active studies)
    active_study_ids = [s['_id'] for s in status_data.get('active', {}).get('studies', [])]
    recent_activity = []
    
    if active_study_ids:
        responses = list(StudyResponse.objects(
            study__in=active_study_ids
        ).only('study', 'respondent_id', 'is_completed', 'last_activity').order_by('-last_activity').limit(10))
        
        # Convert responses to activity objects for template
        for response in responses:
            if response.is_completed:
                activity_type = 'study_completed'
                description = f'Response {response.respondent_id} completed study'
            else:
                activity_type = 'response_received'
                description = f'Response {response.respondent_id} started study'
            
            recent_activity.append({
                'type': activity_type,
                'description': description,
                'last_activity': response.last_activity,
                'respondent_id': response.respondent_id
            })
    
    # Create stats object for template
    stats = {
        'total_studies': total_studies,
        'active_studies': status_data.get('active', {}).get('count', 0),
        'draft_studies': status_data.get('draft', {}).get('count', 0),
        'completed_studies': status_data.get('completed', {}).get('count', 0),
        'paused_studies': status_data.get('paused', {}).get('count', 0),
        'total_responses': StudyResponse.objects.count()  # Real-time count from database
    }
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_studies=status_data.get('active', {}).get('studies', [])[:5],
                         recent_activity=recent_activity,
                         active_studies_list=status_data.get('active', {}).get('studies', [])[:10],
                         draft_studies_list=status_data.get('draft', {}).get('studies', [])[:5])

@dashboard_bp.route('/studies')
@login_required
def studies():
    """List all user's studies with optimized queries."""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    per_page = 10
    
    # Single aggregation for status counts and studies
    pipeline = [
        {'$match': {'creator': current_user._id}},
        {'$facet': {
            'status_counts': [
                {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
            ],
            'studies': [
                {'$sort': {'created_at': -1}},
                {'$skip': (page - 1) * per_page},
                {'$limit': per_page},
                {'$project': {
                    '_id': 1,
                    'title': 1,
                    'status': 1,
                    'study_type': 1,
                    'created_at': 1,
                    'background': 1,
                    'iped_parameters': 1
                }}
            ]
        }}
    ]
    
    # Apply status filter if specified
    if status_filter != 'all':
        pipeline[0]['$match']['status'] = status_filter
    
    # Execute aggregation
    results = list(Study.objects.aggregate(*pipeline))
    
    if not results:
        return render_template('dashboard/studies.html',
                             studies=[],
                             page=page,
                             per_page=per_page,
                             total=0,
                             status_filter=status_filter,
                             status_counts={'all': 0, 'active': 0, 'draft': 0, 'paused': 0, 'completed': 0})
    
    result = results[0]
    studies = result['studies']
    
    # Process status counts
    status_counts = {'all': 0}
    for status_count in result['status_counts']:
        status = status_count['_id']
        count = status_count['count']
        status_counts[status] = count
        status_counts['all'] += count
    
    # Get total for current filter
    if status_filter == 'all':
        total = status_counts['all']
    else:
        total = status_counts.get(status_filter, 0)
    
    # Add real-time response counts for each study
    for study in studies:
        study_id = study['_id']
        # Get real-time counts from StudyResponse collection
        total_responses = StudyResponse.objects(study=study_id).count()
        completed_responses = StudyResponse.objects(study=study_id, is_completed=True).count()
        abandoned_responses = StudyResponse.objects(study=study_id, is_abandoned=True).count()
        
        # Add counts to study object
        study['total_responses'] = total_responses
        study['completed_responses'] = completed_responses
        study['abandoned_responses'] = abandoned_responses
    
    return render_template('dashboard/studies.html',
                         studies=studies,
                         page=page,
                         per_page=per_page,
                         total=total,
                         status_filter=status_filter,
                         status_counts=status_counts)

@dashboard_bp.route('/studies/<study_id>')
@login_required
def study_detail(study_id):
    """Study detail page with optimized analytics."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        flash('Study not found.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    # Get response statistics using simple queries to avoid aggregation issues
    total_responses = StudyResponse.objects(study=study._id).count()
    
    # Get all responses for this study to ensure mutual exclusivity
    all_responses = StudyResponse.objects(study=study._id)
    
    # Count responses by status - ensure mutual exclusivity
    completed_responses = 0
    abandoned_responses = 0
    in_progress_responses = 0
    
    for response in all_responses:
        if response.is_completed:
            completed_responses += 1
        elif response.is_abandoned:
            abandoned_responses += 1
        else:
            in_progress_responses += 1
    
    # Debug: Verify counts add up correctly
    calculated_total = completed_responses + abandoned_responses + in_progress_responses
    if calculated_total != total_responses:
        print(f"Warning: Response counts don't match. Total: {total_responses}, Calculated: {calculated_total}")
        print(f"Completed: {completed_responses}, Abandoned: {abandoned_responses}, In Progress: {in_progress_responses}")
    
    # Calculate completion rate safely
    if total_responses > 0:
        completion_rate = (completed_responses / total_responses) * 100
    else:
        completion_rate = 0
    
    # Calculate average task time safely
    if completed_responses > 0:
        completed_responses_objs = StudyResponse.objects(study=study._id, is_completed=True)
        total_duration = sum(r.total_study_duration for r in completed_responses_objs if r.total_study_duration)
        avg_task_time = total_duration / completed_responses
    else:
        avg_task_time = 0
    
    # Get recent responses
    recent_responses = StudyResponse.objects(study=study._id).order_by('-session_start_time').limit(10)
    recent_responses = [{
        '_id': str(r._id),
        'session_id': r.session_id,
        'respondent_id': r.respondent_id,
        'session_start_time': r.session_start_time,
        'session_end_time': r.session_end_time,
        'is_completed': r.is_completed,
        'is_abandoned': r.is_abandoned,
        'total_study_duration': r.total_study_duration,
        'completed_tasks_count': r.completed_tasks_count,
        'completion_percentage': r.completion_percentage
    } for r in recent_responses]
    
    # Create stats object for template
    stats_obj = {
        'total_responses': total_responses,
        'completed_responses': completed_responses,
        'abandoned_responses': abandoned_responses,
        'in_progress_responses': in_progress_responses,
        'completion_rate': completion_rate,
        'avg_task_time': avg_task_time
    }
    
    return render_template('dashboard/study_detail.html',
                         study=study,
                         stats=stats_obj,
                         total_responses=total_responses,
                         completed_responses=completed_responses,
                         abandoned_responses=abandoned_responses,
                         in_progress_responses=in_progress_responses,
                         completion_rate=completion_rate,
                         avg_task_time=avg_task_time,
                         recent_responses=recent_responses)

@dashboard_bp.route('/studies/<study_id>/responses')
@login_required
def study_responses(study_id):
    """Study responses page with detailed analytics."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        flash('Study not found.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    # Get response statistics using the same logic as study_detail
    total_responses = StudyResponse.objects(study=study._id).count()
    
    # Get all responses for this study to ensure mutual exclusivity
    all_responses = StudyResponse.objects(study=study._id)
    
    # Count responses by status - ensure mutual exclusivity
    completed_responses = 0
    abandoned_responses = 0
    in_progress_responses = 0
    
    for response in all_responses:
        if response.is_completed:
            completed_responses += 1
        elif response.is_abandoned:
            abandoned_responses += 1
        else:
            in_progress_responses += 1
    
    # Debug: Verify counts add up correctly
    calculated_total = completed_responses + abandoned_responses + in_progress_responses
    if calculated_total != total_responses:
        print(f"Warning: Response counts don't match. Total: {total_responses}, Calculated: {calculated_total}")
        print(f"Completed: {completed_responses}, Abandoned: {abandoned_responses}, In Progress: {in_progress_responses}")
    
    # Calculate completion rate safely
    if total_responses > 0:
        completion_rate = (completed_responses / total_responses) * 100
    else:
        completion_rate = 0
    
    # Calculate average task time safely
    if completed_responses > 0:
        completed_responses_objs = StudyResponse.objects(study=study._id, is_completed=True)
        total_duration = sum(r.total_study_duration for r in completed_responses_objs if r.total_study_duration)
        avg_task_time = total_duration / completed_responses
    else:
        avg_task_time = 0
    
    # Create stats object for template
    stats_obj = {
        'total_responses': total_responses,
        'completed_responses': completed_responses,
        'abandoned_responses': abandoned_responses,
        'in_progress_responses': in_progress_responses,
        'completion_rate': completion_rate,
        'avg_task_time': avg_task_time
    }
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    responses = StudyResponse.objects(study=study).order_by('-created_at')
    total = responses.count()
    
    # Ensure total is a valid number
    if total is None:
        total = 0
    
    # Pagination
    responses = responses.skip((page - 1) * per_page).limit(per_page)
    
    return render_template('dashboard/study_responses.html',
                         study=study,
                         responses=responses,
                         stats=stats_obj,
                         total_responses=total_responses,
                         completed_responses=completed_responses,
                         abandoned_responses=abandoned_responses,
                         in_progress_responses=in_progress_responses,
                         completion_rate=completion_rate,
                         avg_task_time=avg_task_time,
                         page=page,
                         per_page=per_page,
                         total=total)

@dashboard_bp.route('/studies/<study_id>/analytics')
@login_required
def study_analytics(study_id):
    """Study analytics page with detailed timing data."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        flash('Study not found.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    # Get all completed responses
    completed_responses = StudyResponse.objects(study=study, is_completed=True)
    
    # Task timing analytics
    task_times = []
    element_interactions = {}
    
    for response in completed_responses:
        for task in response.completed_tasks:
            task_times.append(task.task_duration_seconds)
            
            # Aggregate element interactions
            for interaction in task.element_interactions:
                element_id = interaction.element_id
                if element_id not in element_interactions:
                    element_interactions[element_id] = {
                        'total_view_time': 0,
                        'total_hover_count': 0,
                        'total_click_count': 0,
                        'interaction_count': 0
                    }
                
                element_interactions[element_id]['total_view_time'] += interaction.view_time_seconds
                element_interactions[element_id]['total_hover_count'] += interaction.hover_count
                element_interactions[element_id]['total_click_count'] += interaction.click_count
                element_interactions[element_id]['interaction_count'] += 1
    
    # Calculate timing statistics
    if task_times:
        avg_task_time = sum(task_times) / len(task_times)
        min_task_time = min(task_times)
        max_task_time = max(task_times)
        sorted_times = sorted(task_times)
        median_task_time = sorted_times[len(sorted_times) // 2]
    else:
        avg_task_time = min_task_time = max_task_time = median_task_time = 0
    
    # Completion time trends
    completion_trends = []
    for i in range(7):  # Last 7 days
        date = datetime.utcnow() - timedelta(days=i)
        day_responses = completed_responses.filter(
            session_end_time__gte=date.replace(hour=0, minute=0, second=0, microsecond=0),
            session_end_time__lt=date.replace(hour=23, minute=59, second=59, microsecond=999999)
        )
        completion_trends.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': day_responses.count()
        })
    
    completion_trends.reverse()
    
    return render_template('dashboard/study_analytics.html',
                         study=study,
                         avg_task_time=avg_task_time,
                         min_task_time=min_task_time,
                         max_task_time=max_task_time,
                         median_task_time=median_task_time,
                         element_interactions=element_interactions,
                         completion_trends=completion_trends)

@dashboard_bp.route('/studies/<study_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_study(study_id):
    """Edit study details."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        flash('Study not found.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    if study.status == 'active':
        flash('Cannot edit active studies.', 'warning')
        return redirect(url_for('dashboard.study_detail', study_id=study._id))
    
    if request.method == 'POST':
        try:
            # Update study details
            study.title = request.form.get('title', study.title)
            study.background = request.form.get('background', study.background)
            study.main_question = request.form.get('main_question', study.main_question)
            study.orientation_text = request.form.get('orientation_text', study.orientation_text)
            study.updated_at = datetime.utcnow()
            study.save()
            
            flash('Study updated successfully!', 'success')
            return redirect(url_for('dashboard.study_detail', study_id=study._id))
            
        except Exception as e:
            flash(f'Error updating study: {str(e)}', 'error')
    
    return render_template('dashboard/edit_study.html', study=study)

@dashboard_bp.route('/studies/<study_id>/status', methods=['POST'])
@login_required
def change_study_status(study_id):
    """Change study status."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    new_status = request.json.get('status')
    if new_status not in ['draft', 'active', 'paused', 'completed']:
        return jsonify({'error': 'Invalid status'}), 400
    
    try:
        study.status = new_status
        if new_status == 'active' and not study.launched_at:
            study.launched_at = datetime.utcnow()
        elif new_status == 'completed':
            study.completed_at = datetime.utcnow()
        
        study.updated_at = datetime.utcnow()
        study.save()
        
        return jsonify({'success': True, 'status': new_status})
        #vdvv
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/test-browser-connection')
def test_browser_connection():
    print("🧪 BROWSER CONNECTION TEST CALLED!")
    return "Browser connection test successful!"

@dashboard_bp.route('/studies/<study_id>/export-debug')
def export_debug(study_id):
    print("🔧 EXPORT DEBUG ROUTE CALLED!")
    print(f"🔧 Study ID: {study_id}")
    return f"Export debug called for study: {study_id}"

@dashboard_bp.route('/studies/<study_id>/export-task-matrix')
@login_required
def export_task_matrix(study_id):
    """Export only the task matrix (0/1 data) for all tasks across all respondents."""
    print("=" * 80)
    print("🚀🚀🚀 TASK MATRIX EXPORT CALLED 🚀🚀🚀")
    print(f"🚀 Study ID: {study_id}")
    print(f"🚀 User: {getattr(current_user, 'username', 'Anonymous') if current_user and current_user.is_authenticated else 'Anonymous'}")
    print("=" * 80)
    
    # Get the study
    study = Study.objects(_id=study_id, creator=current_user).first()
    
    if not study:
        flash('Study not found or you do not have permission to access it.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    print(f"🚀 Study found: {study.title}")
    print(f"🚀 Study type: {study.study_type}")
    
    # Create CSV response
    output = StringIO()
    writer = csv.writer(output)
    
    # Generate headers and mapping for both grid and layer studies
    header_row = ['Panelist', 'Task']
    key_to_descriptive = {}
    
    if study.study_type == 'grid' and study.grid_categories:
        print(f"🚀 Processing GRID study with {len(study.grid_categories)} categories")
        
        # Get actual keys from task data first (prefer StudyPanelistTasks)
        actual_keys = set()
        panelist_iter = []
        try:
            from models.study_task import StudyPanelistTasks
            panel_docs = StudyPanelistTasks.objects(draft=study)
            if panel_docs:
                panelist_iter = [(doc.panelist_id, doc.tasks) for doc in panel_docs]
                print(f"🚀 Loaded {len(panel_docs)} panelist task documents from StudyPanelistTasks")
            else:
                print("🚀 No StudyPanelistTasks found, trying legacy study.tasks")
                if hasattr(study, 'tasks') and study.tasks:
                    panelist_iter = list(study.tasks.items())
        except Exception as e:
            print(f"WARN: Could not load StudyPanelistTasks: {e}")
            if hasattr(study, 'tasks') and study.tasks:
                panelist_iter = list(study.tasks.items())
        for panelist_id, panelist_tasks in panelist_iter:
                print(f"🚀 Panelist {panelist_id} tasks type: {type(panelist_tasks)}")
                print(f"🚀 Panelist {panelist_id} tasks length: {len(panelist_tasks) if panelist_tasks else 'None'}")
                
                if panelist_tasks:
                    for task_index, task in enumerate(panelist_tasks[:2]):  # Only check first 2 tasks
                        print(f"🚀 Task {task_index} type: {type(task)}")
                        print(f"🚀 Task {task_index} content: {task}")
                        
                        # Try different ways to access elements_shown
                        elements_shown = None
                        if hasattr(task, 'elements_shown'):
                            elements_shown = getattr(task, 'elements_shown', {})
                            print(f"🚀 Task {task_index} elements_shown (attr): {elements_shown}")
                        elif isinstance(task, dict) and 'elements_shown' in task:
                            elements_shown = task['elements_shown']
                            print(f"🚀 Task {task_index} elements_shown (dict): {elements_shown}")
                        else:
                            print(f"🚀 Task {task_index} no elements_shown found")
                        
                        if elements_shown:
                            actual_keys.update(elements_shown.keys())
                            print(f"🚀 Task {task_index} keys: {list(elements_shown.keys())}")
                    break
        else:
            print("🚀 Study has no tasks or tasks is None")
        
        print(f"🚀 Found actual keys in tasks: {sorted(actual_keys)}")
        
        # Create mapping from actual keys to descriptive names
        print(f"🚀 Available categories: {[cat.name for cat in study.grid_categories]}")
        for actual_key in sorted(actual_keys):
            # Parse actual_key format: "CategoryName_ElementIndex" (e.g., "Color_1", "Shape_2")
            print(f"🚀 Processing key: {actual_key}")
            if '_' in actual_key:
                category_name, element_index_str = actual_key.rsplit('_', 1)
                print(f"🚀 Parsed: category_name={category_name}, element_index_str={element_index_str}")
                try:
                    element_index = int(element_index_str) - 1
                    print(f"🚀 Element index: {element_index}")
                    
                    # Find the corresponding category and element
                    found_category = False
                    for category in study.grid_categories:
                        print(f"🚀 Checking category: {category.name} (has {len(category.elements)} elements)")
                        if category.name == category_name and element_index < len(category.elements):
                            element = category.elements[element_index]
                            element_name = getattr(element, 'name', f'Element_{element_index + 1}')
                            descriptive_name = f"{category_name}_{element_name}_{element_index + 1}"
                            key_to_descriptive[actual_key] = descriptive_name
                            header_row.append(descriptive_name)
                            print(f"🚀 Mapped {actual_key} -> {descriptive_name}")
                            found_category = True
                            break
                    
                    if not found_category:
                        # Fallback if category not found
                        print(f"🚀 Category {category_name} not found or element index {element_index} out of range")
                        key_to_descriptive[actual_key] = actual_key
                        header_row.append(actual_key)
                except ValueError as e:
                    print(f"🚀 ValueError parsing {element_index_str}: {e}")
                    key_to_descriptive[actual_key] = actual_key
                    header_row.append(actual_key)
            else:
                print(f"🚀 Key {actual_key} doesn't contain underscore")
                key_to_descriptive[actual_key] = actual_key
                header_row.append(actual_key)
            
    elif study.study_type == 'layer' and study.study_layers:
        print(f"🚀 Processing LAYER study with {len(study.study_layers)} layers")
        
        # Get actual keys from task data first (prefer StudyPanelistTasks)
        actual_keys = set()
        panelist_iter = []
        try:
            from models.study_task import StudyPanelistTasks
            panel_docs = StudyPanelistTasks.objects(draft=study)
            if panel_docs:
                panelist_iter = [(doc.panelist_id, doc.tasks) for doc in panel_docs]
        except Exception as e:
            print(f"WARN: Could not load StudyPanelistTasks: {e}")
        if not panelist_iter and hasattr(study, 'tasks') and study.tasks:
            panelist_iter = list(study.tasks.items())
        for panelist_id, panelist_tasks in panelist_iter:
                print(f"🚀 Panelist {panelist_id} tasks type: {type(panelist_tasks)}")
                print(f"🚀 Panelist {panelist_id} tasks length: {len(panelist_tasks) if panelist_tasks else 'None'}")
                
                if panelist_tasks:
                    for task_index, task in enumerate(panelist_tasks[:2]):  # Only check first 2 tasks
                        print(f"🚀 Task {task_index} type: {type(task)}")
                        print(f"🚀 Task {task_index} content: {task}")
                        
                        # Try different ways to access elements_shown
                        elements_shown = None
                        if hasattr(task, 'elements_shown'):
                            elements_shown = getattr(task, 'elements_shown', {})
                            print(f"🚀 Task {task_index} elements_shown (attr): {elements_shown}")
                        elif isinstance(task, dict) and 'elements_shown' in task:
                            elements_shown = task['elements_shown']
                            print(f"🚀 Task {task_index} elements_shown (dict): {elements_shown}")
                        else:
                            print(f"🚀 Task {task_index} no elements_shown found")
                        
                        if elements_shown:
                            # Filter out keys ending with '_content'
                            for key in elements_shown.keys():
                                if not key.endswith('_content'):
                                    actual_keys.add(key)
                            print(f"🚀 Task {task_index} keys: {list(elements_shown.keys())}")
                    break
        else:
            print("🚀 Study has no tasks or tasks is None")
        
        print(f"🚀 Found actual layer keys in tasks: {sorted(actual_keys)}")
        
        # Create mapping from actual layer keys to descriptive names
        for key in sorted(actual_keys):
            # Parse key format: "LayerName_ElementIndex" (e.g., "Background_1", "Foreground_2")
            print(f"🚀 Processing layer key: {key}")
            if '_' in key:
                layer_name, element_index_str = key.rsplit('_', 1)
                print(f"🚀 Parsed: layer_name={layer_name}, element_index_str={element_index_str}")
                try:
                    element_index = int(element_index_str) - 1
                    print(f"🚀 Element index: {element_index}")
                    
                    # Find the corresponding layer and element in study_layers
                    found_layer = False
                    for study_layer in study.study_layers:
                        print(f"🚀 Checking layer: {study_layer.name} (has {len(study_layer.images)} images)")
                        if study_layer.name == layer_name and element_index < len(study_layer.images):
                            element = study_layer.images[element_index]
                            element_name = element.name if hasattr(element, 'name') and element.name else f'Element_{element_index + 1}'
                            descriptive_name = f'{layer_name}_{element_name}'
                            key_to_descriptive[key] = descriptive_name
                            header_row.append(descriptive_name)
                            print(f"🚀 Mapped {key} -> {descriptive_name}")
                            found_layer = True
                            break
                    
                    if not found_layer:
                        # Fallback if layer not found
                        print(f"🚀 Layer {layer_name} not found or element index {element_index} out of range")
                        key_to_descriptive[key] = key
                        header_row.append(key)
                except ValueError as e:
                    print(f"🚀 ValueError parsing {element_index_str}: {e}")
                    key_to_descriptive[key] = key
                    header_row.append(key)
            else:
                print(f"🚀 Key {key} doesn't contain underscore")
                key_to_descriptive[key] = key
                header_row.append(key)
    
    # Write header
    writer.writerow(header_row)
    print(f"🚀 Header row: {header_row}")
    
    # Load task data once and cache it
    print("🔄 Loading task data from StudyPanelistTasks...")
    panelist_tasks_cache = {}
    try:
        from models.study_task import StudyPanelistTasks
        panel_docs = StudyPanelistTasks.objects(draft=study)
        if panel_docs:
            for doc in panel_docs:
                panelist_tasks_cache[doc.panelist_id] = doc.tasks
            print(f"✅ Loaded {len(panel_docs)} panelist task documents")
    except Exception as e:
        print(f"WARN: Could not load StudyPanelistTasks: {e}")
    
    # Fallback to legacy data if needed
    if not panelist_tasks_cache and hasattr(study, 'tasks') and study.tasks:
        print("🔄 Falling back to legacy study.tasks...")
        panelist_tasks_cache = dict(study.tasks)
        print(f"✅ Loaded {len(panelist_tasks_cache)} panelists from legacy data")
    
    if panelist_tasks_cache:
        print(f"🔄 Processing {len(panelist_tasks_cache)} panelists...")
        for panelist_id, panelist_tasks in panelist_tasks_cache.items():
            if not panelist_tasks:
                continue
                
            for task_index, task in enumerate(panelist_tasks):
                row_data = [panelist_id, task_index + 1]  # Panelist ID and Task number
                
                # Try new structure first (elements_shown), then fallback to old structure
                elements_shown = {}
                if isinstance(task, dict) and 'elements_shown' in task:
                    elements_shown = task['elements_shown']
                    print(f"🚀 Task {task_index + 1} elements_shown (dict): {elements_shown}")
                elif hasattr(task, 'elements_shown'):
                    elements_shown = getattr(task, 'elements_shown', {})
                    print(f"🚀 Task {task_index + 1} elements_shown (attr): {elements_shown}")
                else:
                    print(f"🚀 Task {task_index + 1} no elements_shown found, task type: {type(task)}")
                    print(f"🚀 Task {task_index + 1} task content: {task}")
                
                print(f"🚀 Task {task_index + 1} elements_shown keys: {list(elements_shown.keys()) if elements_shown else 'EMPTY'}")
                print(f"🚀 Available key mappings: {key_to_descriptive}")
                
                # Add 0/1 values for each element in the header order
                for i in range(2, len(header_row)):  # Skip Panelist and Task columns
                    column_name = header_row[i]
                    
                    # Find the corresponding key for this column
                    element_key = None
                    for key, desc_name in key_to_descriptive.items():
                        if desc_name == column_name:
                            element_key = key
                            break
                    print(key)
                    # Get the value (1 if element was shown, 0 if not)
                    value = elements_shown.get(element_key, 0) if element_key else 0
                    print(f"🚀 Column: {column_name}, Key: {element_key}, Value: {value}")
                    row_data.append(value)
                
                writer.writerow(row_data)
                print(f"🚀 Row written: {row_data}")
                
                # Process all tasks
                pass
    
    # Prepare response
    output.seek(0)
    
    # Generate filename
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    filename = f"{study.title}_task_matrix_{timestamp}.csv"
    
    response = current_app.response_class(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    
    print(f"🚀 Task matrix export completed: {filename}")
    return response

@dashboard_bp.route('/studies/<study_id>/export')
# @login_required  # Temporarily disabled for debugging
def export_study(study_id):
    """Export study data in comprehensive CSV format."""
    print("=" * 80)
    print("🚀🚀🚀 EXPORT FUNCTION CALLED FROM BROWSER 🚀🚀🚀")
    print(f"🚀 Study ID: {study_id}")
    print(f"🚀 User: {getattr(current_user, 'username', 'Anonymous') if current_user and current_user.is_authenticated else 'Anonymous'}")
    print("=" * 80)
    
    # Get the type parameter from query string
    export_type = request.args.get('type', 'csv')
    print(f"🚀 Export type: {export_type}")
    
    # Check if user has permission to access this study
    study = Study.objects(_id=study_id).first()  # Temporarily allow any user for debugging
    print(f"🚀 Study found: {study.title if study else 'None'}")
    print(f"🚀 Study type: {study.study_type if study else 'None'}")
    
    if not study:
        print("❌ Study not found or no permission")
        flash('Study not found or you do not have permission to access it.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    if export_type == 'csv':
        # Get all completed responses for this study
        responses = StudyResponse.objects(study=study, is_completed=True)
        # Convert to list for easier processing
        responses = list(responses)
        
        # Debug: Check all responses (completed and abandoned)
        all_responses = StudyResponse.objects(study=study)
        for resp in all_responses[:3]:  # Show first 3 responses
            if resp.completed_tasks:
                first_task = resp.completed_tasks[0]
        
        if not responses:
            flash('No completed responses found for export.', 'warning')
            return redirect(url_for('dashboard.study_responses', study_id=study_id))
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Create simplified header structure
        header_row = []
        
        # Panelist (Respondent) info
        header_row.append('Panelist')
        
        # Classification questions columns (with option numbers)
        if study.classification_questions:
            for question in study.classification_questions:
                header_row.append(f'{question.question_text}')
        
        # Personal info columns
        header_row.extend(['Gender', 'Age'])
        
        # Task number
        header_row.append('Task')
        
        # Generate layer mapping data for layer studies (needed for both header and data)
        layer_keys = []
        key_to_descriptive = {}
        if study.study_type == 'layer' and study.study_layers:
            # Use cached task data if available, otherwise load once
            if 'panelist_tasks_cache' not in locals():
                panelist_tasks_cache = {}
                try:
                    from models.study_task import StudyPanelistTasks
                    panel_docs = StudyPanelistTasks.objects(draft=study)
                    if panel_docs:
                        for doc in panel_docs:
                            panelist_tasks_cache[doc.panelist_id] = doc.tasks
                except Exception as e:
                    print(f"WARN: Could not load StudyPanelistTasks for layer key extraction: {e}")
            
            # Extract layer keys from cached data
            for panelist_id, panelist_tasks in panelist_tasks_cache.items():
                if panelist_tasks:
                    for task in panelist_tasks[:1]:  # Check first task only
                        if isinstance(task, dict) and 'elements_shown' in task:
                            elements_shown = task['elements_shown']
                            for key in elements_shown.keys():
                                if not key.endswith('_content'):
                                    if key not in layer_keys:
                                        layer_keys.append(key)
                            break
                    if layer_keys:
                        break
            
            # Fallback to response data if StudyPanelistTasks not available
            if not layer_keys:
                for response in responses:
                    if response.completed_tasks:
                        for task in response.completed_tasks:
                            elements_shown = getattr(task, 'elements_shown_in_task', {})
                            if elements_shown:
                                # Get all keys that don't end with '_content' (these are the actual layer keys)
                                for key in elements_shown.keys():
                                    if not key.endswith('_content'):
                                        if key not in layer_keys:
                                            layer_keys.append(key)
                                break
                        if layer_keys:
                            break
            
            # Create mapping from actual layer keys to descriptive names
            for key in layer_keys:
                # Parse key format: "LayerName_ElementIndex" (e.g., "Background_1", "Foreground_2")
                if '_' in key:
                    layer_name, element_index_str = key.rsplit('_', 1)
                    try:
                        element_index = int(element_index_str) - 1  # Convert to 0-based index
                        
                        # Find the corresponding layer and element in study.study_layers
                        for study_layer in study.study_layers:
                            if study_layer.name == layer_name and element_index < len(study_layer.images):
                                element = study_layer.images[element_index]
                                # Create descriptive name: "LayerName_ElementName"
                                element_name = element.name if hasattr(element, 'name') and element.name else f'Element_{element_index + 1}'
                                descriptive_name = f'{layer_name}_{element_name}'
                                key_to_descriptive[key] = descriptive_name
                                break
                        else:
                            # Fallback if layer/element not found
                            key_to_descriptive[key] = key
                    except ValueError:
                        # Fallback if parsing fails
                        key_to_descriptive[key] = key
                else:
                    # Fallback if key doesn't match expected format
                    key_to_descriptive[key] = key

        # Element/Layer columns (same for all tasks)
        if study.study_type == 'grid' and (study.grid_categories or study.elements):
            # For grid studies: get column names from grid structure
            grid_columns = []
            
            if study.grid_categories:

                # New grid structure: create descriptive column names from grid_categories
                # Map simplified keys (a_1, b_2, etc.) to actual category and element names
                
                # First, create a mapping from actual task data keys to descriptive names
                key_to_descriptive = {}
                category_index = 0
                
                for category in study.grid_categories:
                    # Try to get a meaningful category name
                    raw_name = getattr(category, 'name', f'Category_{category_index + 1}')
                    description = getattr(category, 'description', '')
                    # Use actual name if it's not generic, otherwise use description or fallback
                    if raw_name and not raw_name.startswith('Category '):
                        category_name = raw_name
                    elif description and description.strip():
                        category_name = description.strip()
                    else:
                        category_name = f'Category_{category_index + 1}'
                    
                    elements = getattr(category, 'elements', [])
                    
                    for element_index, element in enumerate(elements):
                        element_name = getattr(element, 'name', f'Element_{element_index + 1}')
                        # Create descriptive name using CategoryName_ElementName_ElementIndex format
                        descriptive_name = f"{category_name}_{element_name}_{element_index + 1}"
                        
                        # Create the actual key that matches task data format
                        # Task data uses format: CategoryName_ElementIndex (e.g., "Color_1", "Material_2")
                        actual_key = f"{category_name}_{element_index + 1}"
                        
                        key_to_descriptive[actual_key] = descriptive_name
                    
                    category_index += 1
                
                # Get the actual keys from task data and map them to descriptive names
                actual_keys = set()
                
                # Use cached task data if available, otherwise load once
                if 'panelist_tasks_cache' not in locals():
                    panelist_tasks_cache = {}
                    try:
                        from models.study_task import StudyPanelistTasks
                        panel_docs = StudyPanelistTasks.objects(draft=study)
                        if panel_docs:
                            for doc in panel_docs:
                                panelist_tasks_cache[doc.panelist_id] = doc.tasks
                    except Exception as e:
                        print(f"WARN: Could not load StudyPanelistTasks for key extraction: {e}")
                
                # Extract keys from cached data
                for panelist_id, panelist_tasks in panelist_tasks_cache.items():
                    if panelist_tasks:
                        for task in panelist_tasks[:1]:  # Check first task only
                            if isinstance(task, dict) and 'elements_shown' in task:
                                elements_shown = task['elements_shown']
                                for key in elements_shown.keys():
                                    if not key.endswith('_content'):
                                        actual_keys.add(key)
                                break
                        if actual_keys:
                            break
                
                # Fallback to response data if StudyPanelistTasks not available
                if not actual_keys:
                    for response in responses:
                        if response.completed_tasks:
                            for task in response.completed_tasks:
                                elements_shown = getattr(task, 'elements_shown_in_task', {})
                                if elements_shown:
                                    for key in elements_shown.keys():
                                        if not key.endswith('_content'):
                                            actual_keys.add(key)
                                    break
                            if actual_keys:
                                break
                
                # Create grid_columns using descriptive names for keys that exist in task data
                for key in sorted(actual_keys):
                    if key in key_to_descriptive:
                        grid_columns.append(key_to_descriptive[key])
                    else:
                        # Handle legacy format (E1, E2, etc.)
                        if key.startswith('E') and key[1:].isdigit():
                            # Legacy format: create descriptive name based on legacy elements
                            element_index = int(key[1:]) - 1  # E1 -> index 0, E2 -> index 1, etc.
                            if element_index < len(study.elements):
                                element = study.elements[element_index]
                                element_name = getattr(element, 'name', f'Element_{element_index + 1}')
                                # Create shorter, more meaningful name
                                clean_name = element_name.replace('_', ' ').replace('-', ' ')
                                if len(clean_name) > 20:
                                    clean_name = clean_name[:20] + '...'
                                grid_columns.append(f'Element_{element_index + 1}_{clean_name}')
            else:
                # Legacy grid structure: dynamically get column names from elements_shown_in_task
                for response in responses:
                    if response.completed_tasks:
                        for task in response.completed_tasks:
                            elements_shown = getattr(task, 'elements_shown_in_task', {})
                            if elements_shown:
                                # Get all keys that don't end with '_content' (ignore image URL keys)
                                for key in elements_shown.keys():
                                    if not key.endswith('_content'):
                                        if key not in grid_columns:
                                            grid_columns.append(key)
                                break
                        if grid_columns:
                            break
            
            # Sort the grid columns for consistent ordering
            grid_columns.sort()
            
            # Add the dynamic grid columns to header
            for column in grid_columns:
                header_row.append(column)
            
            header_row.extend(['Rating', 'ResponseTime'])
        elif study.study_type == 'layer' and study.study_layers:
            # For layer studies: use pre-generated descriptive column names
            
            # Create sorted list of descriptive column names using the pre-generated mapping
            layer_columns = []
            for key in sorted(layer_keys):
                descriptive_name = key_to_descriptive[key]
                layer_columns.append(descriptive_name)
            
            
            # Add the descriptive layer columns to header
            for column in layer_columns:
                header_row.append(column)
            
            header_row.extend(['Rating', 'ResponseTime'])
        
        # Write header
        writer.writerow(header_row)
        
        # Write data rows - one row per task
        total_rows = 0
        print(f"🔄 Processing {len(responses)} responses for export...")
        
        for response_idx, response in enumerate(responses):
            if response_idx % 10 == 0:  # Progress every 10 responses
                print(f"🔄 Processing response {response_idx + 1}/{len(responses)}...")
            # Get classification answers once per response
            classification_answers = {}
            if study.classification_questions:
                for question in study.classification_questions:
                    answer = next((a.answer for a in response.classification_answers 
                                 if a.question_id == question.question_id), '')
                    # Store the answer text, not just 'yes'
                    classification_answers[question.question_id] = answer
            
            # Task-specific data - create one row per task
            completed_tasks = response.completed_tasks if hasattr(response, 'completed_tasks') else []
            
            # Use the ACTUAL number of completed tasks instead of total_tasks_assigned
            # This prevents empty rows from old responses that were created with incorrect task counts
            completed_tasks_count = len(completed_tasks) if completed_tasks else 0
            max_tasks = completed_tasks_count
            
            print(f"DEBUG: Response {response.respondent_id}: total_tasks_assigned={response.total_tasks_assigned}, completed_tasks_count={completed_tasks_count}, using max_tasks={max_tasks}")
            
            for task_num in range(1, max_tasks + 1):
                task_data = next((task for task in completed_tasks 
                                if getattr(task, 'task_index', None) == task_num - 1), None)
                
                if not task_data:
                    print(f"DEBUG: No task data found for task {task_num} (task_index {task_num - 1})")
                    print(f"DEBUG: Available task indices: {[getattr(task, 'task_index', 'NO_INDEX') for task in completed_tasks]}")
                    continue
                
                # Debug: Check what fields are available in task_data
                print(f"DEBUG: Task {task_num} data fields: {[attr for attr in dir(task_data) if not attr.startswith('_')]}")
                print(f"DEBUG: Task {task_num} elements_shown: {getattr(task_data, 'elements_shown', 'NOT_FOUND')}")
                print(f"DEBUG: Task {task_num} elements_shown_in_task: {getattr(task_data, 'elements_shown_in_task', 'NOT_FOUND')}")
                print(f"DEBUG: Task {task_num} elements_shown_content: {getattr(task_data, 'elements_shown_content', 'NOT_FOUND')}")
                
                # Check if this is a grid study and has the right data
                if study.study_type == 'grid':
                    print(f"DEBUG: This is a GRID study, checking grid data...")
                    if hasattr(study, 'grid_categories') and study.grid_categories:
                        print(f"DEBUG: Study has {len(study.grid_categories)} grid categories")
                        for i, cat in enumerate(study.grid_categories):
                            print(f"DEBUG: Category {i}: name='{getattr(cat, 'name', 'NO_NAME')}', elements={len(getattr(cat, 'elements', []))}")
                    else:
                        print(f"DEBUG: Study has NO grid_categories, checking legacy elements...")
                        print(f"DEBUG: Legacy elements count: {len(study.elements) if study.elements else 0}")
                else:
                    print(f"DEBUG: This is NOT a grid study, type: {study.study_type}")
                
                row_data = []
                
                # Panelist (Respondent ID)
                row_data.append(response.respondent_id)
                
                # Classification answers (option numbers)
                if study.classification_questions:
                    for question in study.classification_questions:
                        row_data.append(classification_answers.get(question.question_id, ''))
                
                # Personal info (Gender and Age)
                gender = getattr(response, 'personal_info', {}).get('gender', '') if hasattr(response, 'personal_info') else ''
                age = getattr(response, 'personal_info', {}).get('age', '') if hasattr(response, 'personal_info') else ''
                row_data.extend([gender, age])
                
                # Task number
                row_data.append(task_num)
                
                if task_data:
                    # Element/Layer visibility for this task
                    if study.study_type == 'grid' and (study.grid_categories or study.elements):
                        # Try new structure first (elements_shown), then fallback to old structure
                        elements_shown = {}
                        if isinstance(task_data, dict) and 'elements_shown' in task_data:
                            elements_shown = task_data['elements_shown']
                        else:
                            elements_shown = getattr(task_data, 'elements_shown_in_task', {})
                        print(f"DEBUG: Task {task_num} elements_shown: {elements_shown}")
                        print(f"DEBUG: Task {task_num} elements_shown type: {type(elements_shown)}")
                        print(f"DEBUG: Task {task_num} elements_shown keys: {list(elements_shown.keys()) if elements_shown else 'None'}")
                        
                        if study.grid_categories:
                            # New grid structure: use mapping from descriptive names to simplified keys
                            # Create the same mapping as in header generation
                            key_to_descriptive = {}
                            category_index = 0
                            
                            for category in study.grid_categories:
                                # Try to get a meaningful category name
                                raw_name = getattr(category, 'name', f'Category_{category_index + 1}')
                                description = getattr(category, 'description', '')
                                # Use actual name if it's not generic, otherwise use description or fallback
                                if raw_name and not raw_name.startswith('Category '):
                                    category_name = raw_name
                                elif description and description.strip():
                                    category_name = description.strip()
                                else:
                                    category_name = f'Category_{category_index + 1}'
                                
                                elements = getattr(category, 'elements', [])
                                
                                for element_index, element in enumerate(elements):
                                    element_name = getattr(element, 'name', f'Element_{element_index + 1}')
                                    descriptive_name = f"{category_name}_{element_name}_{element_index + 1}"
                                    
                                    # Create the actual key that matches task data format
                                    actual_key = f"{category_name}_{element_index + 1}"
                                    key_to_descriptive[actual_key] = descriptive_name
                                
                                category_index += 1
                            
                            # Create reverse mapping: descriptive_name -> actual_key
                            descriptive_to_key = {v: k for k, v in key_to_descriptive.items()}
                            
                            # For grid studies: use dynamic columns from header
                            for column_index, column in enumerate(grid_columns):
                                # Get the actual key for this descriptive column name
                                actual_key = descriptive_to_key.get(column, None)
                                
                                # Get the value using the actual key
                                is_visible = 0
                                if actual_key and actual_key in elements_shown:
                                    is_visible = elements_shown[actual_key]
                                
                                row_data.append(is_visible)
                        else:
                            # Legacy grid structure: use columns directly
                            for column in grid_columns:
                                # Get the value for this column (1 if visible, 0 if not)
                                is_visible = elements_shown.get(column, 0)
                                row_data.append(is_visible)
                                print(row_data)
                        
                        # Add rating and response time
                        rating = getattr(task_data, 'rating_given', '')
                        response_time = getattr(task_data, 'task_duration_seconds', '')
                        row_data.extend([rating, response_time])
                        
                    elif study.study_type == 'layer' and study.study_layers:
                        # Try new structure first (elements_shown), then fallback to old structure
                        elements_shown_in_task = {}
                        if isinstance(task_data, dict) and 'elements_shown' in task_data:
                            elements_shown_in_task = task_data['elements_shown']
                        else:
                            elements_shown_in_task = getattr(task_data, 'elements_shown_in_task', {})
                        
                        # For layer studies: use actual layer keys to look up values, but write descriptive column names
                        for i, column in enumerate(layer_columns):
                            # Get the actual layer key for this descriptive column
                            layer_key = sorted(layer_keys)[i] if i < len(layer_keys) else column
                            
                            # Get the value using the actual layer key (1 if visible, 0 if not)
                            element_visible = elements_shown_in_task.get(layer_key, 0)
                            row_data.append(element_visible)
                        
                        # Add rating and response time
                        rating = getattr(task_data, 'rating_given', '')
                        response_time = getattr(task_data, 'task_duration_seconds', '')
                        row_data.extend([rating, response_time])
                else:
                    # No data for this task, fill with empty values
                    if study.study_type == 'grid' and (study.elements or study.grid_categories):
                        empty_count = len(grid_columns) + 2  # dynamic columns + rating + response time
                    elif study.study_type == 'layer' and study.study_layers:
                        # Count total elements across all layers using dynamic columns
                        empty_count = len(layer_columns) + 2  # dynamic columns + rating + response time
                    else:
                        empty_count = 0
                    
                    row_data.extend([''] * empty_count)
                
                writer.writerow(row_data)
                total_rows += 1
        
        print(f"✅ Export completed! Generated {total_rows} rows of data")
        output.seek(0)
        
        # Generate descriptive filename with study details
        study_name = study.title.replace(' ', '_').replace('/', '_').replace('\\', '_')
        study_type = study.study_type.upper()
        response_count = len(responses)
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H%M')
        filename = f"{study_name}_{study_type}_{response_count}_responses_{current_date}_{current_time}.csv"
        
        response = current_app.response_class(
            output.getvalue(),
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    elif export_type == 'json':
        # Export as JSON (keep existing functionality)
        study_data = study.to_dict()
        
        # Add responses data
        responses = StudyResponse.objects(study=study)
        study_data['responses'] = [r.to_dict() for r in responses]
        
        response = current_app.response_class(
            json.dumps(study_data, indent=2, default=str),
            status=200,
            mimetype='application/json'
        )
        response.headers['Content-Disposition'] = f'attachment; filename=study_{study._id}.json'
        return response
        
    else:
        flash('Invalid export type.', 'error')
        return redirect(url_for('dashboard.study_detail', study_id=study_id))

@dashboard_bp.route('/responses/<response_id>/export')
@login_required
def export_individual_response(response_id):
    """Export individual response data in CSV format."""
    try:
        # Find the response and ensure it belongs to a study created by current user
        response = StudyResponse.objects(_id=response_id).first()
        if not response:
            flash('Response not found.', 'error')
            return redirect(url_for('dashboard.studies'))
        
        study = Study.objects(_id=response.study._id, creator=current_user).first()
        if not study:
            flash('Access denied.', 'error')
            return redirect(url_for('dashboard.studies'))
        
        # Create CSV output
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        header_row = [
            'Response ID', 'Session ID', 'Respondent ID', 'Study ID', 'Study Title',
            'Session Start Time', 'Session End Time', 'Total Duration (seconds)',
            'Completion Status', 'Tasks Completed', 'Total Tasks Assigned',
            'Completion Percentage', 'Is Abandoned', 'Abandonment Reason'
        ]
        
        # Add classification questions
        if study.classification_questions:
            for question in study.classification_questions:
                header_row.append(f'Classification_{question.question_id}_{question.question_text}')
        
        # Add personal info
        header_row.extend(['Personal_Birth_Date', 'Personal_Age', 'Personal_Gender'])
        
        # Add task columns
        if response.completed_tasks:
            for i, task in enumerate(response.completed_tasks):
                task_prefix = f'Task_{i+1}'
                header_row.extend([
                    f'{task_prefix}_Task_ID', f'{task_prefix}_Task_Index',
                    f'{task_prefix}_Start_Time', f'{task_prefix}_Completion_Time',
                    f'{task_prefix}_Duration_Seconds', f'{task_prefix}_Rating_Given',
                    f'{task_prefix}_Rating_Timestamp'
                ])
                
                # Add element/layer columns based on study type
                if study.study_type == 'grid' and study.elements:
                    for element in study.elements:
                        header_row.extend([
                            f'{task_prefix}_{element.element_id}_Shown',
                            f'{task_prefix}_{element.element_id}_Content'
                        ])
                elif study.study_type == 'layer' and study.study_layers:
                    for layer in study.study_layers:
                        header_row.extend([
                            f'{task_prefix}_Layer_{layer.layer_id}_Z_Index',
                            f'{task_prefix}_Layer_{layer.layer_id}_Order',
                            f'{task_prefix}_Layer_{layer.layer_id}_Image_URL',
                            f'{task_prefix}_Layer_{layer.layer_id}_Image_Name'
                        ])
        
        writer.writerow(header_row)
        
        # Write data row
        row_data = [
            str(response._id), response.session_id, response.respondent_id,
            str(study._id), study.title,
                response.session_start_time.isoformat() if response.session_start_time else '',
                response.session_end_time.isoformat() if response.session_end_time else '',
                response.total_study_duration,
                'Completed' if response.is_completed else 'Abandoned',
            response.completed_tasks_count, response.total_tasks_assigned,
            response.completion_percentage, response.is_abandoned,
            response.abandonment_reason or ''
        ]
        
        # Add classification answers
        if study.classification_questions:
            for question in study.classification_questions:
                answer = next((a.answer for a in response.classification_answers 
                             if a.question_id == question.question_id), '')
                row_data.append(answer)
        
        # Add personal info
        if hasattr(response, 'personal_info') and response.personal_info:
            personal = response.personal_info
            row_data.extend([
                personal.get('birth_date', ''),
                personal.get('age', ''),
                personal.get('gender', '')
            ])
        else:
            row_data.extend(['', '', ''])
        
        # Add task data
        if response.completed_tasks:
            for task in response.completed_tasks:
                row_data.extend([
                    task.task_id, task.task_index,
                    task.task_start_time.isoformat() if task.task_start_time else '',
                    task.task_completion_time.isoformat() if task.task_completion_time else '',
                    task.task_duration_seconds, task.rating_given,
                    task.rating_timestamp.isoformat() if task.rating_timestamp else ''
                ])
                
                # Add element/layer data
                if study.study_type == 'grid' and study.elements:
                    elements_shown = getattr(task, 'elements_shown_in_task', {})
                    elements_shown_content = getattr(task, 'elements_shown_content', {})
                    for element in study.elements:
                        row_data.extend([
                            elements_shown.get(element.element_id, ''),
                            elements_shown_content.get(f'{element.element_id}_content', '')
                        ])
                elif study.study_type == 'layer' and study.study_layers:
                    elements_shown_content = getattr(task, 'elements_shown_content', {})
                    for layer in study.study_layers:
                        layer_data = elements_shown_content.get(str(layer.layer_id), {})
                        row_data.extend([
                            layer_data.get('z_index', layer.z_index),
                            layer_data.get('order', layer.order),
                            layer_data.get('url', ''),
                            layer_data.get('name', '')
                        ])
        
        writer.writerow(row_data)
        output.seek(0)
        
        # Generate descriptive filename
        study_name = study.title.replace(' ', '_').replace('/', '_').replace('\\', '_')
        study_type = study.study_type.upper()
        respondent_id = response.respondent_id
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H%M')
        filename = f"{study_name}_{study_type}_Respondent_{respondent_id}_{current_date}_{current_time}.csv"
        
        response_obj = current_app.response_class(
            output.getvalue(),
            status=200,
            mimetype='text/csv'
        )
        response_obj.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response_obj
        
    except Exception as e:
        flash(f'Error exporting response: {str(e)}', 'error')
        return redirect(url_for('dashboard.studies'))

@dashboard_bp.route('/export-all-studies')
@login_required
def export_all_studies():
    """Export summary data for all studies created by the current user."""
    try:
        studies = Study.objects(creator=current_user)
        
        if not studies:
            flash('No studies found for export.', 'warning')
            return redirect(url_for('dashboard.studies'))
        
        # Create CSV output
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        header_row = [
            'Study ID', 'Study Title', 'Study Type', 'Status', 'Created Date',
            'Total Responses', 'Completed Responses', 'Abandoned Responses',
            'Completion Rate (%)', 'Total Tasks', 'Elements/Layers Count',
            'Classification Questions', 'Creator', 'Share Token'
        ]
        writer.writerow(header_row)
        
        # Write data rows
        for study in studies:
            # Get real-time counts
            real_time_counts = study.get_real_time_counts()
            
            # Count elements/layers
            if study.study_type == 'grid' and study.elements:
                elements_count = len(study.elements)
            elif study.study_type == 'layer' and study.study_layers:
                elements_count = len(study.study_layers)
            else:
                elements_count = 0
            
            # Count classification questions
            classification_count = len(study.classification_questions) if study.classification_questions else 0
            
            # Calculate completion rate
            completion_rate = 0
            if real_time_counts['total'] > 0:
                completion_rate = (real_time_counts['completed'] / real_time_counts['total']) * 100
            
            row_data = [
                str(study._id),
                study.title,
                study.study_type,
                study.status,
                study.created_at.isoformat() if study.created_at else '',
                real_time_counts['total'],
                real_time_counts['completed'],
                real_time_counts['abandoned'],
                round(completion_rate, 2),
                study.iped_parameters.tasks_per_consumer if study.iped_parameters else 0,
                elements_count,
                classification_count,
                study.creator.username if study.creator else '',
                study.share_token or ''
            ]
            writer.writerow(row_data)
        
        output.seek(0)
        
        # Generate descriptive filename
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H%M')
        study_count = len(studies)
        filename = f"All_Studies_Summary_{study_count}_studies_{current_date}_{current_time}.csv"
        
        response = current_app.response_class(
            output.getvalue(),
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    except Exception as e:
        flash(f'Error exporting studies: {str(e)}', 'error')
        return redirect(url_for('dashboard.studies'))

@dashboard_bp.route('/sync-counts')
@login_required
def sync_study_counts():
    """Sync all study response counts to ensure consistency."""
    try:
        studies = Study.objects(creator=current_user)
        updated_count = 0
        
        for study in studies:
            # Update response counters for each study
            study.update_response_counters()
            updated_count += 1
        
        flash(f'Successfully synced response counts for {updated_count} studies.', 'success')
        return redirect(url_for('dashboard.studies'))
        
    except Exception as e:
        flash(f'Error syncing counts: {str(e)}', 'error')
        return redirect(url_for('dashboard.studies'))

@dashboard_bp.route('/responses/<response_id>/details')
@login_required
def get_response_details(response_id):
    """Get detailed information about a specific response including tasks."""
    try:
        # Find the response and ensure it belongs to a study created by current user
        response = StudyResponse.objects(_id=response_id).first()
        if not response:
            return jsonify({'error': 'Response not found'}), 404
        
        # Check if the study belongs to current user
        study = Study.objects(_id=response.study._id, creator=current_user).first()
        if not study:
            return jsonify({'error': 'Access denied'}), 403
        
        # Prepare response data
        response_data = {
            'response_id': str(response._id),
            'respondent_id': response.respondent_id,
            'session_id': response.session_id,
            'status': 'Completed' if response.is_completed else 'Abandoned',
            'completion_percentage': response.completion_percentage or 0,
            'session_start_time': response.session_start_time.isoformat() if response.session_start_time else None,
            'session_end_time': response.session_end_time.isoformat() if response.session_end_time else None,
            'total_study_duration': response.total_study_duration or 0,
            'created_at': response.session_start_time.isoformat() if response.session_start_time else None,  # Use session_start_time as created_at
            'last_activity': response.last_activity.isoformat() if response.last_activity else None,
            'is_completed': response.is_completed,
            'is_abandoned': response.is_abandoned,
            'abandonment_reason': response.abandonment_reason if response.is_abandoned else None,
            'classification_answers': {},
            'personal_info': response.personal_info or {},
            'tasks': []
        }
        
        # Process classification answers
        if response.classification_answers:
            for answer in response.classification_answers:
                if hasattr(answer, 'question_text') and hasattr(answer, 'answer'):
                    response_data['classification_answers'][answer.question_text] = answer.answer
        
        # Add task details with vignette information
        if hasattr(response, 'completed_tasks') and response.completed_tasks:
            for i, task in enumerate(response.completed_tasks):
                try:
                    task_data = {
                        'task_index': i + 1,
                        'task_id': str(task.task_id) if hasattr(task, 'task_id') and task.task_id else f'task_{i+1}',
                        'start_time': task.task_start_time.isoformat() if hasattr(task, 'task_start_time') and task.task_start_time else None,
                        'completion_time': task.task_completion_time.isoformat() if hasattr(task, 'task_completion_time') and task.task_completion_time else None,
                        'duration_seconds': getattr(task, 'task_duration_seconds', 0) or 0,
                        'rating_given': getattr(task, 'rating_given', 0) or 0,
                        'rating_timestamp': task.rating_timestamp.isoformat() if hasattr(task, 'rating_timestamp') and task.rating_timestamp else None,
                        'elements_shown': [],
                        'layers_shown': [],
                        'vignettes': []  # New field for actual vignette content
                    }
                    
                    # Add element information and vignettes for grid studies
                    # Check for new grid structure (elements_shown_content)
                    if hasattr(task, 'elements_shown_content') and task.elements_shown_content:
                        try:
                            
                            # Process new grid study elements structure
                            for element_name, element_data in task.elements_shown_content.items():
                                if element_data and isinstance(element_data, dict) and element_data.get('content'):
                                    # Check if this element is active in elements_shown_in_task
                                    element_active = getattr(task, 'elements_shown_in_task', {}).get(element_name, 0) if hasattr(task, 'elements_shown_in_task') else 0
                                    
                                    if element_active == 1:
                                        print(f"✅ Active grid element: {element_name}")
                                        print(f"✅ Element content: {element_data['content']}")
                                        
                                        # Add to elements_shown for backward compatibility
                                        element_info = {
                                            'element_id': element_data.get('element_id', element_name),
                                            'name': element_data.get('name', element_name),
                                            'content': element_data['content'],
                                            'alt_text': element_data.get('alt_text', ''),
                                            'category_name': element_data.get('category_name', ''),
                                            'position': 'active'
                                        }
                                        task_data['elements_shown'].append(element_info)
                                        
                                        # Add vignette content for grid studies
                                        vignette_data = {
                                            'type': 'grid',
                                            'content': element_data['content'],
                                            'element_id': element_data.get('element_id', element_name),
                                            'element_name': element_data.get('name', element_name),
                                            'alt_text': element_data.get('alt_text', ''),
                                            'category_name': element_data.get('category_name', ''),
                                            'is_active': True
                                        }
                                        task_data['vignettes'].append(vignette_data)
                        except Exception as e:
                            print(f"Error processing elements_shown_content: {e}")
                            pass  # Silently handle errors for performance
                    
                    # Legacy support for old grid structure (elements_shown_in_task)
                    elif hasattr(task, 'elements_shown_in_task') and task.elements_shown_in_task:
                        try:
                            
                            # Process legacy grid study elements
                            for element_name, element_data in task.elements_shown_in_task.items():
                                if element_name.endswith('_content') and element_data and element_data != '':
                                    # This is the image content
                                    base_name = element_name.replace('_content', '')
                                    element_active = task.elements_shown_in_task.get(base_name, 0)
                                    
                                    if element_active == 1:
                                        print(f"✅ Active grid element: {base_name}")
                                        print(f"✅ Element content: {element_data}")
                                        
                                        # Add to elements_shown for backward compatibility
                                        element_info = {
                                            'element_id': str(base_name),
                                            'content': element_data,
                                            'position': 'active'
                                        }
                                        task_data['elements_shown'].append(element_info)
                                        
                                        # Add vignette content for grid studies
                                        vignette_data = {
                                            'type': 'grid',
                                            'content': element_data,
                                            'element_id': str(base_name),
                                            'element_name': base_name,
                                            'is_active': True
                                        }
                                        task_data['vignettes'].append(vignette_data)
                        except Exception:
                            pass  # Silently handle errors for performance
                    
                    # Add layer information and vignettes for layer studies
                    if hasattr(task, 'elements_shown_content') and task.elements_shown_content:
                        try:
                            # Process elements_shown_content (this is the actual vignette data)
                            for element_name, element_data in task.elements_shown_content.items():
                                if isinstance(element_data, dict) and element_data.get('url'):
                                    # Add to layers_shown for backward compatibility
                                    layer_info = {
                                        'layer_id': str(element_name),
                                        'z_index': element_data.get('z_index', 0),
                                        'order': element_data.get('order', 0)
                                    }
                                    task_data['layers_shown'].append(layer_info)
                                    
                                    # Add vignette content directly from elements_shown_content
                                    vignette_data = {
                                        'type': 'layer',
                                        'content': element_data.get('url'),
                                        'layer_id': str(element_name),
                                        'z_index': element_data.get('z_index', 0),
                                        'image_name': element_data.get('name', element_name),
                                        'alt_text': element_data.get('alt_text', ''),
                                        'order': element_data.get('order', 0),
                                        'layer_name': element_data.get('layer_name', element_name)
                                    }
                                    task_data['vignettes'].append(vignette_data)
                        except Exception as e:
                            pass  # Silently handle errors for performance
                    
                    # Also check the old elements_shown field for backward compatibility
                    elif hasattr(task, 'elements_shown') and task.elements_shown:
                        try:
                            # Process grid study elements
                            for element_name, element_data in task.elements_shown.items():
                                if element_name.endswith('_content') and element_data and element_data != '':
                                    # This is the image content
                                    base_name = element_name.replace('_content', '')
                                    element_active = task.elements_shown.get(base_name, 0)
                                    
                                    if element_active == 1:
                                        # Add to elements_shown for backward compatibility
                                        element_info = {
                                            'element_id': str(base_name),
                                            'content': element_data,
                                            'position': 'active'
                                        }
                                        task_data['elements_shown'].append(element_info)
                                        
                                        # Add vignette content for grid studies
                                        vignette_data = {
                                            'type': 'grid',
                                            'content': element_data,
                                            'element_id': str(base_name),
                                            'element_name': base_name,
                                            'is_active': True
                                        }
                                        task_data['vignettes'].append(vignette_data)
                        except Exception:
                            pass  # Silently handle errors for performance
                    
                    # Fallback: If no vignettes were generated but this is a grid study, generate them from study elements
                    if study.study_type == 'grid' and len(task_data['vignettes']) == 0 and study.elements:
                        try:
                            for element in study.elements:
                                if hasattr(element, 'url') and element.url:
                                    vignette_data = {
                                        'type': 'grid',
                                        'content': element.url,
                                        'element_id': str(element.element_id),
                                        'element_name': element.name,
                                        'is_active': True
                                    }
                                    task_data['vignettes'].append(vignette_data)
                        except Exception:
                            pass  # Silently handle errors for performance
                    
                    # Also check layers_shown_in_task for backward compatibility
                    elif hasattr(task, 'layers_shown_in_task') and task.layers_shown_in_task:
                        try:
                            for layer_id, layer_data in task.layers_shown_in_task.items():
                                if isinstance(layer_data, dict):
                                    layer_info = {
                                        'layer_id': str(layer_id),
                                        'z_index': layer_data.get('z_index', 0),
                                        'order': layer_data.get('order', 0)
                                    }
                                    task_data['layers_shown'].append(layer_info)
                                    
                                    # Get actual vignette content from study layers based on z-index
                                    if study.study_type == 'layer' and study.study_layers:
                                        for study_layer in study.study_layers:
                                            if str(study_layer.layer_id) == str(layer_id):
                                                # Add vignette content for this layer
                                                for image in study_layer.images:
                                                    vignette_data = {
                                                        'type': 'layer',
                                                        'content': image.url,
                                                        'layer_id': str(layer_id),
                                                        'layer_name': study_layer.name,
                                                        'z_index': study_layer.z_index,
                                                        'image_name': image.name,
                                                        'alt_text': image.alt_text,
                                                        'order': image.order
                                                    }
                                                    task_data['vignettes'].append(vignette_data)
                        except Exception:
                            pass  # Silently handle errors for performance
                    
                    # Fallback: If no vignettes were generated but this is a layer study, generate them from study layers
                    if study.study_type == 'layer' and len(task_data['vignettes']) == 0 and study.study_layers:
                        try:
                            # Sort layers by z_index to ensure proper stacking order
                            sorted_layers = sorted(study.study_layers, key=lambda x: getattr(x, 'z_index', 0) or 0)
                            
                            for study_layer in sorted_layers:
                                if hasattr(study_layer, 'images') and study_layer.images:
                                    for image in study_layer.images:
                                        vignette_data = {
                                            'type': 'layer',
                                            'content': image.url,
                                            'layer_id': str(study_layer.layer_id),
                                            'layer_name': study_layer.name,
                                            'z_index': getattr(study_layer, 'z_index', 0) or 0,
                                            'image_name': image.name,
                                            'alt_text': image.alt_text,
                                            'order': image.order
                                        }
                                        task_data['vignettes'].append(vignette_data)
                        except Exception:
                            pass  # Silently handle errors for performance
                    
                    response_data['tasks'].append(task_data)
                    
                except Exception:
                    # Add a basic task entry if there's an error
                    response_data['tasks'].append({
                        'task_index': i + 1,
                        'task_id': f'task_{i+1}',
                        'start_time': None,
                        'completion_time': None,
                        'duration_seconds': 0,
                        'rating_given': 0,
                        'rating_timestamp': None,
                        'elements_shown': [],
                        'layers_shown': [],
                        'vignettes': []
                    })
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Error fetching response details: {str(e)}'}), 500

@dashboard_bp.route('/studies/<study_id>/delete', methods=['POST'])
@login_required
def delete_study(study_id):
    """Delete a study."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    if study.status == 'active':
        return jsonify({'error': 'Cannot delete active studies'}), 400
    
    try:
        # Delete associated responses and task sessions
        StudyResponse.objects(study=study).delete()
        TaskSession.objects(study_response__study=study).delete()
        
        # Remove from user's studies list
        current_user.studies.remove(study)
        current_user.save()
        
        # Delete the study
        study.delete()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/studies/<study_id>/share')
@login_required
def study_share(study_id):
    """Study sharing page."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        flash('Study not found.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    return render_template('dashboard/study_share.html', study=study)

@dashboard_bp.route('/studies/<study_id>/preview')
@login_required
def study_preview(study_id):
    """Preview study as a respondent would see it."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        flash('Study not found.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    return render_template('dashboard/study_preview.html', study=study)
