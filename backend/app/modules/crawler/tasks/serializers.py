from __future__ import annotations

from backend.app.schemas.crawl_task import CrawlTaskRead


def serialize_task(task, latest_run=None) -> CrawlTaskRead:
    data = CrawlTaskRead.model_validate(task)
    data._id = data.id
    if latest_run is not None:
        data.last_run_at = latest_run.created_at
        data.last_run_status = latest_run.status
    return data
