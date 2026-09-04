import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun, CrawlerScheduleRunCrawlRun
from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.crawler.schedules.storage import finalize_stalled_schedule_runs, process_schedule_run_completion
from shared.database.models.content import Movie


def test_process_schedule_completion_creates_one_storage_task(db_session, test_user, monkeypatch):
    task = CrawlTask(owner_id=test_user.id, name="Task", storage_location="Task", is_skip=False)
    movie = Movie(code="ABC-001", source_name="Movie", source_task_ids=[])
    schedule = CrawlerSchedule(
        owner_id=test_user.id,
        name="Nightly",
        enabled=True,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=True,
        storage_mode="single",
        selected_storage_location=None,
    )
    schedule.tasks.append(task)
    db_session.add_all([task, movie, schedule])
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(movie)
    db_session.refresh(schedule)
    schedule_run = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={},
        storage_status="pending",
    )
    db_session.add(schedule_run)
    db_session.commit()
    db_session.refresh(schedule_run)
    crawl_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="completed",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=schedule_run.id,
    )
    db_session.add(crawl_run)
    db_session.commit()
    db_session.refresh(crawl_run)
    link = CrawlerScheduleRunCrawlRun(schedule_run_id=schedule_run.id, crawl_run_id=crawl_run.id, task_id=task.id)
    detail = CrawlRunDetailTask(
        run=crawl_run,
        task_name=task.name,
        source_url="https://example.test",
        source_name="Movie",
        status="saved",
        created_at=datetime.now(),
        movie_id=movie.id,
    )
    db_session.add_all([link, detail])
    db_session.commit()

    monkeypatch.setattr("backend.app.modules.storage.tasks.service.ensure_storage_worker_started", lambda *args, **kwargs: None)

    process_schedule_run_completion(db_session, crawl_run)
    db_session.refresh(schedule_run)

    storage_task = db_session.query(StorageMainTask).one()
    assert storage_task.source == "crawler_schedule"
    assert storage_task.total_count == 1
    assert schedule_run.status == "completed"
    assert schedule_run.storage_status == "created"
    assert schedule_run.storage_task_id == storage_task.id


def test_process_schedule_completion_finalizes_run_when_auto_storage_disabled(db_session, test_user):
    task = CrawlTask(owner_id=test_user.id, name="Task", storage_location="Task", is_skip=False)
    movie = Movie(code="ABC-002", source_name="Movie", source_task_ids=[])
    schedule = CrawlerSchedule(
        owner_id=test_user.id,
        name="NightlyDisabled",
        enabled=True,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=False,
        storage_mode="single",
        selected_storage_location=None,
    )
    schedule.tasks.append(task)
    db_session.add_all([task, movie, schedule])
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(movie)
    db_session.refresh(schedule)
    schedule_run = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={},
        storage_status="disabled",
    )
    db_session.add(schedule_run)
    db_session.commit()
    db_session.refresh(schedule_run)
    crawl_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="completed",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=schedule_run.id,
    )
    db_session.add(crawl_run)
    db_session.commit()
    db_session.refresh(crawl_run)
    link = CrawlerScheduleRunCrawlRun(schedule_run_id=schedule_run.id, crawl_run_id=crawl_run.id, task_id=task.id)
    detail = CrawlRunDetailTask(
        run=crawl_run,
        task_name=task.name,
        source_url="https://example.test",
        source_name="Movie",
        status="saved",
        created_at=datetime.now(),
        movie_id=movie.id,
    )
    db_session.add_all([link, detail])
    db_session.commit()

    process_schedule_run_completion(db_session, crawl_run)
    db_session.refresh(schedule_run)

    assert schedule_run.status == "completed"
    assert schedule_run.finished_at is not None
    assert schedule_run.storage_status == "disabled"
    assert db_session.query(StorageMainTask).count() == 0


def test_process_schedule_completion_storage_failure_keeps_run_finalized(db_session, test_user, monkeypatch):
    task = CrawlTask(owner_id=test_user.id, name="Task", storage_location="Task", is_skip=False)
    movie = Movie(code="ABC-003", source_name="Movie", source_task_ids=[])
    schedule = CrawlerSchedule(
        owner_id=test_user.id,
        name="NightlyFail",
        enabled=True,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=True,
        storage_mode="single",
        selected_storage_location=None,
    )
    schedule.tasks.append(task)
    db_session.add_all([task, movie, schedule])
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(movie)
    db_session.refresh(schedule)
    schedule_run = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={},
        storage_status="pending",
    )
    db_session.add(schedule_run)
    db_session.commit()
    db_session.refresh(schedule_run)
    crawl_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="completed",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=schedule_run.id,
    )
    db_session.add(crawl_run)
    db_session.commit()
    db_session.refresh(crawl_run)
    link = CrawlerScheduleRunCrawlRun(schedule_run_id=schedule_run.id, crawl_run_id=crawl_run.id, task_id=task.id)
    detail = CrawlRunDetailTask(
        run=crawl_run,
        task_name=task.name,
        source_url="https://example.test",
        source_name="Movie",
        status="saved",
        created_at=datetime.now(),
        movie_id=movie.id,
    )
    db_session.add_all([link, detail])
    db_session.commit()

    attempts: list[int] = []

    def raise_on_create(self, **kwargs):
        attempts.append(1)
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(
        "backend.app.modules.storage.tasks.service.StorageTaskService.create_schedule_push",
        raise_on_create,
    )

    process_schedule_run_completion(db_session, crawl_run)
    db_session.refresh(schedule_run)

    assert len(attempts) == 1
    assert schedule_run.status == "completed"
    assert schedule_run.finished_at is not None
    assert schedule_run.storage_status == "failed"
    assert schedule_run.storage_error == "simulated storage failure"


def seed_schedule_run_row(db_session, owner_id, *, name, auto_storage_enabled, status, storage_status, task_name="Task"):
    """Shared seeding for schedule-run finalization tests (mirrors the tests above)."""
    task = CrawlTask(owner_id=owner_id, name=task_name, storage_location=task_name, is_skip=False)
    schedule = CrawlerSchedule(
        owner_id=owner_id,
        name=name,
        enabled=True,
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=auto_storage_enabled,
        storage_mode="single",
        selected_storage_location=None,
    )
    schedule.tasks.append(task)
    db_session.add_all([task, schedule])
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(schedule)
    schedule_run = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=owner_id,
        status=status,
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={},
        storage_status=storage_status,
    )
    db_session.add(schedule_run)
    db_session.commit()
    db_session.refresh(schedule_run)
    return task, schedule, schedule_run


def test_finalize_stalled_schedule_runs_finalizes_stopped_run_and_creates_storage(db_session, test_user, monkeypatch):
    movie = Movie(code="ABC-011", source_name="Movie", source_task_ids=[])
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    task, schedule, schedule_run = seed_schedule_run_row(
        db_session,
        test_user.id,
        name="NightlyStalled",
        auto_storage_enabled=True,
        status="running",
        storage_status="pending",
    )
    crawl_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="stopped",
        crawl_mode="incremental",
        schedule_id=schedule.id,
        schedule_run_id=schedule_run.id,
        finished_at=datetime.now(),
        error="服务重启，任务已停止，需手动重启",
    )
    db_session.add(crawl_run)
    db_session.commit()
    db_session.refresh(crawl_run)
    link = CrawlerScheduleRunCrawlRun(schedule_run_id=schedule_run.id, crawl_run_id=crawl_run.id, task_id=task.id)
    detail = CrawlRunDetailTask(
        run=crawl_run,
        task_name=task.name,
        source_url="https://example.test",
        source_name="Movie",
        status="saved",
        created_at=datetime.now(),
        movie_id=movie.id,
    )
    db_session.add_all([link, detail])
    db_session.commit()

    monkeypatch.setattr("backend.app.modules.storage.tasks.service.ensure_storage_worker_started", lambda *args, **kwargs: None)

    count = finalize_stalled_schedule_runs(db_session)
    db_session.refresh(schedule_run)

    assert count == 1
    assert schedule_run.status == "failed"
    assert schedule_run.finished_at is not None
    assert schedule_run.storage_status == "created"
    assert schedule_run.storage_task_id is not None
    storage_task = db_session.query(StorageMainTask).one()
    assert storage_task.source == "crawler_schedule"
    assert schedule_run.storage_task_id == storage_task.id


def test_finalize_stalled_schedule_runs_skips_linkless_and_marks_partial_failed(db_session, test_user):
    _, _, partial_run = seed_schedule_run_row(
        db_session,
        test_user.id,
        name="NightlyPartial",
        auto_storage_enabled=False,
        status="running",
        storage_status="disabled",
    )
    _, _, linkless_run = seed_schedule_run_row(
        db_session,
        test_user.id,
        name="NightlyLinkless",
        auto_storage_enabled=False,
        status="running",
        storage_status="disabled",
        task_name="TaskB",
    )
    completed_run = CrawlRun(
        task_id=None,
        task_name="Task",
        status="completed",
        crawl_mode="incremental",
        schedule_id=partial_run.schedule_id,
        schedule_run_id=partial_run.id,
        finished_at=datetime.now(),
    )
    stopped_run = CrawlRun(
        task_id=None,
        task_name="Task",
        status="stopped",
        crawl_mode="incremental",
        schedule_id=partial_run.schedule_id,
        schedule_run_id=partial_run.id,
        finished_at=datetime.now(),
    )
    db_session.add_all([completed_run, stopped_run])
    db_session.commit()
    db_session.refresh(completed_run)
    db_session.refresh(stopped_run)
    links = [
        CrawlerScheduleRunCrawlRun(schedule_run_id=partial_run.id, crawl_run_id=completed_run.id, task_id=None),
        CrawlerScheduleRunCrawlRun(schedule_run_id=partial_run.id, crawl_run_id=stopped_run.id, task_id=None),
    ]
    db_session.add_all(links)
    db_session.commit()

    count = finalize_stalled_schedule_runs(db_session)
    db_session.refresh(partial_run)
    db_session.refresh(linkless_run)

    assert count == 1
    assert partial_run.status == "partial_failed"
    assert partial_run.finished_at is not None
    assert partial_run.storage_status == "disabled"
    assert linkless_run.status == "running"
    assert linkless_run.finished_at is None
    assert linkless_run.storage_status == "disabled"
    assert db_session.query(StorageMainTask).count() == 0
