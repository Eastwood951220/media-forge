import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.storage_task import StorageMainTask, StorageSubTask

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
                break
            process_main_task(runtime, provider_factory, config_service, task_id)
    finally:
        with _worker_lock:
            _worker_running = False


def process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool:
    from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState
    from backend.app.modules.storage.tasks.events import publish_storage_main_updated
    from backend.app.modules.storage.tasks.repository import StorageTaskRepository
    from backend.app.modules.storage.worker.context import StorageWorkerContext
    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline
    from shared.database.session import get_session_factory

    factory = get_session_factory()
    with factory() as db:
        repository = StorageTaskRepository(db)
        import uuid
        main_task = repository.get_main(uuid.UUID(task_id))
        if main_task is None:
            return False

        main_task.status = "running"
        main_task.started_at = main_task.started_at or datetime.now(timezone.utc)
        db.commit()

        # Load config from snapshot
        config = dict(main_task.config_snapshot or {})
        config.setdefault("video_extensions", [".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov"])
        config.setdefault("minimum_video_size_mb", 100)

        has_failure = False
        for subtask in main_task.subtasks:
            if subtask.status != "queued":
                continue

            if runtime.should_stop(task_id):
                break

            # Create provider from config
            try:
                client = provider_factory.create(config)
                from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway
                provider = CloudDrive2Gateway(client)
            except Exception as exc:
                subtask.status = "failed"
                subtask.error_message = f"创建 CloudDrive2 客户端失败: {exc}"
                subtask.finished_at = datetime.now(timezone.utc)
                has_failure = True
                db.commit()
                continue

            context = StorageWorkerContext(
                db=db,
                main_task=main_task,
                subtask=subtask,
                config=config,
                provider=provider,
            )

            try:
                execute_subtask_pipeline(context)
            except Exception as exc:
                subtask.status = "failed"
                subtask.error_message = str(exc)
                subtask.finished_at = datetime.now(timezone.utc)
                has_failure = True
                logger.exception("Storage subtask %s failed", subtask.id)

            db.commit()
            publish_storage_main_updated(main_task)

            # Close client
            close = getattr(client, "close", None)
            if callable(close):
                close()

        repository.recompute_counts(main_task)

        if runtime.should_stop(task_id):
            main_task.status = "stopped"
        elif has_failure:
            main_task.status = "failed"
        else:
            main_task.status = "completed"

        main_task.finished_at = datetime.now(timezone.utc)
        db.commit()
        publish_storage_main_updated(main_task)

    return True
