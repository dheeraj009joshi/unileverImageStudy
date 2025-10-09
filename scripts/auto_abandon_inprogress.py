"""
Cron-safe script: mark in-progress StudyResponses abandoned after 10 minutes of inactivity.

Usage (cron, every 5 minutes for example):
*/5 * * * * /usr/bin/env python /path/to/unileverImageStudy/scripts/auto_abandon_inprogress.py >> /var/log/auto_abandon.log 2>&1
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure project root on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from mongoengine import connect
from config import config as app_config
from models.user import User  # ensure registration in document registry
from models.study import Study
from models.response import StudyResponse


def _connect_db():
    env = os.environ.get('FLASK_ENV', 'default')
    cfg_cls = app_config.get(env, app_config['default'])
    cfg = cfg_cls()
    connect(host=cfg.MONGODB_SETTINGS['host'])


def run():
    _connect_db()
    total_marked = 0
    now = datetime.now(timezone.utc)
    ten_minutes_ago = now - timedelta(minutes=10)

    try:
        print("inside the script")

        for study in Study.objects(status='active'):
            print(f"inside the study {study.id}")

            # Find responses that have been in progress for more than 10 min since creation
            stale_responses = StudyResponse.objects(
                study=study,
              
                is_abandoned=False,  is_completed=False,
                is_in_progress=True,
                last_activity__lt=ten_minutes_ago
            )

            count = 0
            for resp in stale_responses:
                # Use mark_abandoned method for proper count updates
                resp.mark_abandoned(reason="Auto-abandoned due to inactivity (>10 minutes)")
                resp.save()
                count += 1

            if count:
                print(f"[{now.isoformat()}] Auto-abandoned {count} responses for study {study.id}")

            total_marked += count

    except Exception as e:
        print(f"[{datetime.now(timezone.utc).isoformat()}] ERROR: {e}")

    print(f"[{datetime.now(timezone.utc).isoformat()}] Done. Total marked abandoned: {total_marked}")


if __name__ == '__main__':
    run()


