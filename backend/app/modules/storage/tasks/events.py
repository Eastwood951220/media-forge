from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.schemas import make_realtime_event
from shared.database.models.content import Movie


def publish_storage_main_updated(main_task: StorageMainTask) -> None:
    event_bus.publish(make_realtime_event(
        event="storage.main.updated",
        scope="storage.main",
        owner_id=str(main_task.created_by),
        resource_id=str(main_task.id),
        payload={
            "id": str(main_task.id),
            "status": main_task.status,
            "total_count": main_task.total_count,
            "success_count": main_task.success_count,
            "failed_count": main_task.failed_count,
            "skipped_count": main_task.skipped_count,
        },
    ))


def publish_storage_sub_updated(owner_id: str, subtask: StorageSubTask) -> None:
    event_bus.publish(make_realtime_event(
        event="storage.sub.updated",
        scope="storage.sub",
        owner_id=owner_id,
        resource_id=str(subtask.id),
        payload={
            "id": str(subtask.id),
            "main_task_id": str(subtask.main_task_id),
            "movie_id": str(subtask.movie_id),
            "status": subtask.status,
            "step": subtask.step,
            "error_message": subtask.error_message,
        },
    ))


def publish_storage_sub_log_appended(owner_id: str, subtask_id: str, entry: dict) -> None:
    event_bus.publish(make_realtime_event(
        event="storage.sub.log.appended",
        scope="storage.sub",
        owner_id=owner_id,
        resource_id=subtask_id,
        payload=entry,
    ))


def publish_movie_storage_updated(db: Session, owner_id: str, movie_id) -> None:
    movie = db.get(Movie, movie_id)
    if movie is None:
        return
    event_bus.publish(make_realtime_event(
        event="movie.storage.updated",
        scope="movie",
        owner_id=owner_id,
        resource_id=str(movie.id),
        payload={"movie_id": str(movie.id), "storage_summary": movie.storage_summary or {}},
    ))
