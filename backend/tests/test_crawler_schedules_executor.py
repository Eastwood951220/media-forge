from datetime import datetime, time
from unittest.mock import Mock

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import (
    CrawlerSchedule,
    CrawlerScheduleRun,
    CrawlerScheduleRunCrawlRun,
)
from backend.app.modules.crawler.schedules.executor import execute_schedule


class _RecordingRuntime:
    """Stub runtime that records enqueued run ids instead of touching Redis."""

    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue_run(self, run_id: str) -> None:
        self.enqueued.append(run_id)


def install_runtime_stubs(monkeypatch) -> _RecordingRuntime:
    """Replace Redis/worker side effects in the executor path with stubs."""
    runtime = _RecordingRuntime()
    monkeypatch.setattr(
        "backend.app.modules.crawler.schedules.executor.get_runtime_state",
        lambda: runtime,
    )
    monkeypatch.setattr(
        "backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started",
        lambda runtime: None,
    )
    return runtime


def seed_schedule(db_session, test_user, *, enabled=True, next_run_at=datetime(2026, 9, 5, 3, 30)):
    task = CrawlTask(owner_id=test_user.id, name="Task", storage_location="Task", is_skip=False)
    schedule = CrawlerSchedule(
        owner_id=test_user.id,
        name="Nightly",
        enabled=enabled,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=False,
        storage_mode="single",
        next_run_at=next_run_at,
    )
    schedule.tasks.append(task)
    db_session.add(schedule)
    db_session.commit()
    db_session.refresh(schedule)
    return schedule, task


def test_execute_schedule_creates_incremental_run(db_session, test_user, monkeypatch):
    schedule, task = seed_schedule(db_session, test_user)
    runtime = install_runtime_stubs(monkeypatch)

    schedule_run = execute_schedule(schedule.id, db_factory=lambda: db_session, trigger_type="manual")

    crawl_run = db_session.query(CrawlRun).filter(CrawlRun.task_id == task.id).one()
    assert schedule_run is not None
    assert schedule_run.trigger_type == "manual"
    assert crawl_run.crawl_mode == "incremental"
    assert crawl_run.trigger_source == "schedule"
    assert crawl_run.schedule_id == schedule.id
    assert crawl_run.schedule_run_id == schedule_run.id
    assert runtime.enqueued == [str(crawl_run.id)]


def test_execute_schedule_skips_when_existing_linked_run_active(db_session, test_user, monkeypatch):
    schedule, task = seed_schedule(db_session, test_user)
    first_history = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={},
        storage_status="disabled",
    )
    active_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=first_history.id,
    )
    db_session.add_all([first_history, active_run])
    db_session.flush()
    db_session.add(
        CrawlerScheduleRunCrawlRun(
            schedule_run_id=first_history.id,
            crawl_run_id=active_run.id,
            task_id=task.id,
        )
    )
    db_session.commit()
    install_runtime_stubs(monkeypatch)

    schedule_run = execute_schedule(schedule.id, db_factory=lambda: db_session)

    assert schedule_run.status == "skipped"
    assert schedule_run.result["reason"] == "previous_run_active"


def test_execute_schedule_ignores_unlinked_queued_run(db_session, test_user, monkeypatch):
    """An orphaned run without a link row must not wedge the schedule."""
    schedule, task = seed_schedule(db_session, test_user)
    stale_history = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="failed",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={"accepted": [], "skipped": [], "failed": []},
        storage_status="disabled",
    )
    orphan_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="queued",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=stale_history.id,
    )
    db_session.add_all([stale_history, orphan_run])
    db_session.commit()
    runtime = install_runtime_stubs(monkeypatch)

    schedule_run = execute_schedule(schedule.id, db_factory=lambda: db_session)

    assert schedule_run.status == "running"
    assert len(db_session.query(CrawlRun).filter(CrawlRun.task_id == task.id).all()) == 2
    assert schedule_run.result["accepted"]
    accepted_run_id = schedule_run.result["accepted"][0]["run_id"]
    assert runtime.enqueued == [accepted_run_id]


def test_execute_schedule_records_link_and_advances_schedule(db_session, test_user, monkeypatch):
    schedule, task = seed_schedule(db_session, test_user, next_run_at=datetime(2000, 1, 1, 3, 30))
    install_runtime_stubs(monkeypatch)

    schedule_run = execute_schedule(schedule.id, db_factory=lambda: db_session, trigger_type="manual")

    crawl_run = db_session.query(CrawlRun).filter(CrawlRun.task_id == task.id).one()
    assert schedule_run.status == "running"
    assert schedule_run.result["accepted"] == [{"task_id": str(task.id), "run_id": str(crawl_run.id)}]
    assert schedule_run.result["failed"] == []
    link = (
        db_session.query(CrawlerScheduleRunCrawlRun)
        .filter(CrawlerScheduleRunCrawlRun.schedule_run_id == schedule_run.id)
        .one()
    )
    assert link.crawl_run_id == crawl_run.id
    assert link.task_id == task.id
    db_session.refresh(schedule)
    assert schedule.last_triggered_at is not None
    assert schedule.next_run_at is not None
    assert schedule.next_run_at != datetime(2000, 1, 1, 3, 30)
    assert schedule.next_run_at.time() == time(3, 30)
