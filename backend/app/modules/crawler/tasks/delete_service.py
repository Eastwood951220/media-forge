"""Service for cascading task deletion to associated movies."""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie

logger = logging.getLogger(__name__)


def delete_movies_by_task_id(db: Session, task_id: uuid.UUID | str) -> int:
    """Delete all movies associated with a crawler task.

    Args:
        db: Database session
        task_id: The crawler task ID whose movies should be deleted

    Returns:
        Number of movies deleted
    """
    # Convert to string for comparison since column is String(36)
    task_id_str = str(task_id)

    # Find movies with this source_task_id
    movies = db.scalars(
        select(Movie).where(Movie.source_task_id == task_id_str)
    ).all()

    if not movies:
        return 0

    count = len(movies)
    for movie in movies:
        db.delete(movie)

    db.flush()
    logger.info("Deleted %d movies for task %s", count, task_id)
    return count


def delete_movies_by_task_ids(db: Session, task_ids: list[uuid.UUID | str]) -> int:
    """Delete all movies associated with multiple crawler tasks.

    Args:
        db: Database session
        task_ids: List of crawler task IDs whose movies should be deleted

    Returns:
        Number of movies deleted
    """
    if not task_ids:
        return 0

    # Convert to strings for comparison since column is String(36)
    task_id_strings = [str(tid) for tid in task_ids]

    movies = db.scalars(
        select(Movie).where(Movie.source_task_id.in_(task_id_strings))
    ).all()

    if not movies:
        return 0

    count = len(movies)
    for movie in movies:
        db.delete(movie)

    db.flush()
    logger.info("Deleted %d movies for tasks %s", count, task_ids)
    return count
