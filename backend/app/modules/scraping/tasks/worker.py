from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.scraping.tasks.events import (
    publish_movie_scraping_updated,
    publish_scraping_item_updated,
    publish_scraping_task_updated,
)
from backend.app.modules.scraping.tasks.item_runner import run_item
from shared.database.models.content import Movie

logger = logging.getLogger(__name__)

_worker_lock = threading.Lock()
_worker_running = False
_worker_generation = 0


def get_scraping_config() -> dict:
    from backend.app.modules.scraping.config import ScrapingConfigService

    return ScrapingConfigService().get_raw_config()


def _open_session():
    from shared.database.session import get_session_factory

    return get_session_factory()()


def ensure_scraping_worker_started() -> None:
    global _worker_running, _worker_generation
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
        _worker_generation += 1
        generation = _worker_generation
    _spawn_worker(generation)


def _spawn_worker(generation: int) -> None:
    threading.Thread(
        target=_worker_loop,
        args=(generation,),
        daemon=True,
        name="scraping-worker",
    ).start()


def _claim_task() -> ScrapingTask | None:
    db = _open_session()
    try:
        return _claim_next_task(db)
    except Exception:
        logger.exception("Failed to claim a scraping task")
        return None
    finally:
        db.close()


def _final_claim_or_retire(generation: int) -> ScrapingTask | None:
    """Final claim attempt under the worker lock so no new task is lost.

    The flag is cleared only while holding the lock and only after the queue is
    confirmed empty; a task queued concurrently either gets claimed here or sees
    ``_worker_running`` false and starts a fresh worker.
    """
    global _worker_running
    with _worker_lock:
        task = _claim_task()
        if task is None and generation == _worker_generation:
            _worker_running = False
        return task


def _worker_loop(generation: int | None = None) -> None:
    global _worker_running
    if generation is None:
        generation = _worker_generation
    try:
        while True:
            task = _claim_task()
            if task is None:
                task = _final_claim_or_retire(generation)
                if task is None:
                    return
            try:
                run_task(task.id)
            except Exception:
                logger.exception("Scraping task failed: %s", task.id)
    finally:
        with _worker_lock:
            if generation == _worker_generation:
                _worker_running = False


def _claim_next_task(db) -> ScrapingTask | None:
    task = (
        db.query(ScrapingTask)
        .filter(ScrapingTask.status == "queued")
        .order_by(ScrapingTask.created_at.asc(), ScrapingTask.id.asc())
        .first()
    )
    if task is None:
        return None
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


def run_task(task_id: uuid.UUID) -> None:
    db = _open_session()
    try:
        task = db.get(ScrapingTask, task_id)
        if task is None:
            return
        task_id = task.id
        owner_id = str(task.created_by)
        task.status = "running"
        if task.started_at is None:
            task.started_at = datetime.now(timezone.utc)
        db.commit()
        publish_scraping_task_updated(task)
        config = dict(task.config_snapshot or {}) or get_scraping_config()

        items = [item for item in task.items if item.status == "pending"]
        cancelled = False
        for item in items:
            # Read only the cancellation flag: reloading the whole task (and its
            # items) for every item is O(n²) on large tasks.
            cancel_requested = db.execute(
                select(ScrapingTask.cancel_requested).where(ScrapingTask.id == task_id)
            ).scalar_one()
            if cancel_requested:
                cancelled = True
                break
            item.status = "running"
            db.commit()
            try:
                run_item(db, item, config=config)
            except Exception as exc:
                item.status = "failed"
                item.error_message = f"{type(exc).__name__}: {exc}"
            db.commit()
            _recompute(task, db, task_id=task_id)
            publish_scraping_item_updated(owner_id, item)
            if item.status == "success" and item.movie_id is not None:
                movie = db.get(Movie, item.movie_id)
                if movie is not None:
                    publish_movie_scraping_updated(
                        owner_id,
                        str(movie.id),
                        movie.scraping_status,
                        movie.scraping_checked_at.isoformat() if movie.scraping_checked_at else None,
                    )

        _recompute(task, db, task_id=task_id)
        if cancelled:
            for item in task.items:
                if item.status in {"pending", "running"}:
                    item.status = "skipped"
                    item.error_message = "任务已取消"
            task.status = "cancelled"
            _recompute(task, db, task_id=task_id)
        elif task.success_count > 0 and task.failed_count + task.skipped_count > 0:
            task.status = "partial_failed"
        elif task.success_count > 0:
            task.status = "success"
        elif task.failed_count + task.skipped_count > 0:
            task.status = "failed"
        else:
            task.status = "failed"
            task.error_message = "没有可刮削的电影"
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        publish_scraping_task_updated(task)
    finally:
        db.close()


def _recompute(task: ScrapingTask, db, *, task_id: uuid.UUID | None = None) -> None:
    db.flush()
    rows = db.execute(
        select(ScrapingTaskItem.status, func.count())
        .where(ScrapingTaskItem.task_id == (task_id if task_id is not None else task.id))
        .group_by(ScrapingTaskItem.status)
    ).all()
    counts = {status: count for status, count in rows}
    task.total_count = sum(counts.values())
    task.success_count = counts.get("success", 0)
    task.failed_count = counts.get("failed", 0)
    task.skipped_count = counts.get("skipped", 0)
    db.commit()


def cleanup_interrupted_scraping_tasks(db) -> int:
    rows = db.query(ScrapingTask).filter(ScrapingTask.status == "running").all()
    now = datetime.now(timezone.utc)
    for task in rows:
        task.status = "failed"
        task.finished_at = now
        task.error_message = "任务中断，需重试"
        for item in task.items:
            if item.status in {"pending", "running"}:
                item.status = "skipped"
                item.error_message = "任务中断，需重试"
    if rows:
        db.commit()
    return len(rows)
