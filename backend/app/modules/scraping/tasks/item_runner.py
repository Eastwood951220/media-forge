from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.models.scraping_task import ScrapingTaskItem
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from backend.app.modules.scraping.images import write_artwork
from backend.app.modules.scraping.nfo import write_movie_nfo
from backend.app.modules.scraping.paths import cloud_to_local
from backend.app.modules.scraping.scan import movie_target_folders, refresh_movie_status
from backend.app.modules.scraping.sources import fetch_by_priority
from shared.database.models.content import Movie


def _resolve_folder(movie: Movie, config: dict) -> tuple[Path | None, str]:
    scrape_root = str(config.get("scrape_root") or "")
    media_root = str(config.get("media_root") or "/media")
    for target in movie_target_folders(movie):
        local = cloud_to_local(scrape_root, media_root, target)
        if local is not None and local.is_dir():
            return local, target
    return None, ""


def run_item(
    db: Session,
    item: ScrapingTaskItem,
    *,
    config: dict,
    transport=None,
) -> None:
    started = time.monotonic()
    movie = db.get(Movie, item.movie_id)
    if movie is None:
        item.status = "failed"
        item.error_message = "电影不存在"
        return
    if normalized_movie_storage_status(movie) != "stored":
        item.status = "skipped"
        item.error_message = "未存储"
        return

    folder, cloud_folder = _resolve_folder(movie, config)
    if folder is None:
        item.status = "skipped"
        item.error_message = "目标文件夹不存在"
        return

    metadata = None
    missing = not (movie.cover and movie.actors and movie.release_date and movie.maker and movie.series)
    if missing:
        metadata = fetch_by_priority(movie.code or "", list(config.get("metadata_sources") or []))
        if metadata is not None:
            item.source = metadata.site_key.lower()
            if not movie.cover and metadata.cover_url:
                movie.cover = metadata.cover_url

    if not movie.cover:
        item.status = "failed"
        item.error_message = "缺少封面，无法生成图片"
        return

    write_movie_nfo(
        folder,
        movie,
        cloud_folder=cloud_folder,
        source_site=metadata.site_key if metadata is not None else None,
    )
    written = write_artwork(
        folder,
        cover_url=movie.cover,
        backdrop_url=metadata.backdrop_url if metadata is not None else None,
        landscape_url=metadata.landscape_url if metadata is not None else None,
        transport=transport,
    )
    if written == 0:
        item.status = "failed"
        item.error_message = "图片下载失败"
        return

    refresh_movie_status(db, movie, local_folder=folder, cloud_folder=cloud_folder)
    item.status = "success"
    item.folder = cloud_folder
    item.duration_ms = int((time.monotonic() - started) * 1000)
