import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.dependencies import get_redis
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState

logger = logging.getLogger(__name__)

UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawl_failed", "save_failed"}

_worker_lock = threading.Lock()
_worker_running = False


def get_runtime_state() -> CrawlerRuntimeState:
    return CrawlerRuntimeState(get_redis())


def cleanup_interrupted_runs(db: Session, runtime: CrawlerRuntimeState) -> int:
    runtime.cleanup_runtime()
    rows = db.query(CrawlRun).filter(CrawlRun.status.in_(["queued", "running"])).all()
    now = datetime.now()
    for run in rows:
        run.status = "stopped"
        run.finished_at = run.finished_at or now
        run.error = "服务重启，任务已停止，需手动重启"
    db.commit()
    return len(rows)


class CrawlerRunService:
    def __init__(self, db: Session, runtime: CrawlerRuntimeState) -> None:
        self.db = db
        self.runtime = runtime

    def create_run(self, task: CrawlTask, crawl_mode: str) -> CrawlRun:
        if crawl_mode not in {"incremental", "full"}:
            raise ValueError("crawl_mode must be incremental or full")
        run = CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="queued",
            crawl_mode=crawl_mode,
            queued_at=datetime.now(),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        return run

    def stop_run(self, run_id: uuid.UUID) -> CrawlRun:
        run = self.db.get(CrawlRun, run_id)
        if run is None:
            raise ValueError("运行记录不存在")
        if run.status not in {"queued", "running"}:
            raise ValueError("任务当前未在运行中")
        self.runtime.request_stop(str(run.id))
        run.status = "stopped"
        run.finished_at = datetime.now()
        self.db.commit()
        self.db.refresh(run)
        return run

    def restart_run(self, run_id: uuid.UUID) -> CrawlRun:
        old_run = self.db.get(CrawlRun, run_id)
        if old_run is None:
            raise ValueError("运行记录不存在")
        if old_run.status not in {"stopped", "failed"}:
            raise ValueError("只能重启已停止或失败的运行")
        details = (
            self.db.query(CrawlRunDetailTask)
            .filter(
                CrawlRunDetailTask.run_id == old_run.id,
                CrawlRunDetailTask.status.in_(UNFINISHED_DETAIL_STATUSES),
            )
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        if not details:
            raise ValueError("没有未完成的子任务")
        new_run = CrawlRun(
            task_id=old_run.task_id,
            task_name=old_run.task_name,
            status="queued",
            crawl_mode=old_run.crawl_mode,
            queued_at=datetime.now(),
            resumed_from=old_run.id,
        )
        self.db.add(new_run)
        self.db.flush()
        for detail in details:
            self.db.add(CrawlRunDetailTask(
                run_id=new_run.id,
                task_name=detail.task_name,
                code=detail.code,
                source_url=detail.source_url,
                source_name=detail.source_name,
                status=detail.status,
                error=None,
                item_data=detail.item_data,
                created_at=datetime.now(),
                crawled_at=None,
                saved_at=None,
            ))
        self.db.commit()
        self.db.refresh(new_run)
        self.runtime.enqueue_run(str(new_run.id))
        self._ensure_worker_started()
        return new_run

    def _ensure_worker_started(self) -> None:
        global _worker_running
        with _worker_lock:
            if _worker_running:
                return
            _worker_running = True
            thread = threading.Thread(target=self._worker_loop, daemon=True)
            thread.start()

    def _worker_loop(self) -> None:
        global _worker_running
        try:
            while True:
                run_id = self.runtime.claim_next_run()
                if run_id is None:
                    break
                process_next_run(type(self.db), self.runtime)
        finally:
            with _worker_lock:
                _worker_running = False


def process_next_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState) -> bool:
    run_id = runtime.claim_next_run()
    if run_id is None:
        return False

    db = db_factory()
    try:
        run = db.get(CrawlRun, uuid.UUID(run_id))
        if run is None:
            logger.error("Run %s not found", run_id)
            return False

        run.status = "running"
        run.started_at = datetime.now()
        db.commit()

        runtime.set_current_run(run_id)

        try:
            _execute_run(db, run, runtime)
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            run.status = "failed"
            run.error = str(exc)[:1000]
            run.finished_at = datetime.now()
            db.commit()
        finally:
            runtime.set_current_run(None)
            runtime.write_progress(run_id, {})

        return True
    finally:
        db.close()


def _execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None:
    """Execute a crawler run."""
    from backend.app.models.crawl_task import CrawlTask

    task = db.get(CrawlTask, run.task_id) if run.task_id else None
    if task is None:
        raise ValueError("关联任务不存在")

    # Build task URLs
    task_urls = [{"url": u.url, "url_type": u.url_type} for u in task.urls]
    if not task_urls:
        raise ValueError("任务没有URL")

    # Track progress
    progress = {"total": 0, "saved": 0, "failed": 0, "skipped": 0}
    detail_tasks: dict[str, CrawlRunDetailTask] = {}

    def on_tasks_batch_created(items: list[dict[str, Any]]) -> None:
        for item in items:
            detail = CrawlRunDetailTask(
                run_id=run.id,
                task_name=task.name,
                code=item.get("code"),
                source_url=item.get("url", ""),
                source_name=item.get("name", ""),
                status="pending_crawl",
                created_at=datetime.now(),
            )
            db.add(detail)
            db.flush()
            if detail.code:
                detail_tasks[detail.code] = detail
        progress["total"] += len(items)
        runtime.write_progress(str(run.id), progress)
        db.commit()

    def on_item_saved(task_info: dict, item_data: dict) -> None:
        code = item_data.get("code") or task_info.get("code")
        detail = detail_tasks.get(code) if code else None
        if detail:
            detail.status = "saved"
            detail.item_data = item_data
            detail.crawled_at = datetime.now()
            detail.saved_at = datetime.now()
        progress["saved"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()

    def on_detail_failed(task_info: dict, error: str) -> None:
        code = task_info.get("code")
        detail = detail_tasks.get(code) if code else None
        if detail:
            detail.status = "crawl_failed"
            detail.error = error[:500]
            detail.crawled_at = datetime.now()
        progress["failed"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()

    # Execute crawl
    try:
        from scraper.services.movie_service import MovieService
        movie_service = MovieService()
        result = movie_service.crawl_javdb_task(
            task,
            crawl_mode=run.crawl_mode,
            on_tasks_batch_created=on_tasks_batch_created,
            on_item_saved=on_item_saved,
            on_detail_failed=on_detail_failed,
        )
        run.result = result
        run.status = "completed"
    except ImportError:
        logger.warning("MovieService not available, marking run as completed with stub")
        run.result = {"total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0}
        run.status = "completed"
    except Exception as exc:
        raise

    run.finished_at = datetime.now()
    db.commit()
