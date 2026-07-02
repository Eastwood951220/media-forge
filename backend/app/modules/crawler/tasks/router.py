import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.models.crawl_task import CrawlTask
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskRead,
    CrawlTaskUpdate,
)
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/crawler/tasks", tags=["crawler-tasks"])


@router.get("")
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    repo = CrawlTaskRepository(db)
    rows = repo.get_by_owner(current_user.id, skip=skip, limit=limit, keyword=keyword)
    total = repo.count_by_owner(current_user.id, keyword=keyword)
    return paginated(rows=[CrawlTaskRead.model_validate(row) for row in rows], total=total)


@router.get("/stats")
def get_stats(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    repo = CrawlTaskRepository(db)
    return success(data={"total": repo.count_by_owner(current_user.id)})


@router.get("/{task_id}")
def get_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return success(data=CrawlTaskRead.model_validate(task))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    data: CrawlTaskCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    task = CrawlTask(**data.model_dump(), owner_id=current_user.id)
    repo = CrawlTaskRepository(db)
    created = repo.create(task)
    return success(data=CrawlTaskRead.model_validate(created))


@router.put("/{task_id}")
def update_task(
    task_id: uuid.UUID,
    data: CrawlTaskUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    updated = repo.update(task)
    return success(data=CrawlTaskRead.model_validate(updated))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    repo.delete(task)
