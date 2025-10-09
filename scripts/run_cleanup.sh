#!/bin/bash

# Cleanup script for completed studies
# This script should be run as a cron job

# Set the project directory
PROJECT_DIR="/Users/dheeraj/Development/Work_Dheeraj/v2/final-deliverable/unileverImageStudy"

# Change to project directory
cd "$PROJECT_DIR"

# Activate virtual environment
source venv/bin/activate

# Run the cleanup script
python3 scripts/cleanup_completed_studies.py

# Log the execution
echo "$(date): Cleanup script executed" >> logs/cleanup.log
