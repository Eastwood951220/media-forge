from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.modules.backup.config import BackupConfigService
from backend.app.modules.backup.jobs import backup_job_registry
from backend.app.modules.backup.schemas import BackupConfig, BackupExportRequest

logger = logging.getLogger(__name__)


def next_backup_run(config: BackupConfig, now: datetime | None = None) -> datetime | None:
    """Compute the next enabled run time or ``None`` when no run can be scheduled."""
    if not config.enabled:
        return None
    moment = now or datetime.now()
    hour, minute = [int(part) for part in config.time_of_day.split(":", 1)]
    if config.schedule_type == "daily":
        candidate = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate if candidate > moment else candidate + timedelta(days=1)
    # Weekly
    weekdays = sorted(set(config.weekdays))
    if not weekdays:
        return None
    for offset in range(1, 9):
        candidate_day = moment + timedelta(days=offset)
        if candidate_day.weekday() not in weekdays:
            continue
        candidate = candidate_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate
    return None


class BackupScheduler:
    """In-process automatic backup scheduler based on ``threading.Timer``."""

    def __init__(self, config_service: BackupConfigService | None = None) -> None:
        self.config_service = config_service or BackupConfigService()
        self._timer: threading.Timer | None = None
        self._running = False
        self._mutex = threading.Lock()

    def start(self) -> None:
        with self._mutex:
            if self._running:
                return
            self._running = True
        self._schedule()

    def shutdown(self) -> None:
        with self._mutex:
            self._running = False
        self._cancel_timer()

    def refresh(self) -> None:
        """Cancel the pending timer and schedule again from current settings."""
        self._cancel_timer()
        with self._mutex:
            if not self._running:
                return
        self._schedule()

    def _schedule(self) -> None:
        with self._mutex:
            if not self._running:
                return
            config = self.config_service.get_config()
            run_at = next_backup_run(config)
            if run_at is None:
                self._timer = None
                return
            delay = max(1.0, (run_at - datetime.now()).total_seconds())
            timer = threading.Timer(delay, self._fire)
            timer.daemon = True
            self._timer = timer
            logger.info("Automatic backup scheduled for %s", run_at.isoformat())
            timer.start()

    def _cancel_timer(self) -> None:
        with self._mutex:
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()

    def _fire(self) -> None:
        # Reschedule first so a slow backup never stalls the schedule.
        with self._mutex:
            self._timer = None
            running = self._running
        if running:
            self._schedule()
        config = self.config_service.get_config()
        if not config.enabled:
            return
        job = backup_job_registry.create("auto_export")
        worker = threading.Thread(
            target=self._run_auto_backup,
            args=(config, job.id),
            name=f"backup-auto-{job.id}",
            daemon=True,
        )
        worker.start()

    def _run_auto_backup(self, config: BackupConfig, job_id: uuid.UUID) -> None:
        from backend.app.modules.backup.jobs import backup_operation_lock
        from backend.app.modules.backup.service import (
            BackupService,
            prune_backup_files,
        )
        from shared.database.session import get_session_factory

        if not backup_operation_lock.acquire(blocking=False):
            backup_job_registry.mark_skipped(
                job_id, reason="backup operation already running"
            )
            logger.warning("Automatic backup skipped: backup operation already running")
            return
        try:
            factory = get_session_factory()
            with factory() as db:
                request = BackupExportRequest(
                    groups=list(config.groups),
                    include_sensitive=config.include_sensitive,
                )
                path = BackupService(db).export_to_file(
                    request,
                    output_dir=Path(config.backup_dir),
                    owner_id=None,  # automatic backups cover every user's data
                    job_id=job_id,
                )
            removed = prune_backup_files(Path(config.backup_dir), config.retention_count)
            result: dict[str, Any] = {"file_name": path.name}
            if removed:
                result["removed"] = removed
            backup_job_registry.mark_succeeded(job_id, result=result)
            logger.info(
                "Automatic backup finished: %s (retention removed %d files)",
                path.name,
                removed,
            )
        except Exception as exc:
            backup_job_registry.mark_failed(job_id, error=str(exc))
            logger.exception("Automatic backup failed: %s", exc)
        finally:
            backup_operation_lock.release()


backup_scheduler = BackupScheduler()
