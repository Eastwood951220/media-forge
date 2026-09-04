from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleRun
from backend.app.modules.crawler.schedules.schemas import CrawlerScheduleRead, CrawlerScheduleTaskSummary


def serialize_schedule(schedule: CrawlerSchedule) -> CrawlerScheduleRead:
    latest = schedule.runs[0] if schedule.runs else None
    return CrawlerScheduleRead(
        id=schedule.id,
        name=schedule.name,
        enabled=schedule.enabled,
        schedule_type=schedule.schedule_type,
        time_of_day=schedule.time_of_day,
        weekdays=schedule.weekdays or [],
        auto_storage_enabled=schedule.auto_storage_enabled,
        storage_mode=schedule.storage_mode,
        selected_storage_location=schedule.selected_storage_location,
        task_count=len(schedule.tasks),
        tasks=[
            CrawlerScheduleTaskSummary(id=task.id, name=task.name, is_skip=task.is_skip)
            for task in schedule.tasks
        ],
        last_triggered_at=schedule.last_triggered_at,
        next_run_at=schedule.next_run_at,
        latest_run_status=latest.status if latest else None,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )
