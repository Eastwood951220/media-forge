from __future__ import annotations

from backend.app.schemas.crawl_task import CrawlTaskListItem, CrawlTaskRead, TaskUrlListItem


def serialize_task(task, latest_run=None) -> CrawlTaskRead:
    data = CrawlTaskRead.model_validate(task)
    data._id = data.id
    if latest_run is not None:
        data.last_run_at = latest_run.created_at
        data.last_run_status = latest_run.status
    return data


def serialize_task_list_item(task) -> CrawlTaskListItem:
    """Serialize a task into the lightweight list-item schema (no runtime fields)."""
    return CrawlTaskListItem(
        id=task.id,
        name=task.name,
        storage_location=task.storage_location,
        is_skip=task.is_skip,
        urls=[
            TaskUrlListItem(
                id=u.id,
                position=u.position,
                url=u.url,
                url_type=u.url_type,
                has_magnet=u.has_magnet,
                has_chinese_sub=u.has_chinese_sub,
                url_name=u.url_name,
            )
            for u in task.urls
        ],
    )
