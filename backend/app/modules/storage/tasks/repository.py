from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, noload

from backend.app.models.storage_task import StorageMainTask, StorageSubTask


class StorageTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_main(self, task_id: uuid.UUID) -> StorageMainTask | None:
        return self.db.get(StorageMainTask, task_id)

    def count_today_main_tasks(self) -> int:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(
            self.db.query(func.count(StorageMainTask.id))
            .filter(StorageMainTask.created_at >= today_start)
            .scalar()
            or 0
        )

    def recompute_counts(self, main_task: StorageMainTask) -> None:
        subtasks = list(main_task.subtasks or [])
        main_task.total_count = len(subtasks)
        main_task.success_count = sum(1 for task in subtasks if task.status == "completed")
        main_task.failed_count = sum(1 for task in subtasks if task.status == "failed")
        main_task.skipped_count = sum(1 for task in subtasks if task.status == "skipped")

    def _main_task_query(
        self,
        *,
        created_by: uuid.UUID,
        status: str | None,
        keyword: str | None,
    ):
        query = (
            self.db.query(StorageMainTask)
            .options(noload(StorageMainTask.subtasks))
            .filter(StorageMainTask.created_by == created_by)
        )
        if status:
            query = query.filter(StorageMainTask.status == status)
        if keyword:
            query = query.filter(StorageMainTask.alias.ilike(f"%{keyword}%"))
        return query

    def list_main_tasks(
        self,
        *,
        created_by: uuid.UUID,
        page: int,
        size: int,
        status: str | None,
        keyword: str | None,
    ) -> tuple[list[StorageMainTask], bool]:
        rows = (
            self._main_task_query(created_by=created_by, status=status, keyword=keyword)
            .order_by(StorageMainTask.created_at.desc(), StorageMainTask.id.desc())
            .offset((page - 1) * size)
            .limit(size + 1)
            .all()
        )
        return rows[:size], len(rows) > size

    def count_main_tasks(
        self,
        *,
        created_by: uuid.UUID,
        status: str | None,
        keyword: str | None,
    ) -> int:
        return int(
            self._main_task_query(created_by=created_by, status=status, keyword=keyword)
            .with_entities(func.count(StorageMainTask.id))
            .scalar()
            or 0
        )

    def list_subtasks(
        self,
        main_task_id: uuid.UUID,
        *,
        page: int,
        limit: int,
    ) -> tuple[list[StorageSubTask], int]:
        query = self.db.query(StorageSubTask).filter(StorageSubTask.main_task_id == main_task_id)
        total = query.count()
        rows = query.order_by(StorageSubTask.created_at.asc()).offset((page - 1) * limit).limit(limit).all()
        return rows, total

    def get_subtask(self, subtask_id: uuid.UUID) -> StorageSubTask | None:
        return self.db.get(StorageSubTask, subtask_id)

    def list_subtask_ids(self, main_task_id: uuid.UUID) -> list[uuid.UUID]:
        rows = (
            self.db.query(StorageSubTask.id)
            .filter(StorageSubTask.main_task_id == main_task_id)
            .order_by(StorageSubTask.created_at.asc())
            .all()
        )
        return [row[0] for row in rows]

    def delete_main_task(self, main_task: StorageMainTask) -> None:
        self.db.delete(main_task)
