import uuid

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.models.crawler_schedule import CrawlerSchedule
from backend.app.modules.crawler.schedules.executor import execute_schedule
from shared.database.session import get_session_factory


def schedule_job_id(schedule_id: uuid.UUID | str) -> str:
    return f"crawler-schedule:{schedule_id}"


def build_trigger(schedule: CrawlerSchedule) -> CronTrigger:
    hour, minute = [int(part) for part in schedule.time_of_day.split(":", 1)]
    if schedule.schedule_type == "weekly":
        return CronTrigger(day_of_week=",".join(str(day) for day in schedule.weekdays), hour=hour, minute=minute)
    return CronTrigger(hour=hour, minute=minute)


class CrawlerScheduleScheduler:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def load_enabled_schedules(self) -> None:
        factory = get_session_factory()
        with factory() as db:
            for schedule in db.query(CrawlerSchedule).filter(CrawlerSchedule.enabled.is_(True)).all():
                self.upsert_schedule_job(schedule)

    def upsert_schedule_job(self, schedule: CrawlerSchedule) -> None:
        self.scheduler.add_job(
            execute_schedule,
            trigger=build_trigger(schedule),
            args=[schedule.id],
            id=schedule_job_id(schedule.id),
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def remove_schedule_job(self, schedule_id: uuid.UUID) -> None:
        job_id = schedule_job_id(schedule_id)
        if self.scheduler.get_job(job_id) is not None:
            self.scheduler.remove_job(job_id)


crawler_schedule_scheduler = CrawlerScheduleScheduler()
