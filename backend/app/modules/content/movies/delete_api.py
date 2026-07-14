from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.delete_service import (
    CloudMovieDeleteError,
    UnsupportedMovieDeleteMode,
    delete_movies,
)
from backend.app.modules.content.movies.schemas import MovieDeleteRequest
from shared.database.models.content import Movie


def delete_movies_from_request(db: Session, user_id: str, body: MovieDeleteRequest) -> tuple[str, dict]:
    if not body.movie_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要删除的影片")

    movies = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id.in_(body.movie_ids)).all()
    if not movies:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="影片不存在")

    from backend.app.modules.storage.config.service import StorageConfigService

    config_service = StorageConfigService()

    try:
        if body.mode in {"cloud_only", "database_and_cloud"}:
            with config_service.open_provider() as (_config, provider):
                result = delete_movies(db=db, movies=movies, mode=body.mode, provider=provider)
        else:
            result = delete_movies(db=db, movies=movies, mode=body.mode, provider=None)
        db.commit()
    except UnsupportedMovieDeleteMode as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CloudMovieDeleteError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "删除云存储文件夹失败", "failed_folders": exc.failed_folders},
        ) from exc

    if body.mode == "cloud_only":
        from backend.app.modules.storage.tasks.events import publish_movie_storage_updated
        for movie in movies:
            publish_movie_storage_updated(db, user_id, movie.id)

    return "删除成功", result.to_dict()
