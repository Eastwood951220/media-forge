from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from shared.database.session import get_session_factory
from backend.app.models.crawl_run import CrawlRun
from backend.app.modules.crawler.runtime.details import reset_unfinished_detail_tasks_to_pending
from backend.app.modules.crawler.runtime.events import publish_run_updated
from backend.app.modules.crawler.runtime.executor import execute_run
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.tasks.runtime_status import publish_task_status_updated

logger = logging.getLogger(__name__)
_worker_lock = threading.Lock()
_worker_running = False


def ensure_crawler_worker_started(runtime: CrawlerRuntimeState) -> None:
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
        thread = threading.Thread(target=_worker_loop, args=(runtime,), daemon=True)
        thread.start()


def _worker_loop(runtime: CrawlerRuntimeState) -> None:
    global _worker_running
    try:
        while True:
            run_id = runtime.claim_next_run()
            if run_id is None:
                break
            process_run(get_session_factory(), runtime, run_id)
    finally:
        with _worker_lock:
            _worker_running = False


def cleanup_interrupted_runs(db: Session, runtime: CrawlerRuntimeState) -> int:
    runtime.cleanup_runtime()
    rows = db.query(CrawlRun).filter(CrawlRun.status.in_(["queued", "running"])).all()
    now = datetime.now()
    for run in rows:
        run.status = "stopped"
        run.finished_at = run.finished_at or now
        run.error = "服务重启，任务已停止，需手动重启"
        reset_unfinished_detail_tasks_to_pending(db, run)
        publish_task_status_updated(db, run)
    db.commit()
    return len(rows)


def process_next_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState) -> bool:
    run_id = runtime.claim_next_run()
    if run_id is None:
        return False
    return process_run(db_factory, runtime, run_id)


def process_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState, run_id: str) -> bool:
    db = db_factory()
    try:
        run = db.get(CrawlRun, uuid.UUID(run_id))
        if run is None:
            logger.error("Run %s not found", run_id)
            return False

        run.status = "running"
        run.started_at = datetime.now()
        db.commit()
        publish_run_updated(db, run)

        runtime.set_current_run(run_id)

        try:
            execute_run(db, run, runtime)
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            run.status = "failed"
            run.error = str(exc)[:1000]
            run.finished_at = datetime.now()
            db.commit()
            publish_run_updated(db, run)
        finally:
            runtime.set_current_run(None)
            runtime.write_progress(run_id, {})
            runtime.clear_stop(run_id)

        return True
    finally:
        db.close()
