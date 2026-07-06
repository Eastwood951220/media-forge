from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.tasks.creation import StorageTaskCreator
from backend.app.modules.storage.tasks.logs import delete_storage_subtask_log
from backend.app.modules.storage.tasks.policies import generate_default_alias
from backend.app.modules.storage.tasks.repository import StorageTaskRepository
from backend.app.modules.storage.tasks.schemas import (
    StorageBatchPushRequest,
    StorageMainTaskResponse,
    StorageSinglePushRequest,
)
from backend.app.modules.storage.tasks.serializers import (
    storage_main_task_to_dict,
    storage_subtask_to_dict,
)
from backend.app.modules.storage.worker.runner import ensure_storage_worker_started


class StorageTaskService:
    def __init__(
        self,
        db: Session,
        config_service: StorageConfigService,
        runtime=None,
    ) -> None:
        self.db = db
        self.config_service = config_service
        self.runtime = runtime
        self.repository = StorageTaskRepository(db)

    def generate_next_alias(self) -> str:
        now = datetime.now(timezone.utc)
        sequence = self.repository.count_today_main_tasks() + 1
        return generate_default_alias(now, sequence)

    def create_single_push(self, body: StorageSinglePushRequest, user_id: uuid.UUID) -> StorageMainTask:
        return self._create_main_task(
            movie_ids=[body.movie_id],
            user_id=user_id,
            source="single",
            alias=body.alias,
            storage_mode=body.storage_mode,
            selected_storage_location=body.selected_storage_location,
        )

    def create_batch_push(self, body: StorageBatchPushRequest, user_id: uuid.UUID) -> StorageMainTask:
        return self._create_main_task(
            movie_ids=body.movie_ids,
            user_id=user_id,
            source="batch",
            alias=body.alias,
            storage_mode=body.storage_mode,
            selected_storage_location=None,
        )

    def stop_main_task(self, task_id: uuid.UUID) -> StorageMainTask:
        task = self.repository.get_main(task_id)
        if task is None:
            raise ValueError("存储任务不存在")
        if task.status not in {"queued", "running", "stopping"}:
            raise ValueError("当前状态不能停止")
        task.status = "stopping"
        if self.runtime is not None:
            self.runtime.request_stop(str(task.id))
        self.db.commit()
        self.db.refresh(task)

        from backend.app.modules.storage.tasks.events import publish_storage_main_updated
        publish_storage_main_updated(task)

        return task

    def restart_main_task(self, task_id: uuid.UUID) -> StorageMainTask:
        task = self.repository.get_main(task_id)
        if task is None:
            raise ValueError("存储任务不存在")
        if task.status not in {"stopped", "failed"}:
            raise ValueError("只能重启已停止或失败的存储任务")
        for subtask in task.subtasks:
            if subtask.status in {"queued", "failed", "running"}:
                subtask.status = "queued"
                subtask.step = "prepare"
                subtask.error_message = None
                subtask.started_at = None
                subtask.finished_at = None
        task.status = "queued"
        task.started_at = None
        task.finished_at = None
        task.error_message = None
        self.repository.recompute_counts(task)
        if self.runtime is not None:
            self.runtime.clear_stop(str(task.id))
            self.runtime.enqueue_main_task(str(task.id))
            ensure_storage_worker_started(
                self.runtime,
                self.config_service.provider_factory,
                self.config_service,
            )
        self.db.commit()
        self.db.refresh(task)

        from backend.app.modules.storage.tasks.events import publish_storage_main_updated
        publish_storage_main_updated(task)

        return task

    def delete_main_task(self, task_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        task = self.repository.get_main(task_id)
        if task is None or task.created_by != user_id:
            raise LookupError("存储任务不存在")
        if task.status in {"queued", "running", "stopping"}:
            raise ValueError("运行中的存储任务不能删除，请先停止任务")

        subtask_ids = self.repository.list_subtask_ids(task.id)
        task_id_text = str(task.id)
        owner_id = str(task.created_by)
        deleted_log_count = 0
        for subtask_id in subtask_ids:
            if delete_storage_subtask_log(str(subtask_id)):
                deleted_log_count += 1

        self.repository.delete_main_task(task)
        self.db.commit()

        from backend.app.modules.storage.tasks.events import publish_storage_main_deleted
        publish_storage_main_deleted(owner_id, task_id_text)

        return {
            "id": task_id_text,
            "deleted_subtask_count": len(subtask_ids),
            "deleted_log_count": deleted_log_count,
        }

    def to_main_response(self, task: StorageMainTask) -> dict:
        return storage_main_task_to_dict(task)

    def to_subtask_response(self, task: StorageSubTask) -> dict:
        return storage_subtask_to_dict(task)

    def _create_main_task(
        self,
        movie_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        source: str,
        alias: str | None,
        storage_mode: str,
        selected_storage_location: str | None,
    ) -> StorageMainTask:
        creator = StorageTaskCreator(
            db=self.db,
            repository=self.repository,
            config_service=self.config_service,
        )
        main_task = creator.create_main_task(
            movie_ids=movie_ids,
            user_id=user_id,
            source=source,
            alias=alias,
            storage_mode=storage_mode,
            selected_storage_location=selected_storage_location,
        )
        self.db.commit()
        self.db.refresh(main_task)

        has_queued = any(subtask.status == "queued" for subtask in main_task.subtasks)
        if has_queued and self.runtime is not None:
            self.runtime.enqueue_main_task(str(main_task.id))
            ensure_storage_worker_started(
                self.runtime,
                self.config_service.provider_factory,
                self.config_service,
            )

        return main_task
