import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.content.movies.delete_api import delete_movies_from_request
from backend.app.modules.content.movies.magnet_refresh import create_magnet_refresh_run
from backend.app.modules.crawler.runs.schemas import CrawlRunRead
from backend.app.modules.content.movies.queries import (
    VALID_FILTER_TYPES,
    MovieListFilters,
    list_filter_values,
    list_movies_page,
    movie_matches,
)
from backend.app.modules.content.movies.schemas import MovieDeleteRequest, MovieMagnetRefreshRequest, MovieStorageSyncRequest
from backend.app.modules.content.movies.serializers import build_movie_storage_location_map, serialize_movie
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from backend.app.modules.content.movies.storage_sync_api import (
    sync_movies_from_request,
    sync_single_movie_from_cd2,
)
from backend.app.modules.storage.index.store import StorageIndexMissingError
from shared.database.models.content import Movie, MovieFilter
from backend.app.modules.content.movies.filter_config import (
    MovieFilterConfigPayload,
    read_movie_filter_config,
    write_movie_filter_config,
)
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/content/movies", tags=["content-movies"])


@router.get("/filters")
def list_filters(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    type: str = Query(..., description="actor, tag, director, maker, series"),
) -> dict:
    if type not in VALID_FILTER_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid filter type: {type}")

    return success(data=list_filter_values(db, type))


@router.get("")
def list_movies(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
    search: str | None = Query(default=None, max_length=200),
    source_task_id: str | None = Query(default=None, max_length=36),
    sort_by: str = Query(default="created_at"),
    sort_order: int | str = Query(default=-1),
    rating_min: float | None = Query(default=None, ge=0, le=5),
    rating_max: float | None = Query(default=None, ge=0, le=5),
    actors: str | None = Query(default=None),
    actors_not: str | None = Query(default=None),
    actors_count_min: int | None = Query(default=None, ge=0),
    actors_count_max: int | None = Query(default=None, ge=0),
    tags: str | None = Query(default=None),
    tags_not: str | None = Query(default=None),
    director: str | None = Query(default=None),
    director_not: str | None = Query(default=None),
    maker: str | None = Query(default=None),
    maker_not: str | None = Query(default=None),
    series: str | None = Query(default=None),
    series_not: str | None = Query(default=None),
    release_date_from: str | None = Query(default=None),
    release_date_to: str | None = Query(default=None),
    created_at_from: str | None = Query(default=None),
    created_at_to: str | None = Query(default=None),
    storage_status: str | None = Query(default=None),
) -> dict:
    search_text = search or keyword
    rows, total = list_movies_page(
        db,
        MovieListFilters(
            search=search_text,
            source_task_id=source_task_id,
            rating_min=rating_min,
            rating_max=rating_max,
            actors=actors,
            actors_not=actors_not,
            actors_count_min=actors_count_min,
            actors_count_max=actors_count_max,
            tags=tags,
            tags_not=tags_not,
            director=director,
            director_not=director_not,
            maker=maker,
            maker_not=maker_not,
            series=series,
            series_not=series_not,
            release_date_from=release_date_from,
            release_date_to=release_date_to,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            storage_status=storage_status,
        ),
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        limit=limit,
        skip=skip,
    )
    storage_location_map = build_movie_storage_location_map(db, rows)
    return paginated(
        rows=[
            serialize_movie(movie, include_magnets=True, db=db, storage_location_map=storage_location_map)
            for movie in rows
        ],
        total=total,
    )


@router.get("/filter-config")
def get_filter_config(_current_user: CurrentUser) -> dict:
    return success(data=read_movie_filter_config())


@router.put("/filter-config")
def update_filter_config(body: MovieFilterConfigPayload, _current_user: CurrentUser) -> dict:
    saved = write_movie_filter_config({key: value.model_dump(exclude_none=True) for key, value in body.filters.items()})
    return success(data={"success": True, "filters": saved["filters"]})


@router.post("/storage-sync")
def sync_movie_storage_statuses(
    body: MovieStorageSyncRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    return success(data=sync_movies_from_request(db, str(current_user.id), body))


@router.post("/{movie_id}/storage-sync/cd2")
def sync_single_movie_storage_status_from_cd2(
    movie_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    return success(data=sync_single_movie_from_cd2(db, str(current_user.id), movie_id))


@router.post("/delete")
def delete_content_movies(
    body: MovieDeleteRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    msg, payload = delete_movies_from_request(db, str(current_user.id), body)
    return success(msg=msg, data=payload)


@router.post("/magnet-refresh", status_code=status.HTTP_201_CREATED)
def refresh_movie_magnets(
    body: MovieMagnetRefreshRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    run = create_magnet_refresh_run(db, current_user.id, body.movie_ids)
    return success(data=CrawlRunRead.model_validate(run).model_dump(mode="json"))


@router.get("/{movie_id}")
def get_movie(movie_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    movie = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return success(data=serialize_movie(movie, include_magnets=True, db=db))
