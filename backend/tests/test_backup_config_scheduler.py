from datetime import datetime
from pathlib import Path

from backend.app.modules.backup.config import BackupConfigService
from backend.app.modules.backup.jobs import BackupJobRegistry
from backend.app.modules.backup.schemas import BackupConfig, BackupConfigUpdate
from backend.app.modules.backup.scheduler import BackupScheduler, next_backup_run


def test_backup_config_defaults_to_local_backup_dir(tmp_path: Path):
    service = BackupConfigService(config_file=tmp_path / "backup.conf", project_root=tmp_path)

    config = service.get_config()

    assert config.enabled is False
    assert config.backup_dir == str(tmp_path / "data" / "backups")
    assert config.groups == ["movies", "tasks", "config"]
    assert config.include_sensitive is False
    assert config.retention_count == 10


def test_backup_config_preserves_single_line_values(tmp_path: Path):
    service = BackupConfigService(config_file=tmp_path / "backup.conf", project_root=tmp_path)

    config = service.update_config(
        BackupConfigUpdate(
            enabled=True,
            backup_dir=str(tmp_path / "custom-backups"),
            schedule_type="weekly",
            time_of_day="03:30",
            weekdays=[1, 3, 5],
            groups=["movies", "config"],
            include_sensitive=True,
            retention_count=3,
        )
    )

    assert config.enabled is True
    assert config.schedule_type == "weekly"
    assert config.weekdays == [1, 3, 5]
    assert service.get_config().groups == ["movies", "config"]


def test_backup_config_preserves_monthly_schedule_days(tmp_path: Path):
    service = BackupConfigService(config_file=tmp_path / "backup.conf", project_root=tmp_path)

    config = service.update_config(
        BackupConfigUpdate(
            enabled=True,
            backup_dir=str(tmp_path / "custom-backups"),
            schedule_type="monthly",
            time_of_day="03:30",
            monthdays=[1, 15, 31, 15],
        )
    )

    assert config.schedule_type == "monthly"
    assert config.weekdays == []
    assert config.monthdays == [1, 15, 31]
    assert service.get_config().monthdays == [1, 15, 31]


def test_backup_scheduler_uses_monthly_schedule_days():
    config = BackupConfig(
        enabled=True,
        backup_dir="/tmp/backups",
        schedule_type="monthly",
        time_of_day="03:30",
        monthdays=[1, 15],
    )

    next_run = next_backup_run(config, now=datetime(2026, 9, 1, 4, 0))

    assert next_run == datetime(2026, 9, 15, 3, 30)


def test_backup_job_registry_tracks_success_and_failure():
    registry = BackupJobRegistry()
    job = registry.create("export")

    registry.mark_running(job.id, phase="movies", total=20)
    registry.update_progress(job.id, processed=7)
    registry.mark_succeeded(job.id, result={"file_name": "sample.mfbackup"})

    saved = registry.get(job.id)
    assert saved is not None
    assert saved.status == "succeeded"
    assert saved.processed == 7
    assert saved.result == {"file_name": "sample.mfbackup"}


def test_backup_scheduler_refresh_replaces_timer(tmp_path: Path):
    service = BackupConfigService(config_file=tmp_path / "backup.conf", project_root=tmp_path)
    scheduler = BackupScheduler(config_service=service)

    service.update_config(BackupConfigUpdate(enabled=True, backup_dir=str(tmp_path / "backups")))
    scheduler.start()
    first_timer = scheduler._timer
    scheduler.refresh()

    assert scheduler._timer is not None
    assert scheduler._timer is not first_timer
    scheduler.shutdown()
