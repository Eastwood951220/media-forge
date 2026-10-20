from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.tasks.repository import ScrapingTaskRepository
from shared.database.models.content import Movie

MAX_TASK_ITEMS = 500
TERMINAL_STATUSES = {"success", "partial_failed", "failed", "cancelled"}


class ScrapingTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ScrapingTaskRepository(db)

    def create_task(
        self,
        movie_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        *,
        config: dict,
    ) -> ScrapingTask:
        if not movie_ids:
            raise ValueError("至少选择一部电影")
        if len(movie_ids) > MAX_TASK_ITEMS:
            raise ValueError(f"单个任务最多 {MAX_TASK_ITEMS} 部电影")

        deduped: list[uuid.UUID] = []
        for movie_id in movie_ids:
            if movie_id not in deduped:
                deduped.append(movie_id)

        movies = self.db.query(Movie).filter(Movie.id.in_(deduped)).all()
        by_id = {movie.id: movie for movie in movies}
        missing = [str(movie_id) for movie_id in deduped if movie_id not in by_id]
        if missing:
            raise ValueError(f"电影不存在: {', '.join(missing)}")

        now = datetime.now(timezone.utc)
        task = ScrapingTask(
            status="queued",
            total_count=len(deduped),
            created_by=user_id,
            queued_at=now,
            config_snapshot={
                "scrape_root": config.get("scrape_root", ""),
                "media_root": config.get("media_root", "/media"),
                "metadata_sources": list(config.get("metadata_sources") or []),
            },
        )
        self.db.add(task)
        self.db.flush()
        for movie_id in deduped:
            movie = by_id[movie_id]
            self.db.add(ScrapingTaskItem(
                task_id=task.id,
                movie_id=movie.id,
                movie_code=movie.code or "",
                movie_title=movie.source_name or "",
                status="pending",
            ))
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_task(self, task_id: uuid.UUID, user_id: uuid.UUID) -> ScrapingTask:
        task = self.repository.get_task(task_id)
        if task is None or task.created_by != user_id:
            raise LookupError("任务不存在")
        return task

    def list_tasks(self, *, user_id: uuid.UUID, page: int, size: int, status: str | None) -> list[ScrapingTask]:
        return self.repository.list_tasks(created_by=user_id, page=page, size=size, status=status)

    def count_tasks(self, *, user_id: uuid.UUID, status: str | None) -> int:
        return self.repository.count_tasks(created_by=user_id, status=status)

    def cancel_task(self, task_id: uuid.UUID, user_id: uuid.UUID) -> ScrapingTask:
        task = self.get_task(task_id, user_id)
        if task.status in TERMINAL_STATUSES:
            raise ValueError("当前状态不能取消")
        task.cancel_requested = True
        if task.status == "queued":
            for item in self.repository.pending_items(task.id):
                item.status = "skipped"
                item.error_message = "任务已取消"
            task.status = "cancelled"
            task.finished_at = datetime.now(timezone.utc)
            self.repository.recompute_counts(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def retry_task(self, task_id: uuid.UUID, user_id: uuid.UUID, *, config: dict) -> ScrapingTask:
        task = self.get_task(task_id, user_id)
        if task.status not in {"failed", "partial_failed", "cancelled"}:
            raise ValueError("只有失败、部分失败或已取消的任务可以重试")
        movie_ids = [
            item.movie_id
            for item in self.repository.list_items(task.id)
            if item.status in {"failed", "skipped"}
        ]
        if not movie_ids:
            raise ValueError("没有可重试的电影")
        return self.create_task(movie_ids, user_id, config=config)
