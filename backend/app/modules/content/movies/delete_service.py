from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.modules.content.movies.storage_status import (
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORED,
    set_movie_storage_status,
)
from shared.database.models.content import Movie, MovieMagnet

logger = logging.getLogger(__name__)

MovieDeleteMode = Literal["database_only", "cloud_only", "database_and_cloud"]
MOVIE_DELETE_MODES = {"database_only", "cloud_only", "database_and_cloud"}


class UnsupportedMovieDeleteMode(ValueError):
    pass


class CloudMovieDeleteError(RuntimeError):
    def __init__(self, failed_folders: list[dict]) -> None:
        super().__init__("删除云存储文件夹失败")
        self.failed_folders = failed_folders


@dataclass
class MovieDeleteResult:
    deleted_movies: int = 0
    deleted_magnets: int = 0
    updated_movies: int = 0
    cloud_deleted_folders: list[str] = field(default_factory=list)
    cloud_missing_folders: list[str] = field(default_factory=list)
    cloud_failed_folders: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "deleted_movies": self.deleted_movies,
            "deleted_magnets": self.deleted_magnets,
            "updated_movies": self.updated_movies,
            "cloud_deleted_folders": self.cloud_deleted_folders,
            "cloud_missing_folders": self.cloud_missing_folders,
            "cloud_failed_folders": self.cloud_failed_folders,
        }


def collect_cloud_delete_folders(movie: Movie, *, storage_location_filter: str | None = None) -> list[str]:
    summary = dict(movie.storage_summary or {})
    folders: list[str] = []

    for item in summary.get("locations") or []:
        if not isinstance(item, dict):
            continue
        if storage_location_filter and str(item.get("storage_location") or "") != storage_location_filter:
            continue
        target_folder = str(item.get("target_folder") or "").strip()
        path = str(item.get("path") or "").strip()
        if target_folder:
            folders.append(target_folder)
        elif path:
            folders.append(_folder_from_path(path))

    for path in summary.get("tasks") or []:
        if isinstance(path, str) and path.strip():
            folder = _folder_from_path(path.strip())
            if _path_matches_storage_location(folder, storage_location_filter):
                folders.append(folder)

    for path in summary.get("target_folders") or []:
        if isinstance(path, str) and path.strip() and _path_matches_storage_location(path, storage_location_filter):
            folders.append(str(PurePosixPath(path.strip())))

    return _dedupe_paths(folders)


def delete_movies(
    *,
    db: Session,
    movies: list[Movie],
    mode: MovieDeleteMode,
    provider=None,
    storage_location_filter: str | None = None,
) -> MovieDeleteResult:
    if mode not in MOVIE_DELETE_MODES:
        raise UnsupportedMovieDeleteMode(f"Unsupported movie delete mode: {mode}")
    if mode in {"cloud_only", "database_and_cloud"} and provider is None:
        raise ValueError("删除云存储需要 CloudDrive provider")

    result = MovieDeleteResult()
    if mode in {"cloud_only", "database_and_cloud"}:
        _delete_cloud_folders_for_movies(
            movies=movies,
            provider=provider,
            result=result,
            storage_location_filter=storage_location_filter,
        )
        if result.cloud_failed_folders:
            raise CloudMovieDeleteError(result.cloud_failed_folders)

    if mode == "cloud_only":
        for movie in movies:
            remaining_locations = _remaining_locations_after_cloud_delete(
                movie,
                storage_location_filter=storage_location_filter,
            )
            set_movie_storage_status(
                movie,
                STORAGE_STATUS_STORED if remaining_locations else STORAGE_STATUS_NOT_STORED,
                source="movie_delete_cloud_only",
                locations=remaining_locations,
            )
            result.updated_movies += 1
        db.flush()
        return result

    if mode in {"database_only", "database_and_cloud"}:
        for movie in movies:
            magnet_count = int(
                db.query(MovieMagnet)
                .filter(MovieMagnet.movie_id == movie.id)
                .count()
            )
            result.deleted_magnets += magnet_count
            db.delete(movie)
            result.deleted_movies += 1
        db.flush()
    return result


def _delete_cloud_folders_for_movies(
    *,
    movies: list[Movie],
    provider,
    result: MovieDeleteResult,
    storage_location_filter: str | None,
) -> None:
    folders = _dedupe_paths([
        folder
        for movie in movies
        for folder in collect_cloud_delete_folders(movie, storage_location_filter=storage_location_filter)
    ])
    for folder in folders:
        try:
            provider.delete_file(folder)
            result.cloud_deleted_folders.append(folder)
        except Exception as exc:
            if _is_missing_cloud_path_error(exc):
                result.cloud_missing_folders.append(folder)
                continue
            result.cloud_failed_folders.append({"path": folder, "error": str(exc)})


def _folder_from_path(path: str) -> str:
    normalized = PurePosixPath(path)
    if normalized.suffix:
        return str(normalized.parent)
    return str(normalized)


def _dedupe_paths(paths: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(PurePosixPath(path))
        if not normalized or normalized == "." or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _is_missing_cloud_path_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(token in message for token in ["not found", "不存在", "文件不存在", "目录不存在", "404"])


def _path_matches_storage_location(path: str, storage_location_filter: str | None) -> bool:
    if not storage_location_filter:
        return True
    parts = [part for part in PurePosixPath(path).parts if part not in {"", "/"}]
    return storage_location_filter in parts


def _remaining_locations_after_cloud_delete(movie: Movie, *, storage_location_filter: str | None) -> list[dict]:
    locations = [
        item
        for item in (movie.storage_summary or {}).get("locations") or []
        if isinstance(item, dict)
    ]
    if not storage_location_filter:
        return []
    return [
        item
        for item in locations
        if str(item.get("storage_location") or "") != storage_location_filter
    ]
