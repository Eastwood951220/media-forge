import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.dependencies import CurrentUser, get_db
from shared.database.models.content import Movie, MovieFilter
from backend.app.modules.content.movies.filter_config import (
    MovieFilterConfigPayload,
    read_movie_filter_config,
    write_movie_filter_config,
)
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/content/movies", tags=["content-movies"])

ALLOWED_SORT_FIELDS = {
    "created_at": Movie.created_at,
    "updated_at": Movie.updated_at,
    "code": Movie.code,
    "source_name": Movie.source_name,
    "release_date": Movie.release_date,
    "rating": Movie.rating,
}

VALID_FILTER_TYPES = {"actor", "tag", "director", "maker", "series"}


def _unique_sorted(values: list[str | None]) -> list[str]:
    return sorted({value for value in values if value})


def _sqlite_filter_values(db: Session, filter_type: str) -> list[str]:
    movies = db.query(Movie).all()
    if filter_type == "actor":
        return _unique_sorted([actor for movie in movies for actor in (movie.actors or [])])
    if filter_type == "tag":
        return _unique_sorted([tag for movie in movies for tag in (movie.tags or [])])
    return _unique_sorted([getattr(movie, filter_type) for movie in movies])


def _cached_filter_values(db: Session, filter_type: str) -> list[str]:
    return list(db.scalars(
        select(MovieFilter.name)
        .where(MovieFilter.type == filter_type, MovieFilter.name != "")
        .distinct()
        .order_by(MovieFilter.name.asc())
    ).all())


def _movie_payload(movie: Movie, *, include_magnets: bool = False, db: Session | None = None) -> dict:
    source_task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
    storage_locations: list[str] = []
    if db and source_task_ids:
        from backend.app.models.crawl_task import CrawlTask
        for task_id_str in source_task_ids:
            try:
                task_id = uuid.UUID(task_id_str)
            except (ValueError, TypeError):
                continue
            crawl_task = db.get(CrawlTask, task_id)
            if crawl_task and crawl_task.storage_location:
                loc = crawl_task.storage_location
                if loc not in storage_locations:
                    storage_locations.append(loc)
    payload = {
        "_id": str(movie.id),
        "id": str(movie.id),
        "code": movie.code or "",
        "source_url": movie.source_url or "",
        "source_name": movie.source_name or "",
        "cover": movie.cover or "",
        "release_date": movie.release_date.isoformat() if movie.release_date else None,
        "duration": movie.duration or 0,
        "director": movie.director or "",
        "maker": movie.maker or "",
        "series": movie.series or "",
        "rating": float(movie.rating) if movie.rating is not None else None,
        "actors": list(movie.actors or []),
        "tags": list(movie.tags or []),
        "source_task_ids": source_task_ids,
        "storage_locations": storage_locations,
        "marked": bool(movie.marked),
        "storage_summary": movie.storage_summary or {},
        "raw_detail": movie.raw_detail or {},
        "created_at": movie.created_at.isoformat() if movie.created_at else None,
        "updated_at": movie.updated_at.isoformat() if movie.updated_at else None,
    }
    if include_magnets:
        payload["magnets"] = [
            {
                "_id": str(magnet.id),
                "id": str(magnet.id),
                "movie_id": str(magnet.movie_id),
                "magnet": magnet.magnet_url,
                "magnet_url": magnet.magnet_url,
                "name": magnet.name or "",
                "title": magnet.name or "",
                "size": magnet.size_text or "",
                "size_mb": float(magnet.size_mb or 0),
                "size_text": magnet.size_text or "",
                "file_count": magnet.file_count,
                "file_text": magnet.file_text or "",
                "tags": magnet.tags or [],
                "has_chinese_sub": bool(magnet.has_chinese_sub),
                "date": magnet.date or "",
                "dedupe_key": magnet.dedupe_key or "",
                "weight": magnet.weight or 0,
                "selected": bool(magnet.selected),
            }
            for magnet in (movie.magnets or [])
        ]
        selected = next((magnet for magnet in movie.magnets or [] if magnet.selected), None)
        payload["selected_magnet_dedupe_key"] = selected.dedupe_key if selected else None
    return payload


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def _movie_matches_python(
    movie: Movie,
    *,
    search: str | None,
    source_task_id: str | None,
    rating_min: float | None,
    rating_max: float | None,
    actors: str | None,
    actors_not: str | None,
    actors_count_min: int | None,
    actors_count_max: int | None,
    tags: str | None,
    tags_not: str | None,
    director: str | None,
    director_not: str | None,
    maker: str | None,
    maker_not: str | None,
    series: str | None,
    series_not: str | None,
    release_date_from: str | None,
    release_date_to: str | None,
    created_at_from: str | None,
    created_at_to: str | None,
    storage_status: str | None,
) -> bool:
    if search:
        needle = search.lower()
        haystack = " ".join([movie.code or "", movie.source_name or "", movie.director or "", movie.maker or "", movie.series or ""]).lower()
        if needle not in haystack:
            return False
    if source_task_id:
        task_ids = [str(tid) for tid in (movie.source_task_ids or [])]
        if source_task_id not in task_ids:
            return False
    if rating_min is not None and (movie.rating is None or float(movie.rating) < rating_min):
        return False
    if rating_max is not None and (movie.rating is None or float(movie.rating) > rating_max):
        return False
    movie_actors = set(movie.actors or [])
    movie_tags = set(movie.tags or [])
    if _split_csv(actors) and not set(_split_csv(actors)).issubset(movie_actors):
        return False
    if _split_csv(actors_not) and set(_split_csv(actors_not)).intersection(movie_actors):
        return False
    if _split_csv(tags) and not set(_split_csv(tags)).issubset(movie_tags):
        return False
    if _split_csv(tags_not) and set(_split_csv(tags_not)).intersection(movie_tags):
        return False
    if _split_csv(director) and movie.director not in _split_csv(director):
        return False
    if _split_csv(director_not) and movie.director in _split_csv(director_not):
        return False
    if _split_csv(maker) and movie.maker not in _split_csv(maker):
        return False
    if _split_csv(maker_not) and movie.maker in _split_csv(maker_not):
        return False
    if _split_csv(series) and movie.series not in _split_csv(series):
        return False
    if _split_csv(series_not) and movie.series in _split_csv(series_not):
        return False
    if actors_count_min is not None and len(movie.actors or []) < actors_count_min:
        return False
    if actors_count_max is not None and len(movie.actors or []) > actors_count_max:
        return False
    if release_date_from and (movie.release_date is None or movie.release_date.isoformat() < release_date_from):
        return False
    if release_date_to and (movie.release_date is None or movie.release_date.isoformat() > release_date_to):
        return False
    if created_at_from and (movie.created_at is None or movie.created_at.date().isoformat() < created_at_from):
        return False
    if created_at_to and (movie.created_at is None or movie.created_at.date().isoformat() > created_at_to):
        return False
    last_status = (movie.storage_summary or {}).get("last_status")
    if storage_status == "not_stored":
        return not last_status
    if storage_status and last_status != storage_status:
        return False
    return True


@router.get("/filters")
def list_filters(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    type: str = Query(..., description="actor, tag, director, maker, series"),
) -> dict:
    if type not in VALID_FILTER_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid filter type: {type}")

    cached_names = _cached_filter_values(db, type)
    if cached_names:
        return success(data=cached_names)

    if db.bind.dialect.name == "sqlite":
        return success(data=_sqlite_filter_values(db, type))
    if type == "actor":
        names = db.scalars(select(func.unnest(Movie.actors).label("name")).distinct().order_by("name")).all()
    elif type == "tag":
        names = db.scalars(select(func.unnest(Movie.tags).label("name")).distinct().order_by("name")).all()
    else:
        column = getattr(Movie, type)
        names = db.scalars(select(column).where(column != "", column.is_not(None)).distinct().order_by(column.asc())).all()
    return success(data=[name for name in names if name])


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
    try:
        normalized_sort_order = int(sort_order)
    except (TypeError, ValueError):
        normalized_sort_order = 1 if sort_order == "asc" else -1
    if normalized_sort_order not in (-1, 1):
        normalized_sort_order = -1

    rows = db.query(Movie).options(selectinload(Movie.magnets)).all()
    filtered = [
        movie for movie in rows
        if _movie_matches_python(
            movie,
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
        )
    ]

    sort_column = sort_by if sort_by in ALLOWED_SORT_FIELDS else "created_at"
    filtered.sort(key=lambda movie: getattr(movie, sort_column) is None)
    filtered.sort(key=lambda movie: getattr(movie, sort_column) or "", reverse=normalized_sort_order == -1)

    total = len(filtered)
    offset = skip if skip is not None else (page - 1) * limit
    page_rows = filtered[offset:offset + limit]
    return paginated(rows=[_movie_payload(movie, include_magnets=True, db=db) for movie in page_rows], total=total)


@router.get("/filter-config")
def get_filter_config(_current_user: CurrentUser) -> dict:
    return success(data=read_movie_filter_config())


@router.put("/filter-config")
def update_filter_config(body: MovieFilterConfigPayload, _current_user: CurrentUser) -> dict:
    saved = write_movie_filter_config({key: value.model_dump(exclude_none=True) for key, value in body.filters.items()})
    return success(data={"success": True, "filters": saved["filters"]})


@router.get("/{movie_id}")
def get_movie(movie_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    movie = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return success(data=_movie_payload(movie, include_magnets=True, db=db))
