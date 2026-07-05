from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, false, func, not_, or_, select
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


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_datetime_date(value: str | None) -> date | None:
    return _parse_date(value)


def _case_insensitive_like(column, value: str):
    return func.lower(column).like(f"%{value.lower()}%")


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def requires_python_fallback(db: Session, filters: MovieListFilters) -> bool:
    if filters.storage_status:
        return True
    if db.bind.dialect.name == "sqlite":
        return bool(
            filters.source_task_id
            or filters.actors
            or filters.actors_not
            or filters.actors_count_min is not None
            or filters.actors_count_max is not None
            or filters.tags
            or filters.tags_not
        )
    return False


def build_movie_list_statement(
    filters: MovieListFilters,
    *,
    sort_by: str,
    sort_order: int | str,
    dialect_name: str | None = None,
) -> Select:
    stmt = select(Movie).options(selectinload(Movie.magnets))
    conditions = []

    if filters.search:
        conditions.append(or_(
            _case_insensitive_like(Movie.code, filters.search),
            _case_insensitive_like(Movie.source_name, filters.search),
            _case_insensitive_like(Movie.director, filters.search),
            _case_insensitive_like(Movie.maker, filters.search),
            _case_insensitive_like(Movie.series, filters.search),
        ))
    if filters.rating_min is not None:
        conditions.append(Movie.rating >= filters.rating_min)
    if filters.rating_max is not None:
        conditions.append(Movie.rating <= filters.rating_max)

    release_from = _parse_date(filters.release_date_from)
    release_to = _parse_date(filters.release_date_to)
    if release_from is not None:
        conditions.append(Movie.release_date >= release_from)
    if release_to is not None:
        conditions.append(Movie.release_date <= release_to)

    created_from = _parse_datetime_date(filters.created_at_from)
    created_to = _parse_datetime_date(filters.created_at_to)
    if created_from is not None:
        conditions.append(func.date(Movie.created_at) >= created_from.isoformat())
    if created_to is not None:
        conditions.append(func.date(Movie.created_at) <= created_to.isoformat())

    for value in split_csv(filters.director):
        conditions.append(Movie.director == value)
    for value in split_csv(filters.director_not):
        conditions.append(Movie.director != value)
    for value in split_csv(filters.maker):
        conditions.append(Movie.maker == value)
    for value in split_csv(filters.maker_not):
        conditions.append(Movie.maker != value)
    for value in split_csv(filters.series):
        conditions.append(Movie.series == value)
    for value in split_csv(filters.series_not):
        conditions.append(Movie.series != value)

    # PostgreSQL array conditions
    if dialect_name == "postgresql":
        if filters.source_task_id:
            source_task_id = _parse_uuid(filters.source_task_id)
            if source_task_id is not None:
                conditions.append(Movie.source_task_ids.contains([source_task_id]))
            else:
                conditions.append(false())
        for actor in split_csv(filters.actors):
            conditions.append(Movie.actors.contains([actor]))
        for actor in split_csv(filters.actors_not):
            conditions.append(not_(Movie.actors.contains([actor])))
        for tag in split_csv(filters.tags):
            conditions.append(Movie.tags.contains([tag]))
        for tag in split_csv(filters.tags_not):
            conditions.append(not_(Movie.tags.contains([tag])))
        if filters.actors_count_min is not None:
            conditions.append(func.array_length(Movie.actors, 1) >= filters.actors_count_min)
        if filters.actors_count_max is not None:
            conditions.append(func.array_length(Movie.actors, 1) <= filters.actors_count_max)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    normalized_sort_order = normalize_sort_order(sort_order)
    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Movie.created_at)
    order_expression = sort_column.asc() if normalized_sort_order == 1 else sort_column.desc()
    return stmt.order_by(order_expression)


def count_movies_for_statement(db: Session, statement: Select) -> int:
    count_stmt = select(func.count()).select_from(statement.order_by(None).subquery())
    return int(db.scalar(count_stmt) or 0)


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
    offset = skip if skip is not None else (page - 1) * limit
    statement = build_movie_list_statement(
        filters,
        sort_by=sort_by,
        sort_order=sort_order,
        dialect_name=db.bind.dialect.name,
    )

    # SQL-only path for scalar filters
    if not requires_python_fallback(db, filters):
        total = count_movies_for_statement(db, statement)
        rows = list(db.scalars(statement.offset(offset).limit(limit)).unique().all())
        return rows, total

    # Python fallback for storage status and SQLite array filters
    rows = list(db.scalars(statement).unique().all())
    filtered = [movie for movie in rows if movie_matches(movie, filters)]

    total = len(filtered)
    return filtered[offset:offset + limit], total
