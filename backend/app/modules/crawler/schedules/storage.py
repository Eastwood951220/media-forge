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
    _finalize_schedule_run(db, schedule_run)


def _finalize_schedule_run(db: Session, schedule_run: CrawlerScheduleRun) -> None:
    schedule = schedule_run.schedule
    if schedule is None:
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
    if not schedule.auto_storage_enabled:
        schedule_run.storage_status = "disabled"
        db.commit()
        return
    # Persist the finalized status before touching storage so a storage
    # failure cannot strand the schedule run in "running".
    db.commit()
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
        schedule_run = db.get(CrawlerScheduleRun, schedule_run.id)
        if schedule_run is not None:
            schedule_run.storage_status = "failed"
            schedule_run.storage_error = str(exc)[:1000]
            db.commit()


def finalize_stalled_schedule_runs(db: Session) -> int:
    """Finalize schedule runs stranded in ``running`` by a backend restart.

    ``cleanup_interrupted_runs`` marks interrupted crawler runs "stopped"
    directly (bypassing ``finalize_run``), so a schedule run whose linked
    crawler runs were stopped that way would otherwise keep ``status="running"``
    and ``storage_status="pending"`` forever, hiding a running trigger from
    history and silently skipping auto-storage. Called on startup after the
    crawler-run cleanup once every linked run is terminal.
    """
    stalled = db.query(CrawlerScheduleRun).filter(CrawlerScheduleRun.status == "running").all()
    finalized = 0
    for schedule_run in stalled:
        linked_runs = (
            db.query(CrawlRun)
            .join(CrawlerScheduleRunCrawlRun, CrawlerScheduleRunCrawlRun.crawl_run_id == CrawlRun.id)
            .filter(CrawlerScheduleRunCrawlRun.schedule_run_id == schedule_run.id)
            .all()
        )
        if not linked_runs:
            # Running rows without links are not persisted in practice — skip.
            continue
        if any(linked.status not in TERMINAL_RUN_STATUSES for linked in linked_runs):
            continue
        _finalize_schedule_run(db, schedule_run)
        finalized += 1
    db.commit()
    return finalized
