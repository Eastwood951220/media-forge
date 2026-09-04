import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.crawler.schedules.executor import execute_schedule
from backend.app.modules.crawler.schedules.scheduler import crawler_schedule_scheduler
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleCreate, CrawlerScheduleUpdate
from backend.app.modules.crawler.schedules.serializers import serialize_schedule
from backend.app.modules.crawler.schedules.service import CrawlerScheduleService
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/schedules", tags=["crawler-schedules"])


def get_service(db: Session) -> CrawlerScheduleService:
    return CrawlerScheduleService(db, scheduler=crawler_schedule_scheduler)


@router.get("")
def list_schedules(current_user: CurrentUser, db: Session = Depends(get_db), page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)) -> dict:
    return success(data=get_service(db).list_schedules(current_user.id, page=page, size=size))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_schedule(data: CrawlerScheduleCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=serialize_schedule(get_service(db).create_schedule(data, current_user.id)).model_dump(mode="json"))


@router.post("/{schedule_id}/disable")
def disable_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=serialize_schedule(get_service(db).disable_schedule(schedule_id, current_user.id)).model_dump(mode="json"))


@router.get("/{schedule_id}")
def get_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=get_service(db).get_schedule(schedule_id, current_user.id))


@router.put("/{schedule_id}")
def update_schedule(schedule_id: uuid.UUID, data: CrawlerScheduleUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    schedule = get_service(db).update_schedule(schedule_id, data, current_user.id)
    return success(data=serialize_schedule(schedule).model_dump(mode="json"))


@router.post("/{schedule_id}/enable")
def enable_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    schedule = get_service(db).enable_schedule(schedule_id, current_user.id)
    return success(data=serialize_schedule(schedule).model_dump(mode="json"))


@router.post("/{schedule_id}/trigger", status_code=status.HTTP_201_CREATED)
def trigger_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    get_service(db).get_owned_model(schedule_id, current_user.id)
    history = execute_schedule(schedule_id, trigger_type="manual")
    return success(data={"schedule_run_id": str(history.id) if history else None})


@router.get("/{schedule_id}/runs")
def list_schedule_runs(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db), page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)) -> dict:
    return success(data=get_service(db).list_schedule_runs(schedule_id, current_user.id, page=page, size=size))


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=get_service(db).delete_schedule(schedule_id, current_user.id))
