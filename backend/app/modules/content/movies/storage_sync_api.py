from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.schemas import MovieStorageSyncRequest
from backend.app.modules.content.movies.storage_sync_service import (
    select_movies_for_storage_sync,
    sync_movies_storage_statuses,
    sync_single_movie_storage_status_from_cd2,
)
from backend.app.modules.storage.index.store import StorageIndexMissingError
from shared.database.models.content import Movie


def sync_movies_from_request(db: Session, user_id: str, body: MovieStorageSyncRequest) -> dict:
    filters = body.filters.model_dump() if body.filters else {}
    movies = select_movies_for_storage_sync(db, movie_ids=body.movie_ids, filters=filters)
    try:
        payload = sync_movies_storage_statuses(db, user_id=user_id, movies=movies)
    except StorageIndexMissingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return payload.to_dict()


def sync_single_movie_from_cd2(db: Session, user_id: str, movie_id: uuid.UUID) -> dict:
    movie = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="影片不存在")
    return sync_single_movie_storage_status_from_cd2(db, user_id=user_id, movie=movie)
