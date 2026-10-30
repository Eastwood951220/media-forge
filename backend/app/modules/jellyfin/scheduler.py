from __future__ import annotations

import logging
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
TIMEZONE = ZoneInfo("Asia/Shanghai")


def build_watch_sync_trigger(config: Mapping[str, Any]) -> CronTrigger:
    hour, minute = [int(part) for part in config["jellyfin_watch_sync_time_of_day"].split(":", 1)]
    kwargs: dict[str, Any] = {"hour": hour, "minute": minute, "timezone": TIMEZONE}
    if config["jellyfin_watch_sync_schedule_type"] == "weekly":
        kwargs["day_of_week"] = ",".join(str(day) for day in config["jellyfin_watch_sync_weekdays"])
    return CronTrigger(**kwargs)


def run_scheduled_watch_sync() -> None:
    from backend.app.modules.jellyfin.client import JellyfinClient
    from backend.app.modules.jellyfin.sync import config_fingerprint, sync_jellyfin_watch_state
    from backend.app.modules.scraping.config import ScrapingConfigService
    from shared.database.session import get_session_factory

    config = ScrapingConfigService().get_raw_config()
    if not config["jellyfin_watch_sync_enabled"]:
        return
    try:
        with get_session_factory()() as db:
            sync_jellyfin_watch_state(
                db,
                JellyfinClient(config["jellyfin_base_url"], config["jellyfin_api_key"]),
                fingerprint=config_fingerprint(config),
            )
    except Exception:
        logger.exception("Scheduled Jellyfin watch synchronization failed")


class JellyfinWatchScheduler:
    JOB_ID = "jellyfin-watch-sync"

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone=TIMEZONE)

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self.configure()

    def configure(self) -> None:
        from backend.app.modules.scraping.config import ScrapingConfigService

        if not self.scheduler.running:
            return
        config = ScrapingConfigService().get_raw_config()
        if self.scheduler.get_job(self.JOB_ID):
            self.scheduler.remove_job(self.JOB_ID)
        if config["jellyfin_watch_sync_enabled"]:
            self.scheduler.add_job(
                run_scheduled_watch_sync,
                build_watch_sync_trigger(config),
                id=self.JOB_ID,
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)


jellyfin_watch_scheduler = JellyfinWatchScheduler()
