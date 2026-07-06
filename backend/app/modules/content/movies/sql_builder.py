from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, false, func, not_, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.filters import MovieListFilters, split_csv
from shared.database.models.content import Movie

ALLOWED_SORT_FIELDS = {
    "created_at": Movie.created_at,
    "updated_at": Movie.updated_at,
    "code": Movie.code,
    "source_name": Movie.source_name,
    "release_date": Movie.release_date,
    "rating": Movie.rating,
}


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


def _postgres_array_contains(column: Any, value: Any, item_type: Any):
    return column.op("@>")(postgresql.array([value], type_=item_type))


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
                conditions.append(_postgres_array_contains(Movie.source_task_ids, source_task_id, postgresql.UUID(as_uuid=True)))
            else:
                conditions.append(false())
        for actor in split_csv(filters.actors):
            conditions.append(_postgres_array_contains(Movie.actors, actor, postgresql.TEXT()))
        for actor in split_csv(filters.actors_not):
            conditions.append(not_(_postgres_array_contains(Movie.actors, actor, postgresql.TEXT())))
        for tag in split_csv(filters.tags):
            conditions.append(_postgres_array_contains(Movie.tags, tag, postgresql.TEXT()))
        for tag in split_csv(filters.tags_not):
            conditions.append(not_(_postgres_array_contains(Movie.tags, tag, postgresql.TEXT())))
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
