from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie


def _clean_codes(codes: Iterable[str | None]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for code in codes:
        normalized = str(code or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return cleaned


def find_existing_movie_codes(db: Session, codes: Iterable[str | None]) -> set[str]:
    cleaned = _clean_codes(codes)
    if not cleaned:
        return set()
    rows = db.scalars(select(Movie.code).where(Movie.code.in_(cleaned))).all()
    return {code for code in rows if code}


def movie_code_exists(db: Session, code: str | None) -> bool:
    normalized = str(code or "").strip()
    if not normalized:
        return False
    return db.scalar(select(Movie.id).where(Movie.code == normalized)) is not None


def add_source_task_name_for_code(db: Session, code: str | None, task_name: str) -> bool:
    normalized = str(code or "").strip()
    if not normalized or not task_name:
        return False

    movie = db.scalar(select(Movie).where(Movie.code == normalized))
    if movie is None:
        return False

    current_names = list(movie.source_task_names or [])
    if task_name in current_names:
        return False

    movie.source_task_names = current_names + [task_name]
    db.flush()
    return True
