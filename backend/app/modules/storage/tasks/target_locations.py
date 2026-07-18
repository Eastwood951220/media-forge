from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie


def resolve_target_locations(
    db: Session,
    movie: Movie,
    source: str,
    selected_storage_location: str | None,
    storage_mode: str = "single",
) -> list[str]:
    locations: list[str] = []
    for task_id in movie.source_task_ids or []:
        try:
            parsed_id = uuid.UUID(str(task_id)) if not isinstance(task_id, uuid.UUID) else task_id
        except (ValueError, TypeError):
            continue
        crawl_task = db.get(CrawlTask, parsed_id)
        if crawl_task and crawl_task.storage_location and crawl_task.storage_location not in locations:
            locations.append(crawl_task.storage_location)

    if not locations:
        return []
    if storage_mode == "multiple":
        return locations
    if source == "single" and selected_storage_location and selected_storage_location in locations:
        return [selected_storage_location]
    if source == "batch":
        return [locations[0]]
    return locations
