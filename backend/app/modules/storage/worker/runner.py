import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.scraping.trigger import schedule_strm_after_storage_drain

logger = logging.getLogger(__name__)
_worker_lock = threading.Lock()
_worker_running = False


def cleanup_interrupted_storage_tasks(db: Session, runtime) -> int:
    try:
        runtime.cleanup_runtime()
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to cleanup Redis runtime state (Redis may be unavailable)", exc_info=True
        )
    rows = db.query(StorageMainTask).filter(StorageMainTask.status.in_(["queued", "running", "stopping"])).all()
    now = datetime.now(timezone.utc)
    for main in rows:
        main.status = "stopped"
        main.finished_at = main.finished_at or now
        main.error_message = "服务重启，存储任务已停止，需手动重启"
        for subtask in main.subtasks:
            if subtask.status == "running":
                subtask.status = "queued"
                subtask.step = "prepare"
                subtask.error_message = None
    db.commit()
    return len(rows)


def ensure_storage_worker_started(runtime, provider_factory, config_service) -> None:
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
        thread = threading.Thread(
            target=_worker_loop,
            args=(runtime, provider_factory, config_service),
            daemon=True,
            name="storage-worker",
        )
        thread.start()


def is_storage_worker_idle() -> bool:
    with _worker_lock:
        return not _worker_running


def _worker_loop(runtime, provider_factory, config_service) -> None:
    global _worker_running
    processed_any = False
    try:
        while True:
            task_id = runtime.claim_next_main_task()
            if task_id is None:
                with _worker_lock:
                    task_id = runtime.claim_next_main_task()
                    if task_id is None:
                        _worker_running = False
                        break
            processed_any = True
            try:
                process_main_task(runtime, provider_factory, config_service, task_id)
            except Exception:
                logger.exception("Storage worker failed while processing main task %s", task_id)
    except Exception:
        logger.exception("Storage worker loop crashed")
        with _worker_lock:
            _worker_running = False
        raise

    if processed_any:
        try:
            schedule_strm_after_storage_drain(
                runtime,
                is_worker_idle=is_storage_worker_idle,
            )
        except Exception:
            logger.exception("Failed to schedule STRM generation after storage drain")


def process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool:
    from backend.app.modules.storage.worker.task_processor import process_main_task as process

    return process(runtime, provider_factory, config_service, task_id)
