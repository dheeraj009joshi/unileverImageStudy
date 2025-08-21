"""
One-time migration: normalize DBRef ids to strings for all references.

Context:
- Primary keys were migrated to string `_id` values
- Some references (DBRef) may still store `uuid.UUID` in `$id`
- This script rewrites those references to use string ids, avoiding deref errors

Usage:
  1) Activate venv
     source venv/bin/activate
  2) Run with your Flask app settings loaded (so dotenv is picked up):
     python3 scripts/migrate_ref_ids_to_string.py
"""

import os
import uuid
from dotenv import load_dotenv
from mongoengine import connect, get_db
from bson.dbref import DBRef


def to_str_id(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        return value
    # Try to coerce
    try:
        return str(value)
    except Exception:
        return value


def migrate_study_response_refs(db):
    col = db['study_responses']
    fixed = 0
    for doc in col.find({}, {'study': 1}):
        ref = doc.get('study')
        if isinstance(ref, DBRef) and isinstance(ref.id, uuid.UUID):
            new_ref = DBRef(ref.collection, to_str_id(ref.id))
            col.update_one({'_id': doc['_id']}, {'$set': {'study': new_ref}})
            fixed += 1
    return fixed


def migrate_user_studies_list(db):
    col = db['users']
    fixed = 0
    for doc in col.find({}, {'studies': 1}):
        studies = doc.get('studies') or []
        changed = False
        new_list = []
        for ref in studies:
            if isinstance(ref, DBRef) and isinstance(ref.id, uuid.UUID):
                new_list.append(DBRef(ref.collection, to_str_id(ref.id)))
                changed = True
            else:
                new_list.append(ref)
        if changed:
            col.update_one({'_id': doc['_id']}, {'$set': {'studies': new_list}})
            fixed += 1
    return fixed


def migrate_task_session_refs(db):
    col = db['task_sessions']
    fixed = 0
    for doc in col.find({}, {'study_response': 1}):
        ref = doc.get('study_response')
        if isinstance(ref, DBRef) and isinstance(ref.id, uuid.UUID):
            new_ref = DBRef(ref.collection, to_str_id(ref.id))
            col.update_one({'_id': doc['_id']}, {'$set': {'study_response': new_ref}})
            fixed += 1
    return fixed


def main():
    load_dotenv()
    mongo_uri = os.environ.get('MONGODB_URI') or 'mongodb://localhost:27017/iped_system'
    connect(host=mongo_uri)
    db = get_db()

    print('Starting reference id migration (UUID -> string)...')
    fixed_sr = migrate_study_response_refs(db)
    fixed_users = migrate_user_studies_list(db)
    fixed_ts = migrate_task_session_refs(db)

    print(f'Updated StudyResponse.study refs: {fixed_sr}')
    print(f'Updated User.studies lists: {fixed_users}')
    print(f'Updated TaskSession.study_response refs: {fixed_ts}')
    print('Migration complete.')


if __name__ == '__main__':
    main()


