from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.content.movies.storage_status import (
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORING,
    set_movie_storage_status,
)
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.tasks.policies import generate_default_alias
from backend.app.modules.storage.tasks.repository import StorageTaskRepository
from backend.app.modules.storage.tasks.skip_rules import classify_storage_skip
from backend.app.modules.storage.tasks.target_locations import resolve_target_locations
from shared.database.models.content import Movie


class StorageTaskCreator:
    def __init__(self, db: Session, repository: StorageTaskRepository, config_service) -> None:
        self.db = db
        self.repository = repository
        self.config_service = config_service

    def create_main_task(
        self,
        *,
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
        movie_map = {movie.id: movie for movie in movies}
        for movie_id in movie_ids:
            self._create_subtask(
                main_task=main_task,
                movie=movie_map.get(movie_id),
                movie_id=movie_id,
                source=source,
                storage_mode=storage_mode,
                selected_storage_location=selected_storage_location,
                user_id=user_id,
            )

        self.repository.recompute_counts(main_task)
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
        skip_reason = classify_storage_skip(movie)
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
            write_storage_subtask_log(
                str(subtask.id),
                "INFO",
                "存储子任务已跳过",
                {
                    "main_task_id": str(main_task.id),
                    "movie_id": str(movie_id),
                    "skip_reason": skip_reason,
                },
            )
            return subtask

        # Resolve target locations from source tasks
        target_locations = resolve_target_locations(self.db, movie, source, selected_storage_location)

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

        write_storage_subtask_log(
            str(subtask.id),
            "INFO",
            "存储子任务已创建并等待执行",
            {
                "main_task_id": str(main_task.id),
                "movie_id": str(movie_id),
                "storage_mode": storage_mode,
                "target_locations": target_locations,
            },
        )

        # Update movie storage_summary
        self._update_movie_storage_summary(movie, main_task, subtask, storage_mode, user_id)

        return subtask

    def _update_movie_storage_summary(
        self,
        movie: Movie,
        main_task: StorageMainTask,
        subtask: StorageSubTask,
        storage_mode: str,
        user_id: uuid.UUID,
    ) -> None:
        status = STORAGE_STATUS_STORING if subtask.status == "queued" else STORAGE_STATUS_NOT_STORED
        set_movie_storage_status(
            movie,
            status,
            source="storage_push",
            main_task_id=str(main_task.id),
            sub_task_id=str(subtask.id),
            storage_mode=storage_mode,
        )
