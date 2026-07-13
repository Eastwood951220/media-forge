import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.crawler.runs.schemas import RunCreateRequest
from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
from backend.app.modules.crawler.tasks.runtime_status import build_task_runtime_status_response
from backend.app.modules.crawler.tasks.service import CrawlerTaskService
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskUpdate,
    ExtractNameRequest,
    TemporaryCrawlRunCreate,
)
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/crawler/tasks", tags=["crawler-tasks"])


@router.get("")
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=1000),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    service = CrawlerTaskService(db)
    data = service.list_tasks(current_user.id, skip=skip, limit=limit, keyword=keyword)
    return paginated(rows=data["rows"], total=data["total"])


@router.get("/stats")
def get_stats(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.get_stats(current_user.id))


@router.get("/dict")
def task_dict(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    """Return task ID-to-name mapping for frontend use."""
    service = CrawlerTaskService(db)
    return success(data=service.task_dict(current_user.id))


@router.get("/statuses")
def list_task_runtime_statuses(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    """Return derived runtime status for all tasks.

    Status is derived from each task's latest crawl run, not persisted.
    """
    payload = build_task_runtime_status_response(db, current_user.id)
    return success(data=payload.model_dump(mode="json"))


@router.post("/temp-run", status_code=status.HTTP_201_CREATED)
def create_temporary_run(
    data: TemporaryCrawlRunCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.create_temporary_run(data, current_user.id))


@router.post("/extract-name")
def extract_name(body: ExtractNameRequest, _current_user: CurrentUser) -> dict:
    return success(data={"name": extract_task_name(body)})


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.get_task(task_id, current_user.id))


@router.post("/{task_id}/run", status_code=status.HTTP_201_CREATED)
def run_task(
    task_id: uuid.UUID,
    data: RunCreateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.run_task(task_id, data, current_user.id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(data: CrawlTaskCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.create_task(data, current_user.id))


@router.put("/{task_id}")
def update_task(
    task_id: uuid.UUID,
    data: CrawlTaskUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.update_task(task_id, data, current_user.id))


@router.delete("/{task_id}")
def delete_task_endpoint(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    mode: str = Query(default="task_only", description="Delete mode: task_only, task_and_movies, task_movies_and_cloud"),
) -> dict:
    service = CrawlerTaskService(db)
    return success(msg="删除成功", data=service.delete_task(task_id, current_user.id, mode=mode))
