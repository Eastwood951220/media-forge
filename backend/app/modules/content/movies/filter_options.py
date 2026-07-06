from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie, MovieFilter


def unique_sorted(values: list[str | None]) -> list[str]:
    return sorted({value for value in values if value})


def sqlite_filter_values(db: Session, filter_type: str) -> list[str]:
    movies = db.query(Movie).all()
    if filter_type == "actor":
        return unique_sorted([actor for movie in movies for actor in (movie.actors or [])])
    if filter_type == "tag":
        return unique_sorted([tag for movie in movies for tag in (movie.tags or [])])
    return unique_sorted([getattr(movie, filter_type) for movie in movies])


def cached_filter_values(db: Session, filter_type: str) -> list[str]:
    return list(db.scalars(
        select(MovieFilter.name)
        .where(MovieFilter.type == filter_type, MovieFilter.name != "")
        .distinct()
        .order_by(MovieFilter.name.asc())
    ).all())


def list_filter_values(db: Session, filter_type: str) -> list[str]:
    cached_names = cached_filter_values(db, filter_type)
    if cached_names:
        return cached_names

    if db.bind.dialect.name == "sqlite":
        return sqlite_filter_values(db, filter_type)
    if filter_type == "actor":
        names = db.scalars(select(func.unnest(Movie.actors).label("name")).distinct().order_by("name")).all()
    elif filter_type == "tag":
        names = db.scalars(select(func.unnest(Movie.tags).label("name")).distinct().order_by("name")).all()
    else:
        column = getattr(Movie, filter_type)
        names = db.scalars(select(column).where(column != "", column.is_not(None)).distinct().order_by(column.asc())).all()
    return [name for name in names if name]
