from __future__ import annotations

from backend.app.models.scraping_task import ScrapingTask, ScrapingTaskItem
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.schemas import make_realtime_event


def publish_scraping_task_updated(task: ScrapingTask) -> None:
    event_bus.publish(make_realtime_event(
        event="scraping.task.updated",
        scope="scraping.task",
        owner_id=str(task.created_by),
        resource_id=str(task.id),
        payload={
            "id": str(task.id),
            "status": task.status,
            "total_count": task.total_count,
            "success_count": task.success_count,
            "failed_count": task.failed_count,
            "skipped_count": task.skipped_count,
        },
    ))


def publish_scraping_item_updated(owner_id: str, item: ScrapingTaskItem) -> None:
    event_bus.publish(make_realtime_event(
        event="scraping.item.updated",
        scope="scraping.task",
        owner_id=str(owner_id),
        resource_id=str(item.id),
        payload={
            "id": str(item.id),
            "task_id": str(item.task_id),
            "status": item.status,
            "step": item.step,
            "source": item.source,
            "error_message": item.error_message,
        },
    ))


def publish_scraping_item_log_appended(owner_id: str, item_id: str, entry: dict) -> None:
    event_bus.publish(make_realtime_event(
        event="scraping.item.log.appended",
        scope="scraping.task",
        owner_id=str(owner_id),
        resource_id=item_id,
        payload=entry,
    ))


def publish_movie_scraping_updated(owner_id: str, movie_id: str, status: str | None, checked_at: str | None) -> None:
    event_bus.publish(make_realtime_event(
        event="movie.scraping.updated",
        scope="movie",
        owner_id=str(owner_id),
        resource_id=str(movie_id),
        payload={"movie_id": str(movie_id), "scraping_status": status, "scraping_checked_at": checked_at},
    ))
