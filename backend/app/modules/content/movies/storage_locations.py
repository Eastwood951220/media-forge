from __future__ import annotations

import uuid
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie

KNOWN_STORAGE_SUFFIXES = ("", "-C", "-U", "-UC")


def build_movie_storage_target_folders(db: Session, movie: Movie, config: dict) -> list[dict]:
    target_root = str(config.get("target_folder") or "/Movies").rstrip("/")
    code = str(movie.code or "").upper()
    if not code:
        return []
    storage_locations = _storage_locations_for_movie(db, movie)
    folders: list[dict] = []
    seen: set[str] = set()
    for storage_location in storage_locations:
        for suffix in KNOWN_STORAGE_SUFFIXES:
            folder_name = f"{code}{suffix}"
            target_folder = f"{target_root}/{storage_location}/{folder_name}"
            if target_folder in seen:
                continue
            seen.add(target_folder)
            folders.append({
                "target_folder": target_folder,
                "storage_location": storage_location,
                "folder_name": folder_name,
            })
    return folders


def target_folder_specs_from_subtask(subtask) -> list[dict]:
    specs: list[dict] = []
    target_locations = list(getattr(subtask, "target_locations", None) or [])
    for index, target_folder in enumerate(list(getattr(subtask, "target_paths", None) or [])):
        specs.append({
            "target_folder": target_folder,
            "storage_location": target_locations[index] if index < len(target_locations) else "",
            "folder_name": PurePosixPath(str(target_folder)).name,
        })
    return specs


def _storage_locations_for_movie(db: Session, movie: Movie) -> list[str]:
    locations: list[str] = []
    for raw_task_id in movie.source_task_ids or []:
        try:
            task_id = raw_task_id if isinstance(raw_task_id, uuid.UUID) else uuid.UUID(str(raw_task_id))
        except (TypeError, ValueError):
            continue
        crawl_task = db.get(CrawlTask, task_id)
        if crawl_task and crawl_task.storage_location and crawl_task.storage_location not in locations:
            locations.append(crawl_task.storage_location)
    return locations
