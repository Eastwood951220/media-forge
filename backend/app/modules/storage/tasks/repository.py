from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask


class StorageTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_main(self, task_id: uuid.UUID) -> StorageMainTask | None:
        return self.db.get(StorageMainTask, task_id)

    def count_today_main_tasks(self) -> int:
        return int(self.db.query(func.count(StorageMainTask.id)).scalar() or 0)

    def recompute_counts(self, main_task: StorageMainTask) -> None:
        subtasks = list(main_task.subtasks or [])
        main_task.total_count = len(subtasks)
        main_task.success_count = sum(1 for task in subtasks if task.status == "completed")
        main_task.failed_count = sum(1 for task in subtasks if task.status == "failed")
        main_task.skipped_count = sum(1 for task in subtasks if task.status == "skipped")
