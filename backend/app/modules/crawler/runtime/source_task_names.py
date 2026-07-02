"""Helpers for managing source task IDs on movies."""

from __future__ import annotations

import uuid
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
    """Find which movie codes already exist in the database."""
    cleaned = _clean_codes(codes)
    if not cleaned:
        return set()
    rows = db.scalars(select(Movie.code).where(Movie.code.in_(cleaned))).all()
    return {code for code in rows if code}


def movie_code_exists(db: Session, code: str | None) -> bool:
    """Check if a movie with the given code exists."""
    normalized = str(code or "").strip()
    if not normalized:
        return False
    return db.scalar(select(Movie.id).where(Movie.code == normalized)) is not None


def add_source_task_id_for_code(db: Session, code: str | None, task_id: uuid.UUID) -> bool:
    """Add a task ID to an existing movie's source_task_ids list.

    Returns True if the task ID was added, False if movie not found or task ID already exists.
    """
    normalized = str(code or "").strip()
    if not normalized or not task_id:
        return False

    movie = db.scalar(select(Movie).where(Movie.code == normalized))
    if movie is None:
        return False

    current_ids = list(movie.source_task_ids or [])
    if task_id in current_ids:
        return False

    movie.source_task_ids = current_ids + [task_id]
    db.flush()
    return True
