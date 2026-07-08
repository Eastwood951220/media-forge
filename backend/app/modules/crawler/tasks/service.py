from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.modules.crawler.runs.schemas import CrawlRunRead, RunCreateRequest
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.tasks.delete_service import UnsupportedDeleteMode, delete_task
from backend.app.modules.crawler.tasks.errors import raise_task_integrity_error
from backend.app.modules.crawler.tasks.provider import open_delete_provider
from backend.app.modules.crawler.tasks.runtime_status import (
    can_delete_task_runtime_status,
    get_task_runtime_status,
)
from backend.app.modules.crawler.tasks.serializers import serialize_task
from backend.app.modules.crawler.tasks.validation import check_urls_unique, ensure_delete_mode_supported
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskStats,
    CrawlTaskUpdate,
)

logger = logging.getLogger(__name__)


class CrawlerTaskService:
    """Application service for crawler task operations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CrawlTaskRepository(db)

    def list_tasks(
        self,
        owner_id: uuid.UUID,
        *,
        skip: int | None = None,
        limit: int | None = None,
        keyword: str | None = None,
    ) -> dict:
        rows = self.repo.get_by_owner(owner_id, skip=skip, limit=limit, keyword=keyword)
        total = self.repo.count_by_owner(owner_id, keyword=keyword)
        latest_runs = self.repo.get_latest_runs_by_task_ids([row.id for row in rows])
        return {
            "rows": [
                serialize_task(row, latest_runs.get(row.id)).model_dump(mode="json")
                for row in rows
            ],
            "total": total,
        }

    def get_stats(self, owner_id: uuid.UUID) -> dict:
        return CrawlTaskStats(**self.repo.get_summary_stats(owner_id)).model_dump()

    def task_dict(self, owner_id: uuid.UUID) -> dict:
        return self.repo.get_dict_by_owner(owner_id)

    def get_task(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return serialize_task(task).model_dump(mode="json")

    def run_task(
        self,
        task_id: uuid.UUID,
        data: RunCreateRequest,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if task.is_skip:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")
        try:
            run = CrawlerRunService(self.db, get_runtime_state()).create_run(task, data.crawl_mode)
        except Exception as exc:
            self.db.rollback()
            logger.exception("Create crawler run failed")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
        return CrawlRunRead.model_validate(run).model_dump(mode="json")

    def create_task(self, data: CrawlTaskCreate, owner_id: uuid.UUID) -> dict:
        if self.repo.get_by_name(owner_id, data.name):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{data.name}' 已存在")
        check_urls_unique(data.urls)
        try:
            created = self.repo.create_with_urls(
                owner_id=owner_id,
                name=data.name,
                storage_location=data.storage_location,
                is_skip=data.is_skip,
                urls=data.urls,
            )
        except IntegrityError as exc:
            self.db.rollback()
            raise_task_integrity_error(exc, name=data.name)
        return serialize_task(created).model_dump(mode="json")

    def update_task(
        self,
        task_id: uuid.UUID,
        data: CrawlTaskUpdate,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        update_data = data.model_dump(exclude_unset=True, exclude={"urls"})
        if "name" in update_data:
            duplicate = self.repo.get_by_name(owner_id, update_data["name"])
            if duplicate and duplicate.id != task.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{update_data['name']}' 已存在")

        for field, value in update_data.items():
            setattr(task, field, value)

        if data.urls is not None:
            check_urls_unique(data.urls)
            self.repo.replace_urls(task, data.urls)

        try:
            updated = self.repo.update(task)
        except IntegrityError as exc:
            self.db.rollback()
            raise_task_integrity_error(exc, name=update_data.get("name") or task.name)
        return serialize_task(updated).model_dump(mode="json")

    def delete_task(
        self,
        task_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        mode: str = "task_only",
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        runtime_snapshot = get_task_runtime_status(self.db, task_id, owner_id)
        if runtime_snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if not can_delete_task_runtime_status(runtime_snapshot.runtime_status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只有空闲中的任务才能删除",
            )

        ensure_delete_mode_supported(mode)

        run_ids = [
            str(row.id)
            for row in self.db.query(CrawlRun.id)
            .filter(CrawlRun.task_id == task_id)
            .all()
        ]

        try:
            with open_delete_provider(mode) as provider:
                result = delete_task(self.db, task_id, mode=mode, provider=provider)
                get_runtime_state().purge_runs(run_ids)
        except UnsupportedDeleteMode as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        return result.to_dict()
