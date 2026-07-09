from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie


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

    release_date = item.get("release_date") or None
    movie = Movie(
        code=item.get("code"),
        source_url=item.get("source_url"),
        source_name=item.get("source_name", ""),
        release_date=release_date,
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


def append_source_task_ids_for_codes(session: Session, codes: Iterable[str | None], task_id: UUID) -> set[str]:
    cleaned_codes: list[str] = []
    seen_codes: set[str] = set()
    for code in codes:
        normalized = str(code or "").strip()
        if normalized and normalized not in seen_codes:
            seen_codes.add(normalized)
            cleaned_codes.append(normalized)
    if not cleaned_codes:
        return set()

    movies = session.scalars(select(Movie).where(Movie.code.in_(cleaned_codes))).all()
    task_id_text = str(task_id)
    changed_codes: set[str] = set()

    for movie in movies:
        existing_ids = [str(value) for value in (movie.source_task_ids or [])]
        if task_id_text in existing_ids:
            continue
        movie.source_task_ids = list(movie.source_task_ids or []) + [task_id]
        if movie.code:
            changed_codes.add(movie.code)

    if changed_codes:
        session.flush()
    return changed_codes
