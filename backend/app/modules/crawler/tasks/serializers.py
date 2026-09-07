from __future__ import annotations

from backend.app.schemas.crawl_task import CrawlTaskListItem, CrawlTaskRead, TaskTagRead, TaskUrlListItem


def _latest_run_counts(latest_run) -> tuple[int | None, int | None]:
    if latest_run is None:
        return None, None
    result = latest_run.result or {}
    total = next((result[key] for key in ("total", "total_found", "total_tasks") if key in result), None)
    failed = next((result[key] for key in ("failed", "failed_count", "total_failed") if key in result), None)
    return (
        int(total) if isinstance(total, int | float) else None,
        int(failed) if isinstance(failed, int | float) else None,
    )


def serialize_task(task, latest_run=None) -> CrawlTaskRead:
    data = CrawlTaskRead.model_validate(task)
    data._id = data.id
    if latest_run is not None:
        data.last_run_at = latest_run.created_at
        data.last_run_status = latest_run.status
    return data


def serialize_task_list_item(task, latest_run=None) -> CrawlTaskListItem:
    """Serialize a task into the lightweight list-item schema, adding the latest-run summary when available."""
    last_run_total, last_run_failed = _latest_run_counts(latest_run)
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
        tags=[TaskTagRead.model_validate(tag) for tag in task.tags],
        last_run_status=latest_run.status if latest_run is not None else None,
        last_run_at=latest_run.created_at if latest_run is not None else None,
        last_run_total=last_run_total,
        last_run_failed=last_run_failed,
    )
