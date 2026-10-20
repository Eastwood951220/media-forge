from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session, noload

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem


class ScrapingTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_task(self, task_id: uuid.UUID) -> ScrapingTask | None:
        return self.db.get(ScrapingTask, task_id)

    def get_item(self, item_id: uuid.UUID) -> ScrapingTaskItem | None:
        return self.db.get(ScrapingTaskItem, item_id)

    def list_items(self, task_id: uuid.UUID) -> list[ScrapingTaskItem]:
        return list(
            self.db.query(ScrapingTaskItem)
            .filter(ScrapingTaskItem.task_id == task_id)
            .order_by(ScrapingTaskItem.created_at.asc())
            .all()
        )

    def pending_items(self, task_id: uuid.UUID) -> list[ScrapingTaskItem]:
        return list(
            self.db.query(ScrapingTaskItem)
            .filter(ScrapingTaskItem.task_id == task_id, ScrapingTaskItem.status == "pending")
            .order_by(ScrapingTaskItem.created_at.asc())
            .all()
        )

    def _task_query(self, *, created_by: uuid.UUID, status: str | None):
        query = (
            self.db.query(ScrapingTask)
            .options(noload(ScrapingTask.items))
            .filter(ScrapingTask.created_by == created_by)
        )
        if status:
            query = query.filter(ScrapingTask.status == status)
        return query

    def list_tasks(self, *, created_by: uuid.UUID, page: int, size: int, status: str | None) -> list[ScrapingTask]:
        return list(
            self._task_query(created_by=created_by, status=status)
            .order_by(ScrapingTask.created_at.desc(), ScrapingTask.id.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

    def count_tasks(self, *, created_by: uuid.UUID, status: str | None) -> int:
        return int(
            self._task_query(created_by=created_by, status=status)
            .with_entities(func.count(ScrapingTask.id))
            .scalar()
            or 0
        )

    def recompute_counts(self, task: ScrapingTask) -> None:
        items = list(task.items or [])
        task.total_count = len(items)
        task.success_count = sum(1 for item in items if item.status == "success")
        task.failed_count = sum(1 for item in items if item.status == "failed")
        task.skipped_count = sum(1 for item in items if item.status == "skipped")
