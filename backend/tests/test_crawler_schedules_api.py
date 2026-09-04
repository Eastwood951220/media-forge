from datetime import datetime

import pytest
from fastapi import HTTPException

from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleCreate, CrawlerScheduleUpdate
from backend.app.modules.crawler.schedules.service import CrawlerScheduleService, calculate_next_run_at


def seed_task(db_session, owner_id, name="Task", is_skip=False):
    task = CrawlTask(owner_id=owner_id, name=name, storage_location=name, is_skip=is_skip)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_create_schedule_requires_owned_tasks(db_session, test_user, other_user):
    other_task = seed_task(db_session, other_user.id, "Other")
    service = CrawlerScheduleService(db_session, scheduler=None)
    data = CrawlerScheduleCreate(
        name="Nightly",
        enabled=True,
        task_ids=[other_task.id],
        schedule_type="daily",
        time_of_day="03:30",
        weekdays=[],
        auto_storage_enabled=False,
        storage_mode="single",
        selected_storage_location=None,
    )

    with pytest.raises(HTTPException) as exc:
        service.create_schedule(data, test_user.id)

    assert exc.value.status_code == 400
    assert "任务不存在或无权限" in str(exc.value.detail)


def test_create_weekly_schedule_normalizes_weekdays(db_session, test_user):
    task = seed_task(db_session, test_user.id)
    service = CrawlerScheduleService(db_session, scheduler=None)
    data = CrawlerScheduleCreate(
        name="Weekday",
        enabled=True,
        task_ids=[task.id, task.id],
        schedule_type="weekly",
        time_of_day="04:15",
        weekdays=[4, 0, 4],
        auto_storage_enabled=True,
        storage_mode="single",
        selected_storage_location="",
    )

    schedule = service.create_schedule(data, test_user.id)

    assert schedule.weekdays == [0, 4]
    assert [t.id for t in schedule.tasks] == [task.id]
    assert schedule.selected_storage_location is None
    assert schedule.next_run_at is not None


def test_calculate_next_run_at_daily_moves_to_tomorrow_after_time():
    now = datetime(2026, 9, 4, 5, 0)
    next_run = calculate_next_run_at("daily", "03:30", [], now=now)
    assert next_run == datetime(2026, 9, 5, 3, 30)


def test_calculate_next_run_at_weekly_uses_selected_weekdays():
    now = datetime(2026, 9, 4, 5, 0)  # Friday
    next_run = calculate_next_run_at("weekly", "03:30", [0], now=now)
    assert next_run == datetime(2026, 9, 7, 3, 30)


@pytest.mark.parametrize("field", ["schedule_type", "time_of_day", "weekdays"])
def test_update_schedule_rejects_null_recurrence_field(db_session, test_user, field):
    task = seed_task(db_session, test_user.id)
    service = CrawlerScheduleService(db_session, scheduler=None)
    data = CrawlerScheduleCreate(
        name="Weekly",
        enabled=True,
        task_ids=[task.id],
        schedule_type="weekly",
        time_of_day="04:15",
        weekdays=[2],
        auto_storage_enabled=False,
        storage_mode="single",
        selected_storage_location=None,
    )
    schedule = service.create_schedule(data, test_user.id)

    with pytest.raises(HTTPException) as exc:
        service.update_schedule(schedule.id, CrawlerScheduleUpdate(**{field: None}), test_user.id)

    assert exc.value.status_code == 400
    assert "定时类型、执行时间和星期不能为空" in str(exc.value.detail)
