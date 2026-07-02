"""Movie list and task stats endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlRunRead,
    MovieListItem,
    TaskStatsResponse,
)
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/movies", tags=["movies"])
logger = logging.getLogger(__name__)


@router.get("")
def list_movies(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    task_status: str | None = Query(default=None, description="Filter by task status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List movies from crawl task URLs with optional status filter."""
    repo = CrawlTaskRepository(db)

    if task_status:
        tasks = repo.get_by_status(
            current_user.id,
            task_status=task_status,
            skip=skip,
            limit=limit,
        )
        total = repo.count_by_status(current_user.id, task_status=task_status)
    else:
        tasks = repo.get_by_owner(current_user.id, skip=skip, limit=limit)
        total = repo.count_by_owner(current_user.id)

    # Flatten task URLs into movie list items
    items: list[dict] = []
    for task in tasks:
        latest_run = repo.get_latest_run(task.id)
        for url in task.urls:
            items.append(
                MovieListItem(
                    id=url.id,
                    task_id=task.id,
                    task_name=task.name,
                    status=task.status,
                    url=url.url,
                    url_type=url.url_type,
                    source=url.source,
                    has_magnet=url.has_magnet,
                    has_chinese_sub=url.has_chinese_sub,
                    created_at=url.created_at,
                    updated_at=url.updated_at,
                    last_run_status=latest_run.status if latest_run else None,
                    last_run_at=latest_run.created_at if latest_run else None,
                ).model_dump(mode="json")
            )

    return paginated(rows=items, total=total)


@router.get("/{task_id}/stats")
def get_task_stats(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    """Get task statistics with recent crawl runs."""
    repo = CrawlTaskRepository(db)

    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    runs = repo.get_latest_runs(current_user.id, task_id=task_id, limit=10)

    total_found = sum(r.total_found for r in runs)
    total_qualified = sum(r.total_qualified for r in runs)

    return success(
        data=TaskStatsResponse(
            task_id=task.id,
            task_name=task.name,
            total_runs=len(runs),
            total_found_all_time=total_found,
            total_qualified_all_time=total_qualified,
            recent_runs=[CrawlRunRead.model_validate(r).model_dump(mode="json") for r in runs],
        ).model_dump(mode="json")
    )
