from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.queries import MovieListFilters, list_movies_page
from backend.app.modules.content.movies.storage_status import STORAGE_STATUS_STORED, sync_movie_storage_status
from backend.app.modules.storage.config.service import StorageConfigService
from shared.database.models.content import Movie


@dataclass(frozen=True)
class MovieStorageSyncResultPayload:
    total: int
    stored_count: int
    not_stored_count: int
    results: list[dict]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "stored_count": self.stored_count,
            "not_stored_count": self.not_stored_count,
            "results": self.results,
        }


def select_movies_for_storage_sync(
    db: Session,
    *,
    movie_ids: list[uuid.UUID] | None,
    filters: dict,
) -> list[Movie]:
    query = db.query(Movie).options(selectinload(Movie.magnets))
    if movie_ids:
        return query.filter(Movie.id.in_(movie_ids)).all()

    rows, _total = list_movies_page(
        db,
        MovieListFilters(
            search=filters.get("search"),
            source_task_id=filters.get("source_task_id"),
            rating_min=filters.get("rating_min"),
            rating_max=filters.get("rating_max"),
            actors=filters.get("actors"),
            actors_not=filters.get("actors_not"),
            actors_count_min=filters.get("actors_count_min"),
            actors_count_max=filters.get("actors_count_max"),
            tags=filters.get("tags"),
            tags_not=filters.get("tags_not"),
            director=filters.get("director"),
            director_not=filters.get("director_not"),
            maker=filters.get("maker"),
            maker_not=filters.get("maker_not"),
            series=filters.get("series"),
            series_not=filters.get("series_not"),
            release_date_from=filters.get("release_date_from"),
            release_date_to=filters.get("release_date_to"),
            created_at_from=filters.get("created_at_from"),
            created_at_to=filters.get("created_at_to"),
            storage_status=filters.get("storage_status"),
        ),
        sort_by="created_at",
        sort_order=-1,
        page=1,
        limit=100000,
        skip=0,
    )
    return rows


def sync_movies_storage_statuses(
    db: Session,
    *,
    user_id: str,
    movies: list[Movie],
    config_service: StorageConfigService | None = None,
) -> MovieStorageSyncResultPayload:
    from backend.app.modules.storage.tasks.events import publish_movie_storage_updated

    service = config_service or StorageConfigService()
    with service.open_provider() as (config, provider):
        results = []
        for movie in movies:
            results.append(
                sync_movie_storage_status(
                    db=db,
                    movie=movie,
                    provider=provider,
                    config=config,
                    source="manual_sync",
                )
            )

    db.commit()

    for movie in movies:
        publish_movie_storage_updated(db, user_id, movie.id)

    stored_count = sum(1 for result in results if result.status == STORAGE_STATUS_STORED)
    return MovieStorageSyncResultPayload(
        total=len(results),
        stored_count=stored_count,
        not_stored_count=len(results) - stored_count,
        results=[
            {
                "movie_id": result.movie_id,
                "status": result.status,
                "found_count": result.found_count,
                "checked_targets": result.checked_targets,
                "locations": result.locations,
            }
            for result in results
        ],
    )
