from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy.orm import Session

from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from backend.app.modules.scraping.paths import (
    cloud_to_local,
    code_from_folder_name,
    local_to_cloud,
    normalize_code,
)
from shared.database.models.content import Movie

logger = logging.getLogger(__name__)

MAX_DEPTH = 8
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SCRAPED = "scraped"
NOT_SCRAPED = "not_scraped"
UNMATCHED_LIMIT = 50


@dataclass
class ScanSummary:
    folders_scanned: int = 0
    folders_with_strm: int = 0
    scraped_folders: int = 0
    not_scraped_folders: int = 0
    matched_movies: int = 0
    updated_movies: int = 0
    unmatched_folders: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "folders_scanned": self.folders_scanned,
            "folders_with_strm": self.folders_with_strm,
            "scraped_folders": self.scraped_folders,
            "not_scraped_folders": self.not_scraped_folders,
            "matched_movies": self.matched_movies,
            "updated_movies": self.updated_movies,
            "unmatched_folders": self.unmatched_folders,
            "duration_ms": self.duration_ms,
        }


def judge_folder(folder: Path) -> tuple[bool, bool, int]:
    folder = Path(folder)
    has_strm = False
    has_nfo = False
    image_count = 0
    try:
        for entry in os.scandir(folder):
            if not entry.is_file():
                continue
            name = entry.name.lower()
            if name.endswith(".strm"):
                has_strm = True
            elif name == "movie.nfo":
                has_nfo = True
            elif Path(name).suffix in IMAGE_EXTENSIONS:
                image_count += 1
    except OSError:
        logger.warning("Cannot read scraping folder: %s", folder, exc_info=True)
        return False, False, 0
    return has_strm, has_nfo, image_count


def iter_movie_folders(scrape_root: Path) -> Iterator[Path]:
    root = Path(scrape_root)
    root_depth = len(root.parts)
    for current, dirnames, _filenames in os.walk(root, followlinks=False):
        depth = len(Path(current).parts) - root_depth
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        has_strm, _has_nfo, _images = judge_folder(Path(current))
        if has_strm:
            yield Path(current)


def _stored_movies(db: Session) -> list[Movie]:
    movies = db.query(Movie).all()
    return [movie for movie in movies if normalized_movie_storage_status(movie) == "stored"]


def movie_target_folders(movie: Movie) -> list[str]:
    summary = dict(movie.storage_summary or {})
    result: list[str] = []
    for location in summary.get("locations") or []:
        if not isinstance(location, dict):
            continue
        target = str(location.get("target_folder") or "").strip()
        if target and target not in result:
            result.append(target)
    return result


def _apply_judgement(
    movie: Movie,
    *,
    has_strm: bool,
    has_nfo: bool,
    image_count: int,
    cloud_folder: str,
    checked_at: datetime,
) -> str:
    scraped = has_strm and has_nfo and image_count > 0
    movie.scraping_status = SCRAPED if scraped else NOT_SCRAPED
    movie.scraping_folder = cloud_folder
    movie.scraping_checked_at = checked_at
    return movie.scraping_status


def scan_directory(db: Session, config: dict[str, Any]) -> ScanSummary:
    started = datetime.now(timezone.utc)
    scrape_root = str(config.get("scrape_root") or "").strip()
    media_root = str(config.get("media_root") or "/media")
    summary = ScanSummary()

    if not scrape_root or not Path(scrape_root).is_dir():
        return summary

    candidate_folders = list(iter_movie_folders(Path(scrape_root)))
    summary.folders_with_strm = len(candidate_folders)

    # Count every visited folder; os.walk is repeated cheaply here because the
    # candidate generator does not expose the walk total.
    for _current, _dirnames, _filenames in os.walk(scrape_root):
        summary.folders_scanned += 1

    judgements: dict[str, tuple[bool, bool, int]] = {}
    for folder in candidate_folders:
        judgements[str(folder.resolve())] = judge_folder(folder)
        has_strm, has_nfo, image_count = judgements[str(folder.resolve())]
        if has_strm and has_nfo and image_count > 0:
            summary.scraped_folders += 1
        else:
            summary.not_scraped_folders += 1

    stored = _stored_movies(db)
    stored_by_code = {normalize_code(movie.code or ""): movie for movie in stored}
    assigned: dict[str, str] = {}

    # Exact pass: storage target folders that map under the media root.
    for movie in stored:
        for target in movie_target_folders(movie):
            local = cloud_to_local(scrape_root, media_root, target)
            if local is None:
                continue
            key = str(local.resolve())
            if key in judgements and key not in assigned:
                assigned[key] = str(movie.id)

    # Fallback pass: folder-name codes.
    for folder in candidate_folders:
        key = str(folder.resolve())
        if key in assigned:
            continue
        code = code_from_folder_name(folder.name)
        movie = stored_by_code.get(normalize_code(code or ""))
        if movie is not None and str(movie.id) not in assigned.values():
            assigned[key] = str(movie.id)

    checked_at = datetime.now(timezone.utc)
    updated = 0
    assigned_movie_ids: set[str] = set()
    for key, movie_id in assigned.items():
        movie = next((candidate for candidate in stored if str(candidate.id) == movie_id), None)
        if movie is None:
            continue
        has_strm, has_nfo, image_count = judgements[key]
        cloud = local_to_cloud(scrape_root, media_root, key) or ""
        _apply_judgement(
            movie,
            has_strm=has_strm,
            has_nfo=has_nfo,
            image_count=image_count,
            cloud_folder=cloud,
            checked_at=checked_at,
        )
        assigned_movie_ids.add(movie_id)
        updated += 1

    for movie in stored:
        if str(movie.id) in assigned_movie_ids:
            continue
        mapped = any(cloud_to_local(scrape_root, media_root, target) is not None for target in movie_target_folders(movie))
        if mapped:
            movie.scraping_status = NOT_SCRAPED
            movie.scraping_folder = None
            movie.scraping_checked_at = checked_at
            updated += 1

    for movie in db.query(Movie).all():
        if normalized_movie_storage_status(movie) == "stored":
            continue
        if movie.scraping_status is not None or movie.scraping_folder is not None or movie.scraping_checked_at is not None:
            movie.scraping_status = None
            movie.scraping_folder = None
            movie.scraping_checked_at = None
            updated += 1

    matched_keys = set(assigned)
    for folder in candidate_folders:
        if str(folder.resolve()) in matched_keys:
            continue
        if len(summary.unmatched_folders) < UNMATCHED_LIMIT:
            summary.unmatched_folders.append(str(folder))

    db.commit()
    summary.matched_movies = len(assigned)
    summary.updated_movies = updated
    summary.duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return summary


def refresh_movie_status(
    db: Session,
    movie: Movie,
    *,
    local_folder: Path | None = None,
    cloud_folder: str | None = None,
) -> str:
    if normalized_movie_storage_status(movie) != "stored":
        movie.scraping_status = None
        movie.scraping_folder = None
        movie.scraping_checked_at = None
        db.commit()
        return "not_stored"

    config = _current_scan_config()
    scrape_root = str(config.get("scrape_root") or "")
    media_root = str(config.get("media_root") or "/media")

    folder = local_folder
    cloud = cloud_folder or ""
    if folder is None:
        for target in movie_target_folders(movie):
            candidate = cloud_to_local(scrape_root, media_root, target)
            if candidate is not None and candidate.is_dir():
                folder = candidate
                cloud = target
                break
    if folder is None:
        return "not_scraped"

    has_strm, has_nfo, image_count = judge_folder(folder)
    cloud = cloud or local_to_cloud(scrape_root, media_root, folder) or ""
    status = _apply_judgement(
        movie,
        has_strm=has_strm,
        has_nfo=has_nfo,
        image_count=image_count,
        cloud_folder=cloud,
        checked_at=datetime.now(timezone.utc),
    )
    db.commit()
    return status


def _current_scan_config() -> dict[str, Any]:
    from backend.app.modules.scraping.config import ScrapingConfigService

    return ScrapingConfigService().get_raw_config()


def schedule_scan_after_strm(config: dict[str, Any]) -> None:
    if not str(config.get("scrape_root") or "").strip():
        return

    def _run() -> None:
        try:
            from shared.database.session import get_session_factory

            factory = get_session_factory()
            with factory() as session:
                scan_directory(session, config)
        except Exception:
            logger.warning("Background scraping scan failed", exc_info=True)

    threading.Thread(target=_run, daemon=True, name="scraping-scan").start()
