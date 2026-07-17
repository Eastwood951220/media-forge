from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.service import get_runtime_state
from backend.app.modules.crawler.runtime.worker import ensure_crawler_worker_started
from shared.database.models.content import Movie

MAGNET_REFRESH_TASK_NAME = "磁力更新"


def _ensure_display_task(db: Session, owner_id: uuid.UUID) -> CrawlTask:
    task = db.scalar(
        select(CrawlTask).where(
            CrawlTask.owner_id == owner_id,
            CrawlTask.name == MAGNET_REFRESH_TASK_NAME,
        )
    )
    if task is not None:
        return task
    task = CrawlTask(
        name=MAGNET_REFRESH_TASK_NAME,
        storage_location="",
        owner_id=owner_id,
        is_skip=True,
        status="idle",
    )
    db.add(task)
    db.flush()
    return task


def _movie_belongs_to_user(movie: Movie, owner_task_ids: set[uuid.UUID]) -> bool:
    owner_task_id_strs = {str(task_id) for task_id in owner_task_ids}
    return any(str(task_id) in owner_task_id_strs for task_id in (movie.source_task_ids or []))


def _owner_task_ids(db: Session, owner_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(CrawlTask.id).where(CrawlTask.owner_id == owner_id)).all())


def create_magnet_refresh_run(db: Session, owner_id: uuid.UUID, movie_ids: list[uuid.UUID]) -> CrawlRun:
    if not movie_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="movie_ids 不能为空")
    owner_task_ids = _owner_task_ids(db, owner_id)
    movies = db.scalars(select(Movie).where(Movie.id.in_(movie_ids))).all()
    valid_movies = [movie for movie in movies if _movie_belongs_to_user(movie, owner_task_ids)]
    if not valid_movies:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可更新的电影")

    display_task = _ensure_display_task(db, owner_id)
    run = CrawlRun(
        task_id=display_task.id,
        task_name=display_task.name,
        status="queued",
        crawl_mode="magnet_refresh",
        queued_at=datetime.now(),
        result={"movie_ids": [str(movie.id) for movie in valid_movies], "magnet_refresh": True},
    )
    db.add(run)
    db.flush()
    for movie in valid_movies:
        has_source_url = bool(str(movie.source_url or "").strip())
        db.add(CrawlRunDetailTask(
            run_id=run.id,
            task_name=display_task.name,
            code=movie.code,
            source_url=movie.source_url or "",
            source_name=movie.source_name or "",
            source_url_name=MAGNET_REFRESH_TASK_NAME,
            task_url=movie.source_url or "",
            task_final_url=movie.source_url or "",
            task_url_type="magnet_refresh",
            status="pending_crawl" if has_source_url else "skipped",
            error=None if has_source_url else "missing_source_url",
            item_data={"movie_id": str(movie.id), "magnet_refresh": True},
            created_at=datetime.now(),
        ))
    db.commit()
    db.refresh(run)

    runtime = get_runtime_state()
    runtime.enqueue_run(str(run.id))
    ensure_crawler_worker_started(runtime)
    return run
