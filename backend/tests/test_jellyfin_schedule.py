from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.modules.jellyfin.scheduler import JellyfinWatchScheduler, build_watch_sync_trigger


def test_weekly_sync_runs_only_on_configured_weekdays() -> None:
    trigger = build_watch_sync_trigger({
        "jellyfin_watch_sync_schedule_type": "weekly",
        "jellyfin_watch_sync_time_of_day": "03:15",
        "jellyfin_watch_sync_weekdays": [0, 3],
    })
    now = datetime(2026, 10, 30, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    next_fire = trigger.get_next_fire_time(None, now)
    assert next_fire.weekday() == 0
    assert (next_fire.hour, next_fire.minute) == (3, 15)


def test_scheduler_restores_enabled_job_and_removes_disabled_job(monkeypatch) -> None:
    config = {
        "jellyfin_watch_sync_enabled": True,
        "jellyfin_watch_sync_schedule_type": "daily",
        "jellyfin_watch_sync_time_of_day": "03:00",
        "jellyfin_watch_sync_weekdays": [],
    }
    monkeypatch.setattr(
        "backend.app.modules.scraping.config.ScrapingConfigService.get_raw_config",
        lambda _self: config,
    )
    scheduler = JellyfinWatchScheduler()
    try:
        scheduler.start()
        assert scheduler.scheduler.get_job(scheduler.JOB_ID) is not None
        config["jellyfin_watch_sync_enabled"] = False
        scheduler.configure()
        assert scheduler.scheduler.get_job(scheduler.JOB_ID) is None
    finally:
        scheduler.shutdown()
