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
        'total_responses': sum(s.get('total_responses', 0) for s in status_data.get('active', {}).get('studies', []))
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
                    'total_responses': 1,
                    'completed_responses': 1,
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
    
    # Single aggregation for all response statistics
    pipeline = [
        {'$match': {'study': study._id}},
        {'$group': {
            '_id': None,
            'total_responses': {'$sum': 1},
            'completed_responses': {'$sum': {'$cond': ['$is_completed', 1, 0]}},
            'abandoned_responses': {'$sum': {'$cond': ['$is_abandoned', 1, 0]}},
            'total_duration': {'$sum': {'$cond': ['$is_completed', '$total_study_duration', 0]}},
            'recent_responses': {
                '$push': {
                    '_id': '$_id',
                    'session_id': '$session_id',
                    'respondent_id': '$respondent_id',
                    'session_start_time': '$session_start_time',
                    'session_end_time': '$session_end_time',
                    'is_completed': '$is_completed',
                    'is_abandoned': '$is_abandoned',
                    'total_study_duration': '$total_study_duration',
                    'completed_tasks_count': '$completed_tasks_count',
                    'completion_percentage': '$completion_percentage'
                }
            }
        }},
        {'$project': {
            'total_responses': 1,
            'completed_responses': 1,
            'abandoned_responses': 1,
            'completion_rate': {
                '$multiply': [
                    {'$divide': ['$completed_responses', '$total_responses']},
                    100
                ]
            },
            'avg_task_time': {
                '$cond': [
                    {'$gt': ['$completed_responses', 0]},
                    {'$divide': ['$total_duration', '$completed_responses']},
                    0
                ]
            },
            'recent_responses': {
                '$slice': ['$recent_responses', 10]
            }
        }}
    ]
    
    # Execute aggregation
    results = list(StudyResponse.objects.aggregate(*pipeline))
    
    if results:
        stats = results[0]
        total_responses = stats['total_responses']
        completed_responses = stats['completed_responses']
        abandoned_responses = stats['abandoned_responses']
        completion_rate = stats['completion_rate']
        avg_task_time = stats['avg_task_time']
        recent_responses = stats['recent_responses']
    else:
        total_responses = completed_responses = abandoned_responses = completion_rate = avg_task_time = 0
        recent_responses = []
    
    return render_template('dashboard/study_detail.html',
                         study=study,
                         total_responses=total_responses,
                         completed_responses=completed_responses,
                         abandoned_responses=abandoned_responses,
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
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    responses = StudyResponse.objects(study=study).order_by('-created_at')
    total = responses.count()
    
    # Pagination
    responses = responses.skip((page - 1) * per_page).limit(per_page)
    
    return render_template('dashboard/study_responses.html',
                         study=study,
                         responses=responses,
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
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/studies/<study_id>/export')
@login_required
def export_study(study_id):
    """Export study data."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        flash('Study not found.', 'error')
        return redirect(url_for('dashboard.studies'))
    
    export_type = request.args.get('type', 'json')
    
    if export_type == 'json':
        # Export as JSON
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
        
    elif export_type == 'csv':
        # Export as CSV
        responses = StudyResponse.objects(study=study)
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Response ID', 'Session ID', 'Respondent ID', 'Start Time', 'End Time',
            'Completion Status', 'Total Duration', 'Tasks Completed', 'Completion Percentage'
        ])
        
        # Write data
        for response in responses:
            writer.writerow([
                str(response.id),
                response.session_id,
                response.respondent_id,
                response.session_start_time.isoformat() if response.session_start_time else '',
                response.session_end_time.isoformat() if response.session_end_time else '',
                'Completed' if response.is_completed else 'Abandoned',
                response.total_study_duration,
                response.completed_tasks_count,
                response.completion_percentage
            ])
        
        output.seek(0)
        
        response = current_app.response_class(
            output.getvalue(),
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = f'attachment; filename=study_{study._id}_responses.csv'
        return response
    
    else:
        flash('Invalid export type.', 'error')
        return redirect(url_for('dashboard.study_detail', study_id=study._id))

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
