#!/usr/bin/env python3
"""
Simple test script to verify UUID functionality in models
"""

import uuid
from mongoengine import connect
from models.user import User
from models.study import Study
from models.response import StudyResponse, TaskSession

# Connect to test database
connect('test_iped_system', host='mongodb://localhost:27017/')

def test_uuid_creation():
    """Test that UUIDs are properly created for all models."""
    
    print("Testing UUID creation...")
    
    # Test User creation
    user = User(
        username="testuser",
        email="test@example.com",
        name="Test User"
    )
    user.set_password("password123")
    user.save()
    
    print(f"User created with UUID: {user._id}")
    print(f"UUID type: {type(user._id)}")
    print(f"UUID is valid: {uuid.UUID(str(user._id))}")
    
    # Test Study creation
    study = Study(
        title="Test Study",
        background="Test background",
        language="en",
        main_question="Test question?",
        orientation_text="Test orientation",
        study_type="text",
        share_token="test_token_123",
        creator=user
    )
    study.save()
    
    print(f"Study created with UUID: {study._id}")
    print(f"UUID type: {type(study._id)}")
    print(f"UUID is valid: {uuid.UUID(str(study._id))}")
    
    # Test StudyResponse creation
    response = StudyResponse(
        study=study,
        session_id="test_session_123",
        respondent_id=1,
        total_tasks_assigned=5
    )
    response.save()
    
    print(f"StudyResponse created with UUID: {response._id}")
    print(f"UUID type: {type(response._id)}")
    print(f"UUID is valid: {uuid.UUID(str(response._id))}")
    
    # Test TaskSession creation
    task_session = TaskSession(
        session_id="test_session_123",
        task_id="1_0",
        study_response=response,
        study=study
    )
    task_session.save()
    
    print(f"TaskSession created with UUID: {task_session._id}")
    print(f"UUID type: {type(task_session._id)}")
    print(f"UUID is valid: {uuid.UUID(str(task_session._id))}")
    
    # Clean up
    task_session.delete()
    response.delete()
    study.delete()
    user.delete()
    
    print("\nAll tests passed! UUIDs are working correctly.")

if __name__ == "__main__":
    test_uuid_creation()
