"""Service for task deletion with different modes.

Modes:
- task_only: Delete task, runs, and detail tasks but keep movies
- task_and_movies: Delete task and associated movies (for shared movies, remove task ID)
- task_movies_and_cloud: Not implemented (placeholder for future cloud storage cleanup)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import any_, select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie, MovieMagnet

logger = logging.getLogger(__name__)

DeleteMode = Literal["task_only", "task_and_movies", "task_movies_and_cloud"]
VALID_DELETE_MODES = {"task_only", "task_and_movies", "task_movies_and_cloud"}


class UnsupportedDeleteMode(ValueError):
    pass


class CloudDeleteNotImplemented(RuntimeError):
    pass


@dataclass
class DeleteTaskResult:
    deleted_task: bool
    deleted_runs: int
    deleted_detail_tasks: int
    updated_movies: int
    deleted_movies: int
    deleted_magnets: int
    cloud_delete: str

    def to_dict(self) -> dict:
        return {
            "deleted_task": self.deleted_task,
            "deleted_runs": self.deleted_runs,
            "deleted_detail_tasks": self.deleted_detail_tasks,
            "updated_movies": self.updated_movies,
            "deleted_movies": self.deleted_movies,
            "deleted_magnets": self.deleted_magnets,
            "cloud_delete": self.cloud_delete,
        }


def _contains_task_id(values: list, task_id: str) -> bool:
    """Check if task_id exists in a list of UUID values."""
    return task_id in {str(value) for value in (values or [])}


def _remove_task_id(values: list, task_id: str) -> list:
    """Remove task_id from a list of UUID values."""
    return [value for value in (values or []) if str(value) != task_id]


def delete_task(
    db: Session,
    task_id: uuid.UUID,
    *,
    mode: DeleteMode = "task_only",
) -> DeleteTaskResult:
    """Delete a crawler task with the specified mode.

    Args:
        db: Database session
        task_id: The task ID to delete
        mode: Deletion mode

    Returns:
        DeleteTaskResult with counts of deleted items

    Raises:
        UnsupportedDeleteMode: If mode is invalid
        CloudDeleteNotImplemented: If mode is task_movies_and_cloud
    """
    if mode not in VALID_DELETE_MODES:
        raise UnsupportedDeleteMode(f"Unsupported delete mode: {mode}")

    if mode == "task_movies_and_cloud":
        raise CloudDeleteNotImplemented("Cloud storage cleanup is not yet implemented")

    task = db.get(CrawlTask, task_id)
    if task is None:
        return DeleteTaskResult(
            deleted_task=False,
            deleted_runs=0,
            deleted_detail_tasks=0,
            updated_movies=0,
            deleted_movies=0,
            deleted_magnets=0,
            cloud_delete="skipped",
        )

    # Count and delete runs and detail tasks
    runs = db.scalars(select(CrawlRun).where(CrawlRun.task_id == task_id)).all()
    deleted_runs = len(runs)
    deleted_detail_tasks = 0

    for run in runs:
        details = db.scalars(
            select(CrawlRunDetailTask).where(CrawlRunDetailTask.run_id == run.id)
        ).all()
        deleted_detail_tasks += len(details)
        for detail in details:
            db.delete(detail)
        db.delete(run)

    # Handle movies based on mode
    updated_movies = 0
    deleted_movies = 0
    deleted_magnets = 0

    task_id_str = str(task_id)

    if mode == "task_and_movies":
        # Find movies that reference this task
        # For PostgreSQL ARRAY, we need to check if task_id is in the array
        all_movies = db.scalars(select(Movie)).all()
        movies = [m for m in all_movies if _contains_task_id(m.source_task_ids, task_id_str)]

        for movie in movies:
            task_ids = list(movie.source_task_ids or [])
            if _contains_task_id(task_ids, task_id_str):
                if len(task_ids) <= 1:
                    # Single source - delete the movie and its magnets
                    magnets = db.scalars(
                        select(MovieMagnet).where(MovieMagnet.movie_id == movie.id)
                    ).all()
                    deleted_magnets += len(magnets)
                    for magnet in magnets:
                        db.delete(magnet)
                    db.delete(movie)
                    deleted_movies += 1
                else:
                    # Multiple sources - just remove this task ID
                    movie.source_task_ids = _remove_task_id(task_ids, task_id_str)
                    updated_movies += 1

    # Delete the task itself
    db.delete(task)
    db.flush()

    logger.info(
        "Deleted task %s (mode=%s): runs=%d, details=%d, updated_movies=%d, deleted_movies=%d, deleted_magnets=%d",
        task_id, mode, deleted_runs, deleted_detail_tasks, updated_movies, deleted_movies, deleted_magnets
    )

    return DeleteTaskResult(
        deleted_task=True,
        deleted_runs=deleted_runs,
        deleted_detail_tasks=deleted_detail_tasks,
        updated_movies=updated_movies,
        deleted_movies=deleted_movies,
        deleted_magnets=deleted_magnets,
        cloud_delete="skipped" if mode != "task_movies_and_cloud" else "pending",
    )
