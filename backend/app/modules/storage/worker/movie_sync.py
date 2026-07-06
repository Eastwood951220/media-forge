from __future__ import annotations

from sqlalchemy.orm import Session


def sync_movie_storage_after_subtask(db: Session, context) -> None:
    from backend.app.modules.content.movies.storage_locations import target_folder_specs_from_subtask
    from backend.app.modules.content.movies.storage_status import (
        STORAGE_STATUS_NOT_STORED,
        set_movie_storage_status,
        sync_movie_storage_status,
    )
    from backend.app.modules.storage.tasks.events import publish_movie_storage_updated
    from shared.database.models.content import Movie

    movie = db.get(Movie, context.subtask.movie_id)
    if movie is None:
        return
    if context.subtask.status == "completed":
        sync_movie_storage_status(
            db=db,
            movie=movie,
            provider=context.provider,
            config=context.config,
            source="storage_worker",
            target_folders=target_folder_specs_from_subtask(context.subtask),
            main_task_id=str(context.main_task.id),
            sub_task_id=str(context.subtask.id),
            storage_mode=context.subtask.storage_mode,
        )
    elif context.subtask.status in {"failed", "skipped"}:
        set_movie_storage_status(
            movie,
            STORAGE_STATUS_NOT_STORED,
            source="storage_worker",
            main_task_id=str(context.main_task.id),
            sub_task_id=str(context.subtask.id),
            storage_mode=context.subtask.storage_mode,
        )
    db.flush()
    publish_movie_storage_updated(db, context.owner_id, movie.id)
