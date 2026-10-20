import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.scraping.config import (
    ScrapingConfigService,
    validate_run_config,
    validate_scrape_root,
)
from backend.app.modules.scraping.scan import scan_directory, schedule_scan_after_strm
from backend.app.modules.scraping.schemas import ScrapingConfigUpdate
from backend.app.modules.scraping.strm import run_strm_generation
from backend.app.modules.scraping.tasks.schemas import ScrapingTaskCreate
from backend.app.modules.scraping.tasks.serializers import item_to_dict, task_to_dict
from backend.app.modules.scraping.tasks.service import ScrapingTaskService
from backend.app.modules.scraping.tasks.worker import ensure_scraping_worker_started
from shared.schemas.common import success

router = APIRouter(prefix="/api/scraping", tags=["scraping"])


@router.get("/config")
def get_scraping_config(_current_user: CurrentUser) -> dict:
    return success(data=ScrapingConfigService().get_public_config())


@router.put("/config")
def update_scraping_config(
    body: ScrapingConfigUpdate,
    _current_user: CurrentUser,
) -> dict:
    try:
        return success(data=ScrapingConfigService().update_config(body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strm/run")
def run_scraping_strm(_current_user: CurrentUser) -> dict:
    config = ScrapingConfigService().get_raw_config()
    reason = validate_run_config(config)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    result = run_strm_generation(config)
    if result.success:
        schedule_scan_after_strm(config)
    return success(data=asdict(result))


@router.post("/scan")
def scan_scraping_directory(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    config = ScrapingConfigService().get_raw_config()
    reason = validate_scrape_root(config)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    return success(data=scan_directory(db, config).to_dict())


@router.post("/tasks")
def create_scraping_task(
    body: ScrapingTaskCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = ScrapingTaskService(db)
    try:
        task = service.create_task(
            list(body.movie_ids),
            current_user.id,
            config=ScrapingConfigService().get_raw_config(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ensure_scraping_worker_started()
    return success(data=task_to_dict(task))


@router.get("/tasks")
def list_scraping_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = 1,
    size: int = 20,
    status: str | None = None,
) -> dict:
    service = ScrapingTaskService(db)
    rows = service.list_tasks(user_id=current_user.id, page=page, size=size, status=status)
    total = service.count_tasks(user_id=current_user.id, status=status)
    return success(data={"rows": [task_to_dict(row) for row in rows], "total": total, "page": page, "size": size})


@router.get("/tasks/{task_id}")
def get_scraping_task(
    task_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = ScrapingTaskService(db)
    try:
        task = service.get_task(uuid.UUID(task_id), current_user.id)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    payload = task_to_dict(task)
    payload["items"] = [item_to_dict(item) for item in task.items]
    return success(data=payload)


@router.post("/tasks/{task_id}/cancel")
def cancel_scraping_task(
    task_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = ScrapingTaskService(db)
    try:
        task = service.cancel_task(uuid.UUID(task_id), current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success(data=task_to_dict(task))


@router.post("/tasks/{task_id}/retry")
def retry_scraping_task(
    task_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = ScrapingTaskService(db)
    try:
        task = service.retry_task(
            uuid.UUID(task_id),
            current_user.id,
            config=ScrapingConfigService().get_raw_config(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ensure_scraping_worker_started()
    return success(data=task_to_dict(task))
