from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.modules.content.movies.storage_locations import build_movie_storage_target_folders, target_folder_specs_from_subtask
from backend.app.modules.content.movies.storage_scan import scan_movie_storage_locations
from shared.database.models.content import Movie

STORAGE_STATUS_NOT_STORED = "not_stored"
STORAGE_STATUS_STORING = "storing"
STORAGE_STATUS_STORED = "stored"
STORAGE_STATUSES = {
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORING,
    STORAGE_STATUS_STORED,
}


@dataclass
class MovieStorageSyncResult:
    movie_id: str
    status: str
    found_count: int
    checked_targets: list[str]
    locations: list[dict]


def normalized_movie_storage_status(movie: Movie) -> str:
    summary = dict(movie.storage_summary or {})
    status = str(summary.get("storage_status") or summary.get("last_status") or "")
    if status == "completed":
        return STORAGE_STATUS_STORED
    if status in {"queued", "running", "pending", "waiting_download", "moving"}:
        return STORAGE_STATUS_STORING
    if status in STORAGE_STATUSES:
        return status
    return STORAGE_STATUS_NOT_STORED


def set_movie_storage_status(
    movie: Movie,
    status: str,
    *,
    source: str,
    locations: list[dict] | None = None,
    main_task_id: str | None = None,
    sub_task_id: str | None = None,
    storage_mode: str | None = None,
) -> None:
    if status not in STORAGE_STATUSES:
        raise ValueError(f"Unsupported storage status: {status}")
    summary = dict(movie.storage_summary or {})
    if locations is not None:
        summary["locations"] = _dedupe_locations(locations)
    else:
        summary.setdefault("locations", [])
    summary["storage_status"] = status
    summary["last_status"] = status
    summary["status_source"] = source
    summary["synced_at"] = datetime.now(timezone.utc).isoformat()
    if main_task_id:
        summary["last_main_task_id"] = main_task_id
    if sub_task_id:
        summary["last_sub_task_id"] = sub_task_id
    if storage_mode:
        summary["storage_mode"] = storage_mode
    movie.storage_summary = summary


def sync_movie_storage_status(
    *,
    db: Session,
    movie: Movie,
    provider,
    config: dict,
    source: str,
    target_folders: list[dict] | None = None,
    main_task_id: str | None = None,
    sub_task_id: str | None = None,
    storage_mode: str | None = None,
) -> MovieStorageSyncResult:
    folders = target_folders if target_folders is not None else build_movie_storage_target_folders(db, movie, config)
    checked_targets, found_locations = scan_movie_storage_locations(movie, provider, config, folders, source)
    status = STORAGE_STATUS_STORED if found_locations else STORAGE_STATUS_NOT_STORED
    set_movie_storage_status(
        movie,
        status,
        source=source,
        locations=found_locations,
        main_task_id=main_task_id,
        sub_task_id=sub_task_id,
        storage_mode=storage_mode,
    )
    return MovieStorageSyncResult(
        movie_id=str(movie.id),
        status=status,
        found_count=len(found_locations),
        checked_targets=checked_targets,
        locations=found_locations,
    )


def _dedupe_locations(locations: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for location in locations:
        path = str(location.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        deduped.append(location)
    return deduped
