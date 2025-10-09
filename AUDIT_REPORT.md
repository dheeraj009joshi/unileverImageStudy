# Count Updates Audit Report

## Executive Summary
Comprehensive audit of `completed_tasks_count` and `completion_percentage` updates across the entire project.

## ✅ CORRECT IMPLEMENTATIONS

### 1. `models/response.py` - `add_completed_task()` method (Line 143-147)
```python
def add_completed_task(self, task_data):
    """Add a completed task to the response."""
    completed_task = CompletedTask(**task_data)
    self.completed_tasks.append(completed_task)
    self.completed_tasks_count = len(self.completed_tasks)  # ✅ CORRECT
    self.update_completion_percentage()
```
**Status**: ✅ **CORRECT** - Updates count based on actual list length

### 2. `models/response.py` - `update_completion_percentage()` method (Line 115-124)
```python
def update_completion_percentage(self):
    """Update completion percentage based on completed tasks."""
    actual_completed_tasks = len(self.completed_tasks) if self.completed_tasks else 0
    if self.total_tasks_assigned > 0:
        self.completion_percentage = (actual_completed_tasks / self.total_tasks_assigned) * 100.0
    else:
        self.completion_percentage = 0.0
    
    # Also update the completed_tasks_count to match actual completed tasks
    self.completed_tasks_count = actual_completed_tasks  # ✅ CORRECT
```
**Status**: ✅ **CORRECT** - Uses actual list length

### 3. `models/response.py` - `mark_completed()` method (Line 153-177)
```python
def mark_completed(self):
    """Mark the study response as completed."""
    actual_completed_tasks = len(self.completed_tasks) if self.completed_tasks else 0  # ✅ CORRECT
    total_tasks = self.total_tasks_assigned or 0
    
    # Safety check: Only mark as completed if there are actually completed tasks
    if actual_completed_tasks == 0:  # ✅ CORRECT
        print(f"WARNING: Attempting to mark response {self._id} as completed with 0 tasks - resetting for restart!")
        self.reset_for_restart()
        return
    
    # Calculate completion percentage based on actual completed tasks
    if total_tasks > 0:
        self.completion_percentage = (actual_completed_tasks / total_tasks) * 100.0  # ✅ CORRECT
    else:
        self.completion_percentage = 0.0
```
**Status**: ✅ **CORRECT** - Uses actual list length and includes safety check

### 4. `models/response.py` - `reset_for_restart()` method (Line 126-141)
```python
def reset_for_restart(self):
    """Reset response for task restart when no tasks are completed."""
    self.is_completed = False
    self.is_in_progress = True
    self.is_abandoned = False
    self.completed_tasks_count = 0  # ✅ CORRECT
    self.completion_percentage = 0.0
    self.current_task_index = 0
    # Clear completed tasks
    self.completed_tasks = []
```
**Status**: ✅ **CORRECT** - Resets count to 0 and clears list

### 5. `routes/study_participation.py` - `personal_info()` route (Line 440)
```python
response_data = {
    'study': study,
    'session_id': session_id,
    'respondent_id': respondent_id,
    'total_tasks_assigned': total_tasks,
    'completed_tasks_count': 0,  # ✅ CORRECT - Initialize to 0
    'session_start_time': datetime.utcnow(),
    'is_completed': False,
    'classification_answers': [],
    'personal_info': personal_info_data,
    'total_study_duration': 0.0,
    'last_activity': datetime.utcnow(),
    'completed_tasks': [],  # Initialize empty list
    'current_task_index': 0,  # Start at first task
    'completion_percentage': 0.0,  # Start at 0%
    'is_in_progress': True,
    'is_abandoned': False
}
```
**Status**: ✅ **CORRECT** - Initializes count to 0

### 6. `routes/study_participation.py` - `submit_all_ratings()` route (Line 994-1025)
```python
# Update completion status based on actual completed tasks
try:
    if saved_count > 0:
        # Refresh response to get latest completed_tasks count
        response.reload()
        actual_completed_tasks = len(response.completed_tasks) if response.completed_tasks else 0  # ✅ CORRECT
        total_tasks = response.total_tasks_assigned or 0
        
        # Calculate completion percentage
        if total_tasks > 0:
            completion_percentage = (actual_completed_tasks / total_tasks) * 100
            response.completion_percentage = completion_percentage
        
        # Only mark as completed if ALL tasks are done AND at least one task is completed
        if actual_completed_tasks >= total_tasks and total_tasks > 0 and actual_completed_tasks > 0:  # ✅ CORRECT
            response.is_completed = True
            response.is_in_progress = False
            response.is_abandoned = False
        else:
            response.is_completed = False
            response.is_in_progress = True
            response.is_abandoned = False
            
            # If no tasks completed at all, reset for restart
            if actual_completed_tasks == 0:  # ✅ CORRECT
                print(f"WARNING: Response {response._id} has 0 completed tasks - resetting for restart")
                response.reset_for_restart()
```
**Status**: ✅ **CORRECT** - Uses actual list length and includes safety check

### 7. `routes/study_participation.py` - `task_complete()` route (Line 1113)
```python
response.add_completed_task(task_payload)  # ✅ CORRECT - Uses method that updates count
```
**Status**: ✅ **CORRECT** - Uses `add_completed_task()` which automatically updates count

### 8. `routes/study_participation.py` - `completed()` route (Line 1236-1240)
```python
response.add_completed_task(task_data)  # ✅ CORRECT - Uses method that updates count
print(f"  Task added successfully")

print(f"\n--- SAVING RESPONSE ---")
response.update_completion_percentage()  # ✅ CORRECT - Updates count and percentage
print(f"Completion percentage: {response.completion_percentage}")

# Mark response as completed (not abandoned)
response.mark_completed()  # ✅ CORRECT - Uses method with safety checks
```
**Status**: ✅ **CORRECT** - Uses proper methods that update counts

## ⚠️ ISSUES FOUND

### 1. `scripts/auto_abandon_inprogress.py` - Line 55-61
```python
for resp in stale_responses:
    resp.is_abandoned = True
    resp.is_in_progress = False
    resp.save()
    study.decrement_in_progress_responses()
    study.increment_abandoned_responses()
    study.save()
    count += 1
```
**Issue**: ❌ Does NOT update `completed_tasks_count` or `completion_percentage` when marking as abandoned
**Impact**: Low - These fields don't need to change when abandoning, but `last_activity` should be updated
**Recommended Fix**: Add `resp.last_activity = datetime.now(timezone.utc)` before save

**Additional Issue**: The script calls `study.decrement_in_progress_responses()` TWICE - once inside the loop (line 58) and once outside (line 64)
**Impact**: HIGH - This will decrement the count incorrectly
**Recommended Fix**: Remove line 64 `study.decrement_in_progress_responses()`

### 2. `scripts/cleanup_completed_studies.py` - Line 100-106
```python
for response in in_progress_responses:
    try:
        response.is_abandoned = True
        response.is_in_progress = False
        response.is_completed = False
        response.save()
        marked += 1
```
**Issue**: ❌ Does NOT update `completed_tasks_count`, `completion_percentage`, `abandonment_timestamp`, or `abandonment_reason`
**Impact**: Medium - Should use `mark_abandoned()` method for consistency
**Recommended Fix**: Use `response.mark_abandoned(reason="Marked abandoned by cleanup cron job")`

## 📊 SUMMARY

### Total Locations Checked: 10
- ✅ **Correct**: 8
- ⚠️ **Issues Found**: 2

### Critical Issues: 1
- `auto_abandon_inprogress.py` double-decrement bug

### Medium Issues: 1
- `cleanup_completed_studies.py` not using proper `mark_abandoned()` method

## 🔧 RECOMMENDED FIXES

All issues should be fixed to ensure data consistency across the application.

