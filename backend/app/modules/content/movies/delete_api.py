from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.delete_service import (
    CloudMovieDeleteError,
    UnsupportedMovieDeleteMode,
    delete_movies,
)
from backend.app.modules.content.movies.nas_delete import (
    UnsafeNasMovieFolder,
    delete_nas_movie_folders,
    resolve_nas_movie_folder,
    validate_nas_targets,
)
from backend.app.modules.scraping.config import ScrapingConfigService
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
    scrape_config = ScrapingConfigService().get_raw_config()
    nas_paths = []
    if body.mode in {"cloud_only", "database_and_cloud"}:
        try:
            nas_paths = [path for movie in movies if (path := resolve_nas_movie_folder(movie, scrape_config)) is not None]
            validate_nas_targets(nas_paths)
        except UnsafeNasMovieFolder as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if nas_paths:
            selected_ids = {movie.id for movie in movies}
            selected_folders = [PurePosixPath(movie.scraping_folder) for movie in movies if movie.scraping_status == "scraped" and movie.scraping_folder]
            others = db.query(Movie).filter(Movie.scraping_status == "scraped").all()
            if any(
                other.id not in selected_ids
                and other.scraping_folder
                and any(
                    folder == PurePosixPath(other.scraping_folder)
                    or folder in PurePosixPath(other.scraping_folder).parents
                    for folder in selected_folders
                )
                for other in others
            ):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="刮削目录被未选中的影片共用")

    try:
        if body.mode in {"cloud_only", "database_and_cloud"}:
            with config_service.open_provider() as (_config, provider):
                result = delete_movies(db=db, movies=movies, mode="cloud_only", provider=provider)
            nas_result = delete_nas_movie_folders(movies, scrape_config)
            result.nas_deleted_folders = nas_result.deleted_folders
            result.nas_missing_folders = nas_result.missing_folders
            result.nas_failed_folders = nas_result.failed_folders
            if result.nas_failed_folders:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={"message": "删除 NAS 刮削文件夹失败", "data": result.to_dict()},
                )
            for movie in movies:
                if movie.scraping_status == "scraped":
                    movie.scraping_status = "not_scraped"
                    movie.scraping_folder = None
            if body.mode == "database_and_cloud":
                database_result = delete_movies(db=db, movies=movies, mode="database_only")
                result.deleted_movies = database_result.deleted_movies
                result.deleted_magnets = database_result.deleted_magnets
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
            detail={"message": "删除云存储文件夹失败", "data": {"failed_folders": exc.failed_folders}},
        ) from exc

    if body.mode == "cloud_only":
        from backend.app.modules.storage.tasks.events import publish_movie_storage_updated
        for movie in movies:
            publish_movie_storage_updated(db, user_id, movie.id)

    if nas_paths and scrape_config.get("jellyfin_auto_refresh_enabled"):
        from backend.app.modules.jellyfin.refresh import refresh_libraries_for_paths
        try:
            refresh_libraries_for_paths(scrape_config, nas_paths)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Jellyfin refresh after NAS deletion failed")

    return "删除成功", result.to_dict()
