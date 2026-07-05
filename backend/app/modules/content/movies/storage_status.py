from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie

STORAGE_STATUS_NOT_STORED = "not_stored"
STORAGE_STATUS_STORING = "storing"
STORAGE_STATUS_STORED = "stored"
STORAGE_STATUSES = {
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORING,
    STORAGE_STATUS_STORED,
}
KNOWN_STORAGE_SUFFIXES = ("", "-C", "-U", "-UC")


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
    checked_targets: list[str] = []
    found_locations: list[dict] = []
    for folder in folders:
        target_folder = str(folder["target_folder"])
        checked_targets.append(target_folder)
        try:
            entries = provider.list_files(target_folder)
        except Exception:
            entries = []
        for entry in entries:
            item = _remote_entry_to_dict(entry, target_folder)
            if _is_matching_video(movie, item, config):
                found_locations.append({
                    "path": item["path"],
                    "target_folder": target_folder,
                    "storage_location": str(folder.get("storage_location") or ""),
                    "file_name": item["name"],
                    "size": item["size"],
                    "exists": True,
                    "source": source,
                })
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


def _remote_entry_to_dict(entry, target_folder: str) -> dict:
    path = getattr(entry, "full_path", "") or getattr(entry, "fullPathName", "")
    name = getattr(entry, "name", "") or PurePosixPath(path).name
    if not path:
        path = str(PurePosixPath(target_folder) / name)
    return {
        "name": name,
        "path": path,
        "size": int(getattr(entry, "size", 0) or 0),
        "is_dir": bool(getattr(entry, "is_directory", False) or getattr(entry, "isDirectory", False)),
    }


def _is_matching_video(movie: Movie, item: dict, config: dict) -> bool:
    if item["is_dir"]:
        return False
    ext = PurePosixPath(item["name"]).suffix.lower()
    allowed_exts = {str(value).lower() for value in config.get("video_extensions", [".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov"])}
    if ext not in allowed_exts:
        return False
    min_bytes = int(config.get("minimum_video_size_mb", 100) or 100) * 1024 * 1024
    if int(item.get("size") or 0) < min_bytes:
        return False
    code = str(movie.code or "").upper()
    return bool(code and item["name"].upper().startswith(code))


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
