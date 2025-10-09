#!/usr/bin/env python3
"""
Cron job script to clean up panelist data for completed studies.
This script removes StudyPanelistTasks documents for studies that are marked as completed.
"""

import os
import sys
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from mongoengine import connect
from models.user import User
from models.study import Study
from models.study_draft import StudyDraft
from models.study_task import StudyPanelistTasks
from models.response import StudyResponse
from config import config

def cleanup_completed_studies():
    """Clean up panelist data for completed studies."""
    print("=" * 80)
    print("🧹 CLEANUP COMPLETED STUDIES - CRON JOB")
    print(f"⏰ Started at: {datetime.now()}")
    print("=" * 80)
    
    try:
        # Initialize Flask app and connect to database
        flask_app = Flask(__name__)
        flask_app.config.from_object(config['development'])
        
        # Connect to MongoDB
        connect(host=flask_app.config['MONGODB_SETTINGS']['host'])
        print("✅ Connected to MongoDB")
        
        # Find all completed studies
        completed_studies = Study.objects(status='completed')
        print(f"📊 Found {completed_studies.count()} completed studies")
        
        if completed_studies.count() == 0:
            print("ℹ️  No completed studies found. Nothing to clean up.")
            return
        
        total_deleted = 0
        
        for study in completed_studies:
            print(f"\n🔍 Processing study: {study.title} (ID: {study._id})")
            
            # Count panelist tasks before deletion
            panelist_count = StudyPanelistTasks.objects(draft=study).count()
            
            if panelist_count == 0:
                print(f"   ℹ️  No panelist tasks found for this study")
                continue
            
            print(f"   📋 Found {panelist_count} panelist task documents")
            
            # Delete all StudyPanelistTasks for this study
            deleted_count = StudyPanelistTasks.objects(draft=study).delete()
            
            print(f"   ✅ Deleted {deleted_count} panelist task documents")
            total_deleted += deleted_count
            
            # Optional: Add a cleanup timestamp to the study
            try:
                study.cleanup_timestamp = datetime.utcnow()
                study.save()
                print(f"   📝 Added cleanup timestamp to study")
            except Exception as e:
                print(f"   ⚠️  Warning: Could not add cleanup timestamp: {e}")
        
        print("\n" + "=" * 80)
        print(f"✅ CLEANUP COMPLETED SUCCESSFULLY")
        print(f"📊 Total panelist task documents deleted: {total_deleted}")
        print(f"⏰ Finished at: {datetime.now()}")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ ERROR during cleanup: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def mark_inprogress_as_abandoned():
    """Mark all in-progress responses as abandoned."""
    print("\n" + "=" * 60)
    print("🔄 MARK IN-PROGRESS RESPONSES AS ABANDONED")
    print("=" * 60)
    
    try:
        # Find all in-progress responses
        in_progress_responses = StudyResponse.objects(
            is_completed=False,
            is_abandoned=False,
            is_in_progress=True
        )
        
        count = in_progress_responses.count()
        print(f"📊 Found {count} in-progress responses")
        
        if count == 0:
            print("ℹ️  No in-progress responses to mark as abandoned")
            return
        
        # Mark all in-progress responses as abandoned
        marked = 0
        for response in in_progress_responses:
            try:
                # Use mark_abandoned method for proper count updates and consistency
                response.mark_abandoned(reason="Marked abandoned by cleanup cron job")
                response.save()
                marked += 1
            except Exception as e:
                print(f"❌ Error marking response {response._id} as abandoned: {e}")
        
        print(f"✅ Marked {marked} in-progress responses as abandoned")
            
    except Exception as e:
        print(f"⚠️  Warning: Could not mark in-progress responses as abandoned: {e}")

if __name__ == "__main__":
    # Main cleanup: Remove panelist data for completed studies
    cleanup_completed_studies()
    
    # Mark all in-progress responses as abandoned
    mark_inprogress_as_abandoned()
    
    print("\n🎉 Cleanup script completed successfully!")
