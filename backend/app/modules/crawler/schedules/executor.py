import uuid
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun, CrawlerScheduleRunCrawlRun
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.schedules.service import calculate_next_run_at
from shared.database.session import get_session_factory

TERMINAL_RUN_STATUSES = {"completed", "failed", "stopped"}


def _has_active_schedule_run(db: Session, schedule_id: uuid.UUID) -> bool:
    return (
        db.query(CrawlRun)
        .filter(CrawlRun.schedule_id == schedule_id, CrawlRun.status.in_(["queued", "running"]))
        .first()
        is not None
    )


def execute_schedule(
    schedule_id: uuid.UUID,
    *,
    db_factory: Callable[[], Session] | None = None,
    trigger_type: str = "scheduled",
) -> CrawlerScheduleRun | None:
    factory = db_factory or get_session_factory()
    db = factory()
    close_db = db_factory is None
    try:
        schedule = db.get(CrawlerSchedule, schedule_id)
        if schedule is None or not schedule.enabled:
            return None
        now = datetime.now()
        if _has_active_schedule_run(db, schedule.id):
            history = CrawlerScheduleRun(
                schedule_id=schedule.id,
                owner_id=schedule.owner_id,
                status="skipped",
                trigger_type=trigger_type,
                triggered_at=now,
                finished_at=now,
                result={"reason": "previous_run_active"},
                storage_status="disabled",
            )
            db.add(history)
            db.commit()
            db.refresh(history)
            return history

        history = CrawlerScheduleRun(
            schedule_id=schedule.id,
            owner_id=schedule.owner_id,
            status="running",
            trigger_type=trigger_type,
            triggered_at=now,
            result={"accepted": [], "skipped": [], "failed": []},
            storage_status="pending" if schedule.auto_storage_enabled else "disabled",
        )
        db.add(history)
        db.flush()
        service = CrawlerRunService(db, get_runtime_state())
        accepted = []
        skipped = []
        failed = []
        for task in schedule.tasks:
            if task.is_skip:
                skipped.append({"task_id": str(task.id), "reason": "禁用任务不能执行"})
                continue
            try:
                run = service.create_run(
                    task,
                    "incremental",
                    trigger_source="schedule",
                    schedule_id=schedule.id,
                    schedule_run_id=history.id,
                )
                db.add(CrawlerScheduleRunCrawlRun(schedule_run_id=history.id, crawl_run_id=run.id, task_id=task.id))
                accepted.append({"task_id": str(task.id), "run_id": str(run.id)})
            except Exception as exc:
                failed.append({"task_id": str(task.id), "reason": str(exc)})
        history.result = {"accepted": accepted, "skipped": skipped, "failed": failed}
        if not accepted:
            history.status = "failed" if failed else "skipped"
            history.finished_at = datetime.now()
        schedule.last_triggered_at = now
        schedule.next_run_at = calculate_next_run_at(schedule.schedule_type, schedule.time_of_day, schedule.weekdays)
        db.commit()
        db.refresh(history)
        return history
    finally:
        if close_db:
            db.close()
