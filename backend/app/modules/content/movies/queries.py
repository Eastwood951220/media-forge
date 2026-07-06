from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.modules.content.movies.fallback import movie_matches
from backend.app.modules.content.movies.filter_options import list_filter_values
from backend.app.modules.content.movies.filters import (
    MovieListFilters,
    VALID_FILTER_TYPES,
    split_csv,
)
from backend.app.modules.content.movies.sql_builder import (
    ALLOWED_SORT_FIELDS,
    build_movie_list_statement,
    count_movies_for_statement,
    normalize_sort_order,
    requires_python_fallback,
)
from shared.database.models.content import Movie


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

    if not requires_python_fallback(db, filters):
        total = count_movies_for_statement(db, statement)
        rows = list(db.scalars(statement.offset(offset).limit(limit)).unique().all())
        return rows, total

    rows = list(db.scalars(statement).unique().all())
    filtered = [movie for movie in rows if movie_matches(movie, filters)]
    total = len(filtered)
    return filtered[offset:offset + limit], total


__all__ = [
    "ALLOWED_SORT_FIELDS",
    "MovieListFilters",
    "VALID_FILTER_TYPES",
    "build_movie_list_statement",
    "count_movies_for_statement",
    "list_filter_values",
    "list_movies_page",
    "movie_matches",
    "normalize_sort_order",
    "requires_python_fallback",
    "split_csv",
]
