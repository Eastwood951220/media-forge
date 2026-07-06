import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask

logger = logging.getLogger(__name__)
_worker_lock = threading.Lock()
_worker_running = False


def cleanup_interrupted_storage_tasks(db: Session, runtime) -> int:
    runtime.cleanup_runtime()
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


def _worker_loop(runtime, provider_factory, config_service) -> None:
    global _worker_running
    try:
        while True:
            task_id = runtime.claim_next_main_task()
            if task_id is None:
                with _worker_lock:
                    task_id = runtime.claim_next_main_task()
                    if task_id is None:
                        _worker_running = False
                        return
            try:
                process_main_task(runtime, provider_factory, config_service, task_id)
            except Exception:
                logger.exception("Storage worker failed while processing main task %s", task_id)
    except Exception:
        logger.exception("Storage worker loop crashed")
        with _worker_lock:
            _worker_running = False
        raise


def process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool:
    from backend.app.modules.storage.worker.task_processor import process_main_task as process

    return process(runtime, provider_factory, config_service, task_id)
