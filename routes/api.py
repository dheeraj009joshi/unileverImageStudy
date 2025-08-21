from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models.study import Study
from models.response import StudyResponse, TaskSession
from datetime import datetime, timedelta
import json

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/studies/<study_id>/stats')
@login_required
def study_stats(study_id):
    """Get real-time study statistics."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    try:
        # Get responses for the last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_responses = StudyResponse.objects(
            study=study,
            session_start_time__gte=yesterday
        )
        
        # Get responses for the last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        weekly_responses = StudyResponse.objects(
            study=study,
            session_start_time__gte=week_ago
        )
        
        # Calculate statistics
        total_responses = StudyResponse.objects(study=study).count()
        completed_responses = StudyResponse.objects(study=study, is_completed=True).count()
        abandoned_responses = StudyResponse.objects(study=study, is_abandoned=True).count()
        
        # Recent activity
        recent_total = recent_responses.count()
        recent_completed = recent_responses.filter(is_completed=True).count()
        recent_abandoned = recent_responses.filter(is_abandoned=True).count()
        
        # Weekly trends
        daily_stats = []
        for i in range(7):
            date = datetime.utcnow() - timedelta(days=i)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            day_responses = StudyResponse.objects(
                study=study,
                session_start_time__gte=day_start,
                session_start_time__lte=day_end
            )
            
            daily_stats.append({
                'date': date.strftime('%Y-%m-%d'),
                'total': day_responses.count(),
                'completed': day_responses.filter(is_completed=True).count(),
                'abandoned': day_responses.filter(is_abandoned=True).count()
            })
        
        daily_stats.reverse()
        
        return jsonify({
            'total_responses': total_responses,
            'completed_responses': completed_responses,
            'abandoned_responses': abandoned_responses,
            'completion_rate': (completed_responses / total_responses * 100) if total_responses > 0 else 0,
            'recent_24h': {
                'total': recent_total,
                'completed': recent_completed,
                'abandoned': recent_abandoned
            },
            'daily_trends': daily_stats
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/studies/<study_id>/task-timing')
@login_required
def task_timing_analytics(study_id):
    """Get detailed task timing analytics."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    try:
        # Get all completed responses
        completed_responses = StudyResponse.objects(study=study, is_completed=True)
        
        # Task timing data
        task_times = []
        element_interactions = {}
        
        for response in completed_responses:
            for task in response.completed_tasks:
                task_times.append({
                    'task_id': task.task_id,
                    'duration': task.task_duration_seconds,
                    'respondent_id': task.respondent_id,
                    'completion_time': task.task_completion_time.isoformat()
                })
                
                # Aggregate element interactions
                for interaction in task.element_interactions:
                    element_id = interaction.element_id
                    if element_id not in element_interactions:
                        element_interactions[element_id] = {
                            'total_view_time': 0,
                            'total_hover_count': 0,
                            'total_click_count': 0,
                            'interaction_count': 0,
                            'avg_view_time': 0
                        }
                    
                    element_interactions[element_id]['total_view_time'] += interaction.view_time_seconds
                    element_interactions[element_id]['total_hover_count'] += interaction.hover_count
                    element_interactions[element_id]['total_click_count'] += interaction.click_count
                    element_interactions[element_id]['interaction_count'] += 1
        
        # Calculate averages
        for element_id, data in element_interactions.items():
            if data['interaction_count'] > 0:
                data['avg_view_time'] = data['total_view_time'] / data['interaction_count']
        
        # Timing distribution
        if task_times:
            durations = [t['duration'] for t in task_times]
            durations.sort()
            
            # Percentiles
            p25 = durations[int(len(durations) * 0.25)]
            p50 = durations[int(len(durations) * 0.50)]
            p75 = durations[int(len(durations) * 0.75)]
            p90 = durations[int(len(durations) * 0.90)]
            
            timing_distribution = {
                'min': min(durations),
                'max': max(durations),
                'mean': sum(durations) / len(durations),
                'median': p50,
                'p25': p25,
                'p75': p75,
                'p90': p90,
                'total_tasks': len(durations)
            }
        else:
            timing_distribution = {}
        
        return jsonify({
            'task_times': task_times,
            'element_interactions': element_interactions,
            'timing_distribution': timing_distribution
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/studies/<study_id>/element-heatmap')
@login_required
def element_heatmap(study_id):
    """Get element interaction heatmap data."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    try:
        # Get all completed responses
        completed_responses = StudyResponse.objects(study=study, is_completed=True)
        
        # Initialize element data
        element_data = {}
        for element in study.elements:
            element_data[element.element_id] = {
                'name': element.name,
                'total_view_time': 0,
                'total_hover_count': 0,
                'total_click_count': 0,
                'appearance_count': 0,
                'avg_rating': 0,
                'ratings': []
            }
        
        # Aggregate data from all tasks
        for response in completed_responses:
            for task in response.completed_tasks:
                # Count element appearances
                for element_id, shown in task.elements_shown_in_task.items():
                    if shown == 1:
                        element_data[element_id]['appearance_count'] += 1
                
                # Aggregate interactions and ratings
                for interaction in task.element_interactions:
                    element_id = interaction.element_id
                    if element_id in element_data:
                        element_data[element_id]['total_view_time'] += interaction.view_time_seconds
                        element_data[element_id]['total_hover_count'] += interaction.hover_count
                        element_data[element_id]['total_click_count'] += interaction.click_count
                
                # Get rating for this task
                rating = task.rating_given
                visible_elements = [eid for eid, shown in task.elements_shown_in_task.items() if shown == 1]
                for element_id in visible_elements:
                    if element_id in element_data:
                        element_data[element_id]['ratings'].append(rating)
        
        # Calculate averages
        for element_id, data in element_data.items():
            if data['appearance_count'] > 0:
                data['avg_rating'] = sum(data['ratings']) / len(data['ratings']) if data['ratings'] else 0
                data['avg_view_time'] = data['total_view_time'] / data['appearance_count']
                data['avg_hover_count'] = data['total_hover_count'] / data['appearance_count']
                data['avg_click_count'] = data['total_click_count'] / data['appearance_count']
            else:
                data['avg_rating'] = 0
                data['avg_view_time'] = 0
                data['avg_hover_count'] = 0
                data['avg_click_count'] = 0
        
        return jsonify({
            'element_data': element_data,
            'total_responses': completed_responses.count()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/studies/<study_id>/abandonment-analysis')
@login_required
def abandonment_analysis(study_id):
    """Get study abandonment analysis."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    try:
        # Get abandoned responses
        abandoned_responses = StudyResponse.objects(study=study, is_abandoned=True)
        
        # Abandonment reasons
        abandonment_reasons = {}
        task_abandonment = {}
        
        for response in abandoned_responses:
            reason = response.abandonment_reason or 'Unknown'
            abandonment_reasons[reason] = abandonment_reasons.get(reason, 0) + 1
            
            # Task-level abandonment
            current_task = response.current_task_index
            if current_task not in task_abandonment:
                task_abandonment[current_task] = 0
            task_abandonment[current_task] += 1
        
        # Time-based abandonment
        time_based_abandonment = {
            '0-30s': 0,
            '30s-1m': 0,
            '1m-2m': 0,
            '2m-5m': 0,
            '5m+': 0
        }
        
        for response in abandoned_responses:
            if response.session_start_time and response.abandonment_timestamp:
                duration = (response.abandonment_timestamp - response.session_start_time).total_seconds()
                if duration < 30:
                    time_based_abandonment['0-30s'] += 1
                elif duration < 60:
                    time_based_abandonment['30s-1m'] += 1
                elif duration < 120:
                    time_based_abandonment['1m-2m'] += 1
                elif duration < 300:
                    time_based_abandonment['2m-5m'] += 1
                else:
                    time_based_abandonment['5m+'] += 1
        
        return jsonify({
            'total_abandoned': abandoned_responses.count(),
            'abandonment_reasons': abandonment_reasons,
            'task_abandonment': task_abandonment,
            'time_based_abandonment': time_based_abandonment
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/studies/<study_id>/export-timing-data')
@login_required
def export_timing_data(study_id):
    """Export detailed timing data for analysis."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    try:
        # Get all responses
        responses = StudyResponse.objects(study=study)
        
        # Prepare timing data
        timing_data = []
        
        for response in responses:
            response_data = {
                'session_id': response.session_id,
                'respondent_id': response.respondent_id,
                'session_start_time': response.session_start_time.isoformat() if response.session_start_time else None,
                'session_end_time': response.session_end_time.isoformat() if response.session_end_time else None,
                'total_duration': response.total_study_duration,
                'completion_status': 'completed' if response.is_completed else 'abandoned',
                'abandonment_reason': response.abandonment_reason,
                'tasks': []
            }
            
            for task in response.completed_tasks:
                task_data = {
                    'task_id': task.task_id,
                    'task_index': task.task_index,
                    'start_time': task.task_start_time.isoformat() if task.task_start_time else None,
                    'completion_time': task.task_completion_time.isoformat() if task.task_completion_time else None,
                    'duration_seconds': task.task_duration_seconds,
                    'rating': task.rating_given,
                    'elements_shown': task.elements_shown_in_task,
                    'element_interactions': []
                }
                
                for interaction in task.element_interactions:
                    interaction_data = {
                        'element_id': interaction.element_id,
                        'view_time_seconds': interaction.view_time_seconds,
                        'hover_count': interaction.hover_count,
                        'click_count': interaction.click_count,
                        'first_view_time': interaction.first_view_time.isoformat() if interaction.first_view_time else None,
                        'last_view_time': interaction.last_view_time.isoformat() if interaction.last_view_time else None
                    }
                    task_data['element_interactions'].append(interaction_data)
                
                response_data['tasks'].append(task_data)
            
            timing_data.append(response_data)
        
        return jsonify({
            'study_id': str(study._id),
            'study_title': study.title,
            'export_timestamp': datetime.utcnow().isoformat(),
            'total_responses': len(timing_data),
            'timing_data': timing_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/studies/<study_id>/regenerate-tasks', methods=['POST'])
@login_required
def regenerate_tasks(study_id):
    """Regenerate IPED task matrix for a study."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    if study.status == 'active':
        return jsonify({'error': 'Cannot regenerate tasks for active studies'}), 400
    
    try:
        # Regenerate task matrix
        new_tasks = study.generate_tasks()
        study.save()
        
        return jsonify({
            'success': True,
            'message': 'Task matrix regenerated successfully',
            'total_tasks': study.iped_parameters.total_tasks
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/studies/<study_id>/validate-tasks')
@login_required
def validate_tasks(study_id):
    """Validate IPED task matrix."""
    study = Study.objects(_id=study_id, creator=current_user).first()
    if not study:
        return jsonify({'error': 'Study not found'}), 404
    
    try:
        if not study.tasks:
            return jsonify({'error': 'No tasks generated'}), 400
        
        # Validation results
        validation_results = {
            'total_tasks': study.iped_parameters.total_tasks,
            'tasks_per_consumer': study.iped_parameters.tasks_per_consumer,
            'number_of_respondents': study.iped_parameters.number_of_respondents,
            'min_active_elements': study.iped_parameters.min_active_elements,
            'max_active_elements': study.iped_parameters.max_active_elements,
            'validation_passed': True,
            'issues': []
        }
        
        # Validate task structure
        for respondent_id, tasks in study.tasks.items():
            if len(tasks) != study.iped_parameters.tasks_per_consumer:
                validation_results['validation_passed'] = False
                validation_results['issues'].append(
                    f'Respondent {respondent_id} has {len(tasks)} tasks, expected {study.iped_parameters.tasks_per_consumer}'
                )
            
            for task in tasks:
                active_elements = sum(1 for shown in task['elements_shown'].values() if shown == 1)
                if not (study.iped_parameters.min_active_elements <= active_elements <= study.iped_parameters.max_active_elements):
                    validation_results['validation_passed'] = False
                    validation_results['issues'].append(
                        f'Task {task["task_id"]} has {active_elements} active elements, expected between {study.iped_parameters.min_active_elements} and {study.iped_parameters.max_active_elements}'
                    )
        
        return jsonify(validation_results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
