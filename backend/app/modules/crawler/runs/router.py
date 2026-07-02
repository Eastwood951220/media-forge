import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.modules.crawler.runs.schemas import CrawlRunDetailTaskRead, CrawlRunRead
from backend.app.modules.crawler.runtime.service import get_runtime_state
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/crawler/runs", tags=["crawler-runs"])


@router.get("/queue-status")
def queue_status(_current_user: CurrentUser) -> dict:
    return success(data=get_runtime_state().queue_status())


@router.get("")
def list_runs(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    task_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict:
    query = db.query(CrawlRun)
    if task_id is not None:
        query = query.filter(CrawlRun.task_id == task_id)
    if status_filter is not None:
        query = query.filter(CrawlRun.status == status_filter)
    total = query.count()
    rows = query.order_by(CrawlRun.created_at.desc()).offset(skip).limit(limit).all()
    return paginated(
        rows=[CrawlRunRead.model_validate(r).model_dump(mode="json") for r in rows],
        total=total,
    )


@router.get("/{run_id}")
def get_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return success(data=CrawlRunRead.model_validate(run).model_dump(mode="json"))


@router.get("/{run_id}/tasks")
def list_run_tasks(
    run_id: uuid.UUID,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    query = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run_id)
    if status_filter is not None:
        query = query.filter(CrawlRunDetailTask.status == status_filter)
    if keyword:
        query = query.filter(
            CrawlRunDetailTask.code.ilike(f"%{keyword}%")
            | CrawlRunDetailTask.source_name.ilike(f"%{keyword}%")
        )
    total = query.count()
    rows = query.order_by(CrawlRunDetailTask.created_at.asc()).offset(skip).limit(limit).all()
    return paginated(
        rows=[CrawlRunDetailTaskRead.model_validate(r).model_dump(mode="json") for r in rows],
        total=total,
    )
