import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log  # noqa: F401
from backend.app.modules.storage.worker.movie_sync import sync_movie_storage_after_subtask
from backend.app.modules.storage.worker.provider_session import (
    close_storage_provider,
    mark_provider_creation_failed,
    open_storage_provider,
)

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


def _publish_main_with_recomputed_counts(db: Session, repository, main_task: StorageMainTask) -> None:
    from backend.app.modules.storage.tasks.events import publish_storage_main_updated

    repository.recompute_counts(main_task)
    db.flush()
    db.commit()
    publish_storage_main_updated(main_task)


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
        logger.info("Storage main task %s claimed by worker", task_id)

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

            write_storage_subtask_log(
                str(subtask.id),
                "INFO",
                "存储 worker 开始执行子任务",
                {
                    "main_task_id": str(main_task.id),
                    "movie_id": str(subtask.movie_id),
                    "step": subtask.step,
                },
            )

            # Create provider from config
            try:
                client, provider = open_storage_provider(provider_factory, config)
            except Exception as exc:
                mark_provider_creation_failed(subtask, str(main_task.id), exc)
                has_failure = True
                _publish_main_with_recomputed_counts(db, repository, main_task)
                continue

            context = StorageWorkerContext(
                db=db,
                main_task=main_task,
                subtask=subtask,
                config=config,
                provider=provider,
                owner_id=str(main_task.created_by),
            )

            try:
                execute_subtask_pipeline(context)
                context.log(
                    "INFO",
                    "存储子任务执行结束",
                    {
                        "main_task_id": str(main_task.id),
                        "status": subtask.status,
                        "step": subtask.step,
                    },
                    step=subtask.step,
                    event="subtask_finished",
                )
                context.publish_subtask()
                sync_movie_storage_after_subtask(db, context)
            except Exception as exc:
                subtask.status = "failed"
                subtask.error_message = str(exc)
                subtask.finished_at = datetime.now(timezone.utc)
                has_failure = True
                context.log(
                    "ERROR",
                    f"存储子任务执行失败: {exc}",
                    {
                        "main_task_id": str(main_task.id),
                        "step": subtask.step,
                    },
                    step=subtask.step,
                    event="subtask_failed",
                )
                context.publish_subtask()
                sync_movie_storage_after_subtask(db, context)
                logger.exception("Storage subtask %s failed", subtask.id)

            _publish_main_with_recomputed_counts(db, repository, main_task)

            close_storage_provider(client)

        repository.recompute_counts(main_task)

        if runtime.should_stop(task_id):
            main_task.status = "stopped"
        elif has_failure:
            main_task.status = "failed"
        else:
            main_task.status = "completed"

        main_task.finished_at = datetime.now(timezone.utc)
        _publish_main_with_recomputed_counts(db, repository, main_task)

    return True
