from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from backend.app.models.scraping_task import ScrapingTask
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


def get_scraping_config() -> dict:
    from backend.app.modules.scraping.config import ScrapingConfigService

    return ScrapingConfigService().get_raw_config()


def _open_session():
    from shared.database.session import get_session_factory

    return get_session_factory()()


def ensure_scraping_worker_started() -> None:
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
    threading.Thread(target=_worker_loop, daemon=True, name="scraping-worker").start()


def _worker_loop() -> None:
    global _worker_running
    try:
        while True:
            db = _open_session()
            try:
                task = _claim_next_task(db)
            except Exception:
                logger.exception("Failed to claim a scraping task")
                task = None
            finally:
                db.close()
            if task is None:
                break
            try:
                run_task(task.id)
            except Exception:
                logger.exception("Scraping task failed: %s", task)
    finally:
        with _worker_lock:
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
        task.status = "running"
        if task.started_at is None:
            task.started_at = datetime.now(timezone.utc)
        db.commit()
        publish_scraping_task_updated(task)
        config = dict(task.config_snapshot or {}) or get_scraping_config()

        items = [item for item in task.items if item.status == "pending"]
        cancelled = False
        for item in items:
            db.refresh(task)
            if task.cancel_requested:
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
            _recompute(task, db)
            publish_scraping_item_updated(str(task.created_by), item)
            if item.status == "success" and item.movie_id is not None:
                movie = db.get(Movie, item.movie_id)
                if movie is not None:
                    publish_movie_scraping_updated(
                        str(task.created_by),
                        str(movie.id),
                        movie.scraping_status,
                        movie.scraping_checked_at.isoformat() if movie.scraping_checked_at else None,
                    )

        _recompute(task, db)
        if cancelled:
            for item in task.items:
                if item.status in {"pending", "running"}:
                    item.status = "skipped"
                    item.error_message = "任务已取消"
            task.status = "cancelled"
            _recompute(task, db)
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


def _recompute(task: ScrapingTask, db) -> None:
    db.flush()
    items = list(task.items)
    task.total_count = len(items)
    task.success_count = sum(1 for item in items if item.status == "success")
    task.failed_count = sum(1 for item in items if item.status == "failed")
    task.skipped_count = sum(1 for item in items if item.status == "skipped")
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
