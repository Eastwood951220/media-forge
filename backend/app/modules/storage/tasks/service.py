from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.tasks.policies import generate_default_alias
from backend.app.modules.storage.tasks.repository import StorageTaskRepository
from backend.app.modules.storage.worker.runner import ensure_storage_worker_started
from backend.app.modules.storage.tasks.schemas import (
    StorageBatchPushRequest,
    StorageMainTaskResponse,
    StorageSinglePushRequest,
)
from shared.database.models.content import Movie


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

    def to_main_response(self, task: StorageMainTask) -> dict:
        return {
            "id": str(task.id),
            "alias": task.alias,
            "display_name": task.display_name,
            "source": task.source,
            "storage_mode": task.storage_mode,
            "status": task.status,
            "total_count": task.total_count,
            "success_count": task.success_count,
            "failed_count": task.failed_count,
            "skipped_count": task.skipped_count,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "error_message": task.error_message,
        }

    def to_subtask_response(self, task: StorageSubTask) -> dict:
        return {
            "id": str(task.id),
            "main_task_id": str(task.main_task_id),
            "movie_id": str(task.movie_id),
            "movie_code": task.movie_code,
            "movie_title": task.movie_title,
            "status": task.status,
            "step": task.step,
            "storage_mode": task.storage_mode,
            "selected_storage_location": task.selected_storage_location,
            "target_locations": task.target_locations or [],
            "download_path": task.download_path,
            "target_paths": task.target_paths or [],
            "magnet_attempts": task.magnet_attempts or [],
            "current_magnet_id": str(task.current_magnet_id) if task.current_magnet_id else None,
            "current_magnet_url": task.current_magnet_url,
            "renamed_files": task.renamed_files or [],
            "moved_files": task.moved_files or [],
            "skipped_files": task.skipped_files or [],
            "result": task.result or {},
            "skip_reason": task.skip_reason,
            "error_message": task.error_message,
            "queued_at": task.queued_at.isoformat() if task.queued_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }

    def _create_main_task(
        self,
        movie_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        source: str,
        alias: str | None,
        storage_mode: str,
        selected_storage_location: str | None,
    ) -> StorageMainTask:
        if storage_mode not in {"single", "multiple"}:
            raise ValueError("storage_mode must be single or multiple")

        now = datetime.now(timezone.utc)
        sequence = self.repository.count_today_main_tasks() + 1
        final_alias = alias or generate_default_alias(now, sequence)

        main_task = StorageMainTask(
            alias=final_alias,
            display_name=final_alias,
            source=source,
            storage_mode=storage_mode,
            status="queued",
            total_count=0,
            created_by=user_id,
            queued_at=now,
            config_snapshot=self.config_service.get_raw_config(),
        )
        self.db.add(main_task)
        self.db.flush()

        movies = self._load_movies(movie_ids)
        movie_map = {m.id: m for m in movies}

        has_queued = False
        for movie_id in movie_ids:
            movie = movie_map.get(movie_id)
            subtask = self._create_subtask(
                main_task=main_task,
                movie=movie,
                movie_id=movie_id,
                source=source,
                storage_mode=storage_mode,
                selected_storage_location=selected_storage_location,
                user_id=user_id,
            )
            if subtask.status == "queued":
                has_queued = True

        self.repository.recompute_counts(main_task)
        self.db.commit()
        self.db.refresh(main_task)

        if has_queued and self.runtime is not None:
            self.runtime.enqueue_main_task(str(main_task.id))
            ensure_storage_worker_started(
                self.runtime,
                self.config_service.provider_factory,
                self.config_service,
            )

        return main_task

    def _load_movies(self, movie_ids: list[uuid.UUID]) -> list[Movie]:
        stmt = select(Movie).where(Movie.id.in_(movie_ids)).options(selectinload(Movie.magnets))
        return list(self.db.scalars(stmt).all())

    def _create_subtask(
        self,
        main_task: StorageMainTask,
        movie: Movie | None,
        movie_id: uuid.UUID,
        source: str,
        storage_mode: str,
        selected_storage_location: str | None,
        user_id: uuid.UUID,
    ) -> StorageSubTask:
        skip_reason = self._classify_skip(movie, movie_id)
        if skip_reason:
            subtask = StorageSubTask(
                main_task_id=main_task.id,
                movie_id=movie_id,
                movie_code=getattr(movie, "code", "") or "",
                movie_title=getattr(movie, "source_name", "") or "",
                status="skipped",
                step="prepare",
                storage_mode=storage_mode,
                skip_reason=skip_reason,
            )
            self.db.add(subtask)
            self.db.flush()
            return subtask

        # Resolve target locations from source tasks
        target_locations = self._resolve_target_locations(movie, source, selected_storage_location)

        subtask = StorageSubTask(
            main_task_id=main_task.id,
            movie_id=movie_id,
            movie_code=movie.code or "",
            movie_title=movie.source_name or "",
            status="queued",
            step="prepare",
            storage_mode=storage_mode,
            selected_storage_location=selected_storage_location,
            target_locations=target_locations,
            download_path="",
        )
        self.db.add(subtask)
        self.db.flush()

        # Update movie storage_summary
        self._update_movie_storage_summary(movie, main_task, subtask, storage_mode, user_id)

        return subtask

    def _classify_skip(self, movie: Movie | None, movie_id: uuid.UUID) -> str | None:
        if movie is None:
            return "movie_not_found"
        if movie.marked:
            return "movie_marked"
        if not movie.magnets:
            return "no_magnets"
        usable = [m for m in movie.magnets if m.magnet_url]
        if not usable:
            return "no_magnet_url"
        return None

    def _resolve_target_locations(
        self,
        movie: Movie,
        source: str,
        selected_storage_location: str | None,
    ) -> list[str]:
        # Get locations from source crawl tasks
        locations: list[str] = []
        from backend.app.models.crawl_task import CrawlTask

        for task_id in (movie.source_task_ids or []):
            # Ensure task_id is a UUID (CompatibleARRAY may return strings on SQLite)
            try:
                parsed_id = uuid.UUID(str(task_id)) if not isinstance(task_id, uuid.UUID) else task_id
            except (ValueError, TypeError):
                continue
            crawl_task = self.db.get(CrawlTask, parsed_id)
            if crawl_task and crawl_task.storage_location:
                loc = crawl_task.storage_location
                if loc not in locations:
                    locations.append(loc)

        if not locations:
            return []

        if source == "single" and selected_storage_location:
            if selected_storage_location in locations:
                return [selected_storage_location]

        if source == "batch":
            return [locations[0]]

        return locations

    def _update_movie_storage_summary(
        self,
        movie: Movie,
        main_task: StorageMainTask,
        subtask: StorageSubTask,
        storage_mode: str,
        user_id: uuid.UUID,
    ) -> None:
        summary = dict(movie.storage_summary or {})
        summary.update({
            "last_main_task_id": str(main_task.id),
            "last_sub_task_id": str(subtask.id),
            "last_status": subtask.status,
            "storage_mode": storage_mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        movie.storage_summary = summary
