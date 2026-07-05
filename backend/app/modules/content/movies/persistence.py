from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie, MovieFilter, MovieMagnet


def extract_info_hash(magnet_url: str | None) -> str:
    if not magnet_url:
        return ""
    query = parse_qs(urlparse(magnet_url).query)
    for xt in query.get("xt", []):
        prefix = "urn:btih:"
        if xt.lower().startswith(prefix):
            return xt[len(prefix):].lower()
    return ""


def build_magnet_dedupe_key(movie_id: str, magnet: dict[str, Any]) -> str:
    info_hash = str(magnet.get("info_hash") or "").strip().lower()
    if not info_hash:
        info_hash = extract_info_hash(magnet.get("magnet") or magnet.get("magnet_url"))
    if info_hash:
        return info_hash

    parts = [
        str(movie_id),
        str(magnet.get("name") or ""),
        str(magnet.get("size_text") or ""),
        str(magnet.get("file_count") or ""),
        str(magnet.get("file_text") or ""),
        str(magnet.get("date") or ""),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _parse_size_mb(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    size_text = str(value).strip().upper()
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|TB)?", size_text)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = match.group(2) or "MB"
    multipliers = {"KB": 1 / 1024, "MB": 1, "GB": 1024, "TB": 1024 * 1024}
    return number * multipliers.get(unit, 1)


def _has_chinese_sub(magnet: dict[str, Any]) -> bool:
    if magnet.get("has_chinese_sub"):
        return True
    tags = magnet.get("tags") or []
    if any("字幕" in str(tag) or "中字" in str(tag) for tag in tags):
        return True
    title = (magnet.get("title") or magnet.get("name") or "").lower()
    return any(keyword in title for keyword in ["chs", "cht", "chinese", "中字", "中文", "字幕"])


def compute_magnet_weight(magnet: dict[str, Any]) -> int:
    has_sub = _has_chinese_sub(magnet)
    size_mb = _parse_size_mb(magnet.get("size") or magnet.get("size_text"))
    is_large_sub = has_sub and size_mb > 2048

    file_count = magnet.get("file_count")
    if isinstance(file_count, (int, float)) and file_count > 0:
        file_penalty = max(0, 10000 - int(file_count) * 100)
    else:
        file_penalty = 5000

    return int(is_large_sub * 100000 + has_sub * 10000 + min(size_mb, 50000) + file_penalty)


def _movie_unique_value(item: dict[str, Any]) -> tuple[str, str]:
    code = str(item.get("code") or "").strip()
    if code:
        return "code", code
    return "source_url", str(item.get("source_url") or "").strip()


def upsert_movie(session: Session, item: dict[str, Any]) -> UUID:
    unique_field, unique_value = _movie_unique_value(item)
    if not unique_value:
        raise ValueError("movie item must include code or source_url")

    if unique_field == "code":
        existing = session.scalar(select(Movie).where(Movie.code == unique_value))
    else:
        existing = session.scalar(select(Movie).where(Movie.source_url == unique_value))
    if existing is not None:
        return existing.id

    movie = Movie(
        code=item.get("code"),
        source_url=item.get("source_url"),
        source_name=item.get("source_name", ""),
        release_date=item.get("release_date"),
        duration=item.get("duration", 0),
        director=item.get("director", ""),
        maker=item.get("maker", ""),
        series=item.get("series", ""),
        rating=item.get("rating"),
        actors=item.get("actors", []),
        tags=item.get("tags", []),
        source_task_ids=item.get("source_task_ids", []),
        cover=item.get("cover", ""),
        marked=item.get("marked", False),
        storage_summary=item.get("storage_summary", {}),
        raw_detail=item.get("raw_detail", {}),
    )
    session.add(movie)
    session.flush()
    return movie.id


def append_source_task_id(session: Session, code: str | None, task_id: UUID) -> bool:
    if not code:
        return False
    movie = session.scalar(select(Movie).where(Movie.code == code))
    if movie is None:
        return False

    existing_ids = [str(value) for value in (movie.source_task_ids or [])]
    task_id_text = str(task_id)
    if task_id_text in existing_ids:
        return False
    movie.source_task_ids = list(movie.source_task_ids or []) + [task_id]
    session.flush()
    return True


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_magnet(movie_id: UUID, magnet: dict[str, Any]) -> dict[str, Any] | None:
    magnet_url = str(magnet.get("magnet") or magnet.get("magnet_url") or "").strip()
    name = str(magnet.get("name") or "").strip()
    size_text = str(magnet.get("size_text") or "").strip()
    file_text = str(magnet.get("file_text") or "").strip()
    if not (magnet_url or name or size_text or file_text):
        return None

    info_hash = str(magnet.get("info_hash") or "").strip().lower()
    if not info_hash:
        info_hash = extract_info_hash(magnet_url)

    tags = magnet.get("tags")
    if not isinstance(tags, list):
        tags = []

    size_mb = _to_float(magnet.get("size"))
    if size_mb is None:
        size_mb = _parse_size_mb(size_text)

    return {
        "magnet_url": magnet_url,
        "info_hash": info_hash if info_hash else None,
        "dedupe_key": build_magnet_dedupe_key(str(movie_id), {**magnet, "magnet": magnet_url, "info_hash": info_hash, "name": name, "size_text": size_text, "file_text": file_text}),
        "name": name,
        "size_mb": size_mb,
        "size_text": size_text,
        "file_count": magnet.get("file_count"),
        "file_text": file_text,
        "tags": tags,
        "has_chinese_sub": bool(magnet.get("has_chinese_sub")),
        "weight": compute_magnet_weight(magnet),
        "date": magnet.get("date") or "",
        "selected": False,
        "raw_data": {},
    }


def upsert_magnets(session: Session, movie_id: UUID, movie: dict[str, Any], magnets: list[dict[str, Any]]) -> int:
    saved_count = 0
    for magnet in magnets:
        document = _normalize_magnet(movie_id, magnet)
        if document is None:
            continue
        existing = session.scalar(
            select(MovieMagnet).where(
                MovieMagnet.movie_id == movie_id,
                MovieMagnet.dedupe_key == document["dedupe_key"],
            )
        )
        if existing is None:
            session.add(MovieMagnet(movie_id=movie_id, **document))
        else:
            for key, value in document.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        saved_count += 1
    session.flush()
    if saved_count:
        auto_select_best_magnet(session, movie_id)
    return saved_count


def auto_select_best_magnet(session: Session, movie_id: UUID) -> None:
    magnets = session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie_id)).all()
    if not magnets:
        return
    best = max(magnets, key=lambda magnet: magnet.weight or 0)
    for magnet in magnets:
        magnet.selected = magnet.id == best.id
    session.flush()


def upsert_movie_with_magnets(session: Session, item_data: dict[str, Any]) -> UUID:
    movie_doc = dict(item_data)
    magnets = movie_doc.pop("magnets", []) or []
    movie_id = upsert_movie(session, movie_doc)
    if magnets:
        upsert_magnets(session, movie_id, movie_doc, magnets)
    return movie_id


def sync_movie_filters(session: Session) -> dict[str, int]:
    actors: set[str] = set()
    tags: set[str] = set()
    directors: set[str] = set()
    makers: set[str] = set()
    series: set[str] = set()

    for movie in session.scalars(select(Movie)).all():
        for value in movie.actors or []:
            if isinstance(value, str) and value.strip():
                actors.add(value.strip())
        for value in movie.tags or []:
            if isinstance(value, str) and value.strip():
                tags.add(value.strip())
        if movie.director and movie.director.strip():
            directors.add(movie.director.strip())
        if movie.maker and movie.maker.strip():
            makers.add(movie.maker.strip())
        if movie.series and movie.series.strip():
            series.add(movie.series.strip())

    session.execute(delete(MovieFilter))
    for name in sorted(actors):
        session.add(MovieFilter(type="actor", name=name, count=0))
    for name in sorted(tags):
        session.add(MovieFilter(type="tag", name=name, count=0))
    for name in sorted(directors):
        session.add(MovieFilter(type="director", name=name, count=0))
    for name in sorted(makers):
        session.add(MovieFilter(type="maker", name=name, count=0))
    for name in sorted(series):
        session.add(MovieFilter(type="series", name=name, count=0))
    session.flush()

    return {
        "actors": len(actors),
        "tags": len(tags),
        "directors": len(directors),
        "makers": len(makers),
        "series": len(series),
    }
