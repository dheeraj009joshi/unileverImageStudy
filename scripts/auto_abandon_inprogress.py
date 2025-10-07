"""
Cron-safe script: mark in-progress StudyResponses abandoned after 10 minutes of inactivity.

Usage (cron, every 5 minutes for example):
*/5 * * * * /usr/bin/env python /path/to/unileverImageStudy/scripts/auto_abandon_inprogress.py >> /var/log/auto_abandon.log 2>&1
"""

import os
import sys
from datetime import datetime, timedelta

# Ensure project root on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from models.study import Study
from models.response import StudyResponse


def run():
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    total_marked = 0

    try:
        # Iterate all active studies
        for study in Study.objects(status='active'):
            stale = StudyResponse.objects(
                study=study,
                is_completed=False,
                is_abandoned=False,
                is_in_progress=True,
                last_activity__lt=cutoff
            )
            count = 0
            for resp in stale:
                resp.mark_abandoned('Auto-abandoned after 10 minutes of inactivity')
                resp.save()
                count += 1
            if count:
                print(f"[{datetime.utcnow().isoformat()}] Auto-abandoned {count} responses for study {study._id}")
            total_marked += count
    except Exception as e:
        print(f"[{datetime.utcnow().isoformat()}] ERROR: {e}")

    print(f"[{datetime.utcnow().isoformat()}] Done. Total marked abandoned: {total_marked}")


if __name__ == '__main__':
    run()


