from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from shared.database.models.content import Movie


def build_movie_storage_location_map(db: Session, movies: list[Movie]) -> dict[str, list[str]]:
    from backend.app.models.crawl_task import CrawlTask

    task_ids: set[uuid.UUID] = set()
    movie_task_ids: dict[str, list[str]] = {}
    for movie in movies:
        ids = [str(tid) for tid in (movie.source_task_ids or [])]
        movie_task_ids[str(movie.id)] = ids
        for task_id_text in ids:
            try:
                task_ids.add(uuid.UUID(task_id_text))
            except (TypeError, ValueError):
                continue

    if not task_ids:
        return {movie_id: [] for movie_id in movie_task_ids}

    task_rows = (
        db.query(CrawlTask.id, CrawlTask.storage_location)
        .filter(CrawlTask.id.in_(task_ids))
        .all()
    )
    location_by_task = {str(task_id): location for task_id, location in task_rows if location}
    result: dict[str, list[str]] = {}
    for movie_id, ids in movie_task_ids.items():
        locations: list[str] = []
        for task_id_text in ids:
            location = location_by_task.get(task_id_text)
            if location and location not in locations:
                locations.append(location)
        result[movie_id] = locations
    return result


def movie_storage_locations(
    movie: Movie,
    db: Session | None,
    storage_location_map: dict[str, list[str]] | None = None,
) -> list[str]:
    if storage_location_map is not None:
        return list(storage_location_map.get(str(movie.id), []))
    source_task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
    if db is None or not source_task_ids:
        return []

    from backend.app.models.crawl_task import CrawlTask

    locations: list[str] = []
    for task_id_text in source_task_ids:
        try:
            task_id = uuid.UUID(task_id_text)
        except (TypeError, ValueError):
            continue
        crawl_task = db.get(CrawlTask, task_id)
        if crawl_task and crawl_task.storage_location and crawl_task.storage_location not in locations:
            locations.append(crawl_task.storage_location)
    return locations


def serialize_movie(
    movie: Movie,
    *,
    include_magnets: bool = False,
    db: Session | None = None,
    storage_location_map: dict[str, list[str]] | None = None,
) -> dict:
    source_task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
    payload = {
        "_id": str(movie.id),
        "id": str(movie.id),
        "code": movie.code or "",
        "source_url": movie.source_url or "",
        "source_name": movie.source_name or "",
        "cover": movie.cover or "",
        "release_date": movie.release_date.isoformat() if movie.release_date else None,
        "duration": movie.duration or 0,
        "director": movie.director or "",
        "maker": movie.maker or "",
        "series": movie.series or "",
        "rating": float(movie.rating) if movie.rating is not None else None,
        "actors": list(movie.actors or []),
        "tags": list(movie.tags or []),
        "source_task_ids": source_task_ids,
        "storage_locations": movie_storage_locations(movie, db, storage_location_map),
        "marked": bool(movie.marked),
        "storage_status": normalized_movie_storage_status(movie),
        "storage_summary": movie.storage_summary or {},
        "raw_detail": movie.raw_detail or {},
        "created_at": movie.created_at.isoformat() if movie.created_at else None,
        "updated_at": movie.updated_at.isoformat() if movie.updated_at else None,
    }
    if include_magnets:
        magnets = list(movie.magnets or [])
        payload["magnets"] = [
            {
                "_id": str(magnet.id),
                "id": str(magnet.id),
                "movie_id": str(magnet.movie_id),
                "magnet": magnet.magnet_url,
                "magnet_url": magnet.magnet_url,
                "name": magnet.name or "",
                "title": magnet.name or "",
                "size": magnet.size_text or "",
                "size_mb": float(magnet.size_mb or 0),
                "size_text": magnet.size_text or "",
                "file_count": magnet.file_count,
                "file_text": magnet.file_text or "",
                "tags": magnet.tags or [],
                "has_chinese_sub": bool(magnet.has_chinese_sub),
                "date": magnet.date or "",
                "dedupe_key": magnet.dedupe_key or "",
                "weight": magnet.weight or 0,
                "selected": bool(magnet.selected),
            }
            for magnet in magnets
        ]
        selected = next((magnet for magnet in magnets if magnet.selected), None)
        payload["selected_magnet_dedupe_key"] = selected.dedupe_key if selected else None
    return payload
