from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawler_schedule import CrawlerScheduleRun, CrawlerScheduleRunCrawlRun
from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState
from backend.app.modules.storage.tasks.service import StorageTaskService
from backend.app.core.dependencies import get_redis
from backend.app.modules.storage.config.service import StorageConfigService

TERMINAL_RUN_STATUSES = {"completed", "failed", "stopped"}


def process_schedule_run_completion(db: Session, run: CrawlRun) -> None:
    if run.schedule_run_id is None:
        return
    schedule_run = db.get(CrawlerScheduleRun, run.schedule_run_id)
    if schedule_run is None or schedule_run.storage_status in {"created", "skipped", "failed"}:
        return
    linked_runs = (
        db.query(CrawlRun)
        .join(CrawlerScheduleRunCrawlRun, CrawlerScheduleRunCrawlRun.crawl_run_id == CrawlRun.id)
        .filter(CrawlerScheduleRunCrawlRun.schedule_run_id == schedule_run.id)
        .all()
    )
    if any(linked.status not in TERMINAL_RUN_STATUSES for linked in linked_runs):
        return
    schedule_run.finished_at = datetime.now()
    if all(linked.status == "completed" for linked in linked_runs):
        schedule_run.status = "completed"
    elif any(linked.status == "completed" for linked in linked_runs):
        schedule_run.status = "partial_failed"
    else:
        schedule_run.status = "failed"
    schedule = schedule_run.schedule
    if not schedule.auto_storage_enabled:
        schedule_run.storage_status = "disabled"
        db.commit()
        return
    movie_ids = [
        row[0]
        for row in (
            db.query(CrawlRunDetailTask.movie_id)
            .join(CrawlerScheduleRunCrawlRun, CrawlerScheduleRunCrawlRun.crawl_run_id == CrawlRunDetailTask.run_id)
            .filter(
                CrawlerScheduleRunCrawlRun.schedule_run_id == schedule_run.id,
                CrawlRunDetailTask.status == "saved",
                CrawlRunDetailTask.movie_id.isnot(None),
            )
            .distinct()
            .all()
        )
    ]
    if not movie_ids:
        schedule_run.storage_status = "skipped"
        schedule_run.result = {**(schedule_run.result or {}), "storage_message": "本次无可自动存储影片"}
        db.commit()
        return
    try:
        service = StorageTaskService(db, StorageConfigService(), runtime=StorageRuntimeState(get_redis()))
        storage_task = service.create_schedule_push(
            movie_ids=movie_ids,
            user_id=schedule_run.owner_id,
            storage_mode=schedule.storage_mode,
            selected_storage_location=schedule.selected_storage_location,
        )
        schedule_run.storage_task_id = storage_task.id
        schedule_run.storage_status = "created"
        db.commit()
    except Exception as exc:
        db.rollback()
        schedule_run = db.get(CrawlerScheduleRun, run.schedule_run_id)
        if schedule_run is not None:
            schedule_run.finished_at = datetime.now()
            schedule_run.storage_status = "failed"
            schedule_run.storage_error = str(exc)[:1000]
            db.commit()
