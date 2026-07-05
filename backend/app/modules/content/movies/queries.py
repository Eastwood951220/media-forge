from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from shared.database.models.content import Movie, MovieFilter


ALLOWED_SORT_FIELDS = {
    "created_at": Movie.created_at,
    "updated_at": Movie.updated_at,
    "code": Movie.code,
    "source_name": Movie.source_name,
    "release_date": Movie.release_date,
    "rating": Movie.rating,
}

VALID_FILTER_TYPES = {"actor", "tag", "director", "maker", "series"}


@dataclass(frozen=True)
class MovieListFilters:
    search: str | None = None
    source_task_id: str | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    actors: str | None = None
    actors_not: str | None = None
    actors_count_min: int | None = None
    actors_count_max: int | None = None
    tags: str | None = None
    tags_not: str | None = None
    director: str | None = None
    director_not: str | None = None
    maker: str | None = None
    maker_not: str | None = None
    series: str | None = None
    series_not: str | None = None
    release_date_from: str | None = None
    release_date_to: str | None = None
    created_at_from: str | None = None
    created_at_to: str | None = None
    storage_status: str | None = None


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


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


def movie_matches(movie: Movie, filters: MovieListFilters) -> bool:
    if filters.search:
        needle = filters.search.lower()
        haystack = " ".join([movie.code or "", movie.source_name or "", movie.director or "", movie.maker or "", movie.series or ""]).lower()
        if needle not in haystack:
            return False
    if filters.source_task_id:
        task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
        if filters.source_task_id not in task_ids:
            return False
    if filters.rating_min is not None and (movie.rating is None or float(movie.rating) < filters.rating_min):
        return False
    if filters.rating_max is not None and (movie.rating is None or float(movie.rating) > filters.rating_max):
        return False
    movie_actors = set(movie.actors or [])
    movie_tags = set(movie.tags or [])
    if split_csv(filters.actors) and not set(split_csv(filters.actors)).issubset(movie_actors):
        return False
    if split_csv(filters.actors_not) and set(split_csv(filters.actors_not)).intersection(movie_actors):
        return False
    if split_csv(filters.tags) and not set(split_csv(filters.tags)).issubset(movie_tags):
        return False
    if split_csv(filters.tags_not) and set(split_csv(filters.tags_not)).intersection(movie_tags):
        return False
    if split_csv(filters.director) and movie.director not in split_csv(filters.director):
        return False
    if split_csv(filters.director_not) and movie.director in split_csv(filters.director_not):
        return False
    if split_csv(filters.maker) and movie.maker not in split_csv(filters.maker):
        return False
    if split_csv(filters.maker_not) and movie.maker in split_csv(filters.maker_not):
        return False
    if split_csv(filters.series) and movie.series not in split_csv(filters.series):
        return False
    if split_csv(filters.series_not) and movie.series in split_csv(filters.series_not):
        return False
    if filters.actors_count_min is not None and len(movie.actors or []) < filters.actors_count_min:
        return False
    if filters.actors_count_max is not None and len(movie.actors or []) > filters.actors_count_max:
        return False
    if filters.release_date_from and (movie.release_date is None or movie.release_date.isoformat() < filters.release_date_from):
        return False
    if filters.release_date_to and (movie.release_date is None or movie.release_date.isoformat() > filters.release_date_to):
        return False
    if filters.created_at_from and (movie.created_at is None or movie.created_at.date().isoformat() < filters.created_at_from):
        return False
    if filters.created_at_to and (movie.created_at is None or movie.created_at.date().isoformat() > filters.created_at_to):
        return False
    if filters.storage_status and normalized_movie_storage_status(movie) != filters.storage_status:
        return False
    return True


def normalize_sort_order(sort_order: int | str) -> int:
    try:
        normalized = int(sort_order)
    except (TypeError, ValueError):
        normalized = 1 if sort_order == "asc" else -1
    return normalized if normalized in (-1, 1) else -1


def list_movies_page(
    db: Session,
    filters: MovieListFilters,
    *,
    sort_by: str,
    sort_order: int | str,
    page: int,
    limit: int,
    skip: int | None,
) -> tuple[list[Movie], int]:
    rows = db.query(Movie).options(selectinload(Movie.magnets)).all()
    filtered = [movie for movie in rows if movie_matches(movie, filters)]

    normalized_sort_order = normalize_sort_order(sort_order)
    sort_column = sort_by if sort_by in ALLOWED_SORT_FIELDS else "created_at"
    filtered.sort(key=lambda movie: getattr(movie, sort_column) is None)
    filtered.sort(key=lambda movie: getattr(movie, sort_column) or "", reverse=normalized_sort_order == -1)

    total = len(filtered)
    offset = skip if skip is not None else (page - 1) * limit
    return filtered[offset:offset + limit], total
