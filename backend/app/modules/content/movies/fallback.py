from __future__ import annotations

from backend.app.modules.content.movies.filters import MovieListFilters, split_csv
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from shared.database.models.content import Movie


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
