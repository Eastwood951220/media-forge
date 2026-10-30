from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.models.scraping_task import ScrapingTaskItem
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from backend.app.modules.scraping.images import write_artwork
from backend.app.modules.scraping.metatube import is_metatube_source, write_metatube_artwork
from backend.app.modules.scraping.nfo import write_movie_nfo
from backend.app.modules.scraping.paths import (
    cloud_to_local,
    code_from_folder_name,
    local_to_cloud,
    normalize_code,
)
from backend.app.modules.scraping.tasks.progress import start_item_step
from backend.app.modules.scraping.scan import (
    iter_movie_folders,
    movie_target_folders,
    refresh_movie_status,
)
from backend.app.modules.scraping.sources import (
    SourceMetadata,
    fetch_by_priority,
    referer_for_url,
    source_referer,
)
from shared.database.models.content import Movie


def _scan_index_folder(movie: Movie, scrape_root: str, media_root: str) -> tuple[Path | None, str]:
    """Fall back to the scan index (walk the scrape root) when locations do not map."""
    if not scrape_root or not Path(scrape_root).is_dir():
        return None, ""
    wanted = normalize_code(movie.code or "")
    if not wanted:
        return None, ""
    candidates: list[Path] = []
    for folder, *_rest in iter_movie_folders(Path(scrape_root)):
        code = code_from_folder_name(folder.name)
        if code and normalize_code(code) == wanted:
            candidates.append(folder)
    if not candidates:
        return None, ""
    chosen = sorted(candidates, key=str)[0]
    cloud = local_to_cloud(scrape_root, media_root, chosen)
    if cloud is None:
        return None, ""
    return chosen, cloud


def _resolve_folder(movie: Movie, config: dict) -> tuple[Path | None, str]:
    scrape_root = str(config.get("scrape_root") or "")
    media_root = str(config.get("media_root") or "/media")
    for target in movie_target_folders(movie):
        local = cloud_to_local(scrape_root, media_root, target)
        if local is not None and local.is_dir():
            return local, target
    return _scan_index_folder(movie, scrape_root, media_root)


def _parse_premiered(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _apply_metadata(movie: Movie, metadata: SourceMetadata) -> None:
    """Fill only fields the DB row is missing; the status refresh commit persists them."""
    if not movie.cover and metadata.cover_url:
        movie.cover = metadata.cover_url
    if movie.release_date is None and metadata.premiered:
        parsed = _parse_premiered(metadata.premiered)
        if parsed is not None:
            movie.release_date = parsed
    if not str(movie.maker or "").strip() and metadata.studio:
        movie.maker = metadata.studio
    if not str(movie.series or "").strip() and metadata.series:
        movie.series = metadata.series
    if not list(movie.actors or []) and metadata.actors:
        movie.actors = list(metadata.actors)
    # The Movie model exposes the genre/tag list as the single ``tags`` column.
    if not list(movie.tags or []) and metadata.tags:
        movie.tags = list(metadata.tags)


def run_item(
    db: Session,
    item: ScrapingTaskItem,
    *,
    config: dict,
    transport=None,
    owner_id: str | None = None,
) -> None:
    started = time.monotonic()
    owner_id = owner_id or str(item.task.created_by)
    movie = db.get(Movie, item.movie_id)
    if movie is None:
        item.status = "failed"
        item.error_message = "电影不存在"
        return
    if normalized_movie_storage_status(movie) != "stored":
        item.status = "skipped"
        item.error_message = "未存储"
        return

    start_item_step(db, item, owner_id, "locate_folder", "定位影片文件夹")
    folder, cloud_folder = _resolve_folder(movie, config)
    if folder is None:
        item.status = "skipped"
        item.error_message = "目标文件夹不存在"
        return

    start_item_step(db, item, owner_id, "fetch_metadata", "获取元数据")
    sources = list(config.get("metadata_sources") or [])
    if any(is_metatube_source(source) for source in sources):
        metadata = fetch_by_priority(
            movie.code or "", sources,
            metatube_url=str(config.get("metatube_url") or ""),
            metatube_token=str(config.get("metatube_token") or ""),
        )
    else:
        metadata = fetch_by_priority(movie.code or "", sources)
    missing = not (
        movie.cover
        and list(movie.actors or [])
        and movie.release_date
        and str(movie.maker or "").strip()
        and str(movie.series or "").strip()
        and list(movie.tags or [])
    )
    if metadata is not None:
        item.source = metadata.site_key.lower()
        if missing:
            _apply_metadata(movie, metadata)

    if not movie.cover:
        item.status = "failed"
        item.error_message = "缺少封面，无法生成图片"
        return

    start_item_step(db, item, owner_id, "write_artwork", "下载并筛选图片")
    site_key = metadata.site_key if metadata is not None else None
    if metadata is not None:
        referer = source_referer(metadata.site_key)
    else:
        referer = referer_for_url(movie.source_url) or referer_for_url(movie.cover)

    previews = list(metadata.preview_urls) if metadata is not None else []
    if not previews and metadata is not None:
        previews = [url for url in (metadata.backdrop_url, metadata.landscape_url) if url]
    artwork = write_metatube_artwork(folder, metadata, transport=transport) if metadata and metadata.primary_image_url else write_artwork(
        folder,
        cover_url=movie.cover,
        source_cover_url=metadata.cover_url if metadata is not None else None,
        backdrop_urls=previews,
        landscape_urls=previews,
        referer=referer,
        cover_referer=referer_for_url(movie.source_url) or referer_for_url(movie.cover) or referer,
        transport=transport,
    )
    if "folder.jpg" not in artwork.available:
        item.status = "failed"
        item.error_message = "图片下载失败"
        return

    start_item_step(db, item, owner_id, "write_nfo", "写入影片 NFO")
    write_movie_nfo(
        folder,
        movie,
        cloud_folder=cloud_folder,
        source_site=site_key,
        artwork=artwork.available,
    )

    start_item_step(db, item, owner_id, "refresh_status", "更新影片刮削状态")
    refresh_movie_status(db, movie, local_folder=folder, cloud_folder=cloud_folder)
    item.status = "success"
    item.folder = cloud_folder
    item.duration_ms = int((time.monotonic() - started) * 1000)
