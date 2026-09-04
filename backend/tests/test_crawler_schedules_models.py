import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_schedule import (
    CrawlerSchedule,
    CrawlerScheduleRun,
    CrawlerScheduleRunCrawlRun,
)


def test_schedule_model_links_tasks_runs_and_saved_movies(db_session, test_user):
    task = CrawlTask(
        owner_id=test_user.id,
        name="JavDB",
        storage_location="JavDB",
        is_skip=False,
    )
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
    db_session.add(schedule)
    db_session.commit()
    db_session.refresh(schedule)

    schedule_run = CrawlerScheduleRun(
        schedule_id=schedule.id,
        owner_id=test_user.id,
        status="running",
        trigger_type="scheduled",
        triggered_at=datetime.now(),
        result={"accepted": []},
        storage_status="pending",
    )
    db_session.add(schedule_run)
    db_session.commit()
    db_session.refresh(schedule_run)

    crawl_run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="queued",
        crawl_mode="incremental",
        trigger_source="schedule",
        schedule_id=schedule.id,
        schedule_run_id=schedule_run.id,
    )
    link = CrawlerScheduleRunCrawlRun(schedule_run=schedule_run, crawl_run=crawl_run, task_id=task.id)
    detail = CrawlRunDetailTask(
        run=crawl_run,
        task_name=task.name,
        source_url="https://example.test/movie",
        source_name="Example",
        status="saved",
        created_at=datetime.now(),
        movie_id=uuid.uuid4(),
    )
    db_session.add_all([crawl_run, link, detail])
    db_session.commit()
    db_session.refresh(schedule_run)

    assert schedule.tasks[0].id == task.id
    assert schedule_run.crawl_run_links[0].crawl_run_id == crawl_run.id
    assert crawl_run.schedule_run_id == schedule_run.id
    assert crawl_run.detail_tasks[0].movie_id is not None
