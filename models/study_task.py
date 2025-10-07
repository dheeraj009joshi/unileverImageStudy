from mongoengine import Document, ReferenceField, StringField, ListField, DictField, DateTimeField
import uuid
from datetime import datetime


class StudyPanelistTasks(Document):
    """Stores the generated tasks for a single panelist of a study.

    This avoids storing a huge nested structure on the Study document and keeps each
    panelist's tasks in a dedicated, size-safe document.
    """

    # Use UUID for _id (avoid ObjectId)
    _id = StringField(primary_key=True, default=lambda: str(uuid.uuid4()))

    # During step3a we may not have a Study yet; allow draft-scoped storage too
    study = ReferenceField('Study', required=False)
    draft = ReferenceField('StudyDraft', required=False)
    panelist_id = StringField(required=True, max_length=32)
    tasks = ListField(DictField())  # Each item mirrors one task dict used in participation

    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'study_panelist_tasks',
        'indexes': [
            {'fields': ['study', 'panelist_id'],  'sparse': True},
            {'fields': ['draft', 'panelist_id'],  'sparse': True},
            'study',
            'draft'
        ]
    }

    def save(self, *args, **kwargs):  # noqa: D401
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)


