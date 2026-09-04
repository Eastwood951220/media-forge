import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleCreate, CrawlerScheduleListResponse, CrawlerScheduleUpdate
from backend.app.modules.crawler.schedules.serializers import serialize_schedule


def normalize_weekdays(schedule_type: str, weekdays: list[int]) -> list[int]:
    if schedule_type == "daily":
        return []
    normalized = sorted(set(weekdays))
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="每周定时至少选择一天")
    if any(day < 0 or day > 6 for day in normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="星期只能是 0 到 6")
    return normalized


def calculate_next_run_at(schedule_type: str, time_of_day: str, weekdays: list[int], now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    hour, minute = [int(part) for part in time_of_day.split(":", 1)]
    if schedule_type == "daily":
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate if candidate > now else candidate + timedelta(days=1)
    normalized = normalize_weekdays(schedule_type, weekdays)
    for offset in range(0, 8):
        candidate_day = now + timedelta(days=offset)
        if candidate_day.weekday() not in normalized:
            continue
        candidate = candidate_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法计算下次执行时间")


class CrawlerScheduleService:
    def __init__(self, db: Session, scheduler=None) -> None:
        self.db = db
        self.scheduler = scheduler

    def _owned_tasks(self, task_ids: list[uuid.UUID], owner_id: uuid.UUID) -> list[CrawlTask]:
        unique_ids = list(dict.fromkeys(task_ids))
        if not unique_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择 1 个任务")
        tasks = self.db.query(CrawlTask).filter(CrawlTask.owner_id == owner_id, CrawlTask.id.in_(unique_ids)).all()
        by_id = {task.id: task for task in tasks}
        if len(by_id) != len(unique_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务不存在或无权限")
        return [by_id[task_id] for task_id in unique_ids]

    def _sync_job(self, schedule: CrawlerSchedule) -> None:
        if self.scheduler is None:
            return
        if schedule.enabled:
            self.scheduler.upsert_schedule_job(schedule)
        else:
            self.scheduler.remove_schedule_job(schedule.id)

    def create_schedule(self, data: CrawlerScheduleCreate, owner_id: uuid.UUID) -> CrawlerSchedule:
        tasks = self._owned_tasks(list(data.task_ids), owner_id)
        weekdays = normalize_weekdays(data.schedule_type, data.weekdays)
        schedule = CrawlerSchedule(
            owner_id=owner_id,
            name=data.name.strip(),
            enabled=data.enabled,
            schedule_type=data.schedule_type,
            time_of_day=data.time_of_day,
            weekdays=weekdays,
            auto_storage_enabled=data.auto_storage_enabled,
            storage_mode=data.storage_mode,
            selected_storage_location=(data.selected_storage_location or "").strip() or None,
            next_run_at=calculate_next_run_at(data.schedule_type, data.time_of_day, weekdays),
        )
        schedule.tasks = tasks
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        self._sync_job(schedule)
        return schedule

    def get_owned_model(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlerSchedule:
        schedule = self.db.get(CrawlerSchedule, schedule_id)
        if schedule is None or schedule.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时配置不存在")
        return schedule

    def get_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> dict:
        return serialize_schedule(self.get_owned_model(schedule_id, owner_id)).model_dump(mode="json")

    def list_schedules(self, owner_id: uuid.UUID, *, page: int, size: int) -> dict:
        query = self.db.query(CrawlerSchedule).filter(CrawlerSchedule.owner_id == owner_id)
        total = query.count()
        rows = query.order_by(CrawlerSchedule.created_at.desc()).offset((page - 1) * size).limit(size).all()
        return CrawlerScheduleListResponse(
            rows=[serialize_schedule(row) for row in rows],
            total=total,
            page=page,
            size=size,
        ).model_dump(mode="json")

    def update_schedule(self, schedule_id: uuid.UUID, data: CrawlerScheduleUpdate, owner_id: uuid.UUID) -> CrawlerSchedule:
        schedule = self.get_owned_model(schedule_id, owner_id)
        update_data = data.model_dump(exclude_unset=True)
        if any(key in update_data and update_data[key] is None for key in ("schedule_type", "time_of_day", "weekdays")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="定时类型、执行时间和星期不能为空")
        if "name" in update_data and update_data["name"] is not None:
            schedule.name = update_data["name"].strip()
        next_type = update_data.get("schedule_type", schedule.schedule_type)
        next_time = update_data.get("time_of_day", schedule.time_of_day)
        next_weekdays = update_data.get("weekdays", schedule.weekdays or [])
        if "schedule_type" in update_data or "time_of_day" in update_data or "weekdays" in update_data:
            schedule.schedule_type = next_type
            schedule.time_of_day = next_time
            schedule.weekdays = normalize_weekdays(next_type, next_weekdays)
            schedule.next_run_at = calculate_next_run_at(schedule.schedule_type, schedule.time_of_day, schedule.weekdays)
        if "enabled" in update_data and update_data["enabled"] is not None:
            schedule.enabled = update_data["enabled"]
        if "auto_storage_enabled" in update_data and update_data["auto_storage_enabled"] is not None:
            schedule.auto_storage_enabled = update_data["auto_storage_enabled"]
        if "storage_mode" in update_data and update_data["storage_mode"] is not None:
            schedule.storage_mode = update_data["storage_mode"]
        if "selected_storage_location" in update_data:
            schedule.selected_storage_location = (update_data["selected_storage_location"] or "").strip() or None
        if data.task_ids is not None:
            schedule.tasks = self._owned_tasks(list(data.task_ids), owner_id)
        self.db.commit()
        self.db.refresh(schedule)
        self._sync_job(schedule)
        return schedule

    def delete_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> dict:
        schedule = self.get_owned_model(schedule_id, owner_id)
        self.db.delete(schedule)
        self.db.commit()
        if self.scheduler is not None:
            self.scheduler.remove_schedule_job(schedule_id)
        return {"id": str(schedule_id)}

    def enable_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlerSchedule:
        schedule = self.get_owned_model(schedule_id, owner_id)
        schedule.enabled = True
        schedule.next_run_at = calculate_next_run_at(schedule.schedule_type, schedule.time_of_day, schedule.weekdays)
        self.db.commit()
        self.db.refresh(schedule)
        self._sync_job(schedule)
        return schedule

    def disable_schedule(self, schedule_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlerSchedule:
        schedule = self.get_owned_model(schedule_id, owner_id)
        schedule.enabled = False
        self.db.commit()
        self.db.refresh(schedule)
        self._sync_job(schedule)
        return schedule

    def list_schedule_runs(self, schedule_id: uuid.UUID, owner_id: uuid.UUID, *, page: int, size: int) -> dict:
        schedule = self.get_owned_model(schedule_id, owner_id)
        query = self.db.query(CrawlerScheduleRun).filter(CrawlerScheduleRun.schedule_id == schedule.id)
        total = query.count()
        rows = query.order_by(CrawlerScheduleRun.triggered_at.desc()).offset((page - 1) * size).limit(size).all()
        return {
            "rows": [
                {
                    "id": str(row.id),
                    "schedule_id": str(row.schedule_id),
                    "status": row.status,
                    "trigger_type": row.trigger_type,
                    "triggered_at": row.triggered_at,
                    "finished_at": row.finished_at,
                    "result": row.result or {},
                    "storage_status": row.storage_status,
                    "storage_task_id": str(row.storage_task_id) if row.storage_task_id else None,
                    "storage_error": row.storage_error,
                    "crawl_run_ids": [str(link.crawl_run_id) for link in row.crawl_run_links],
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "size": size,
        }
