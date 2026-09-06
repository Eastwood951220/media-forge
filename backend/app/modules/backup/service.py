from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.modules.backup.format import (
    inspect_backup_archive,
    write_manifest,
)
from backend.app.modules.backup.groups import (
    BACKUP_FORMAT_NAME,
    BACKUP_FORMAT_VERSION,
)
from backend.app.modules.backup.exporters import (
    MOVIE_EXPORTS,
    TASK_EXPORTS,
    export_config_files,
    export_db_group,
)
from backend.app.modules.backup.restorers import (
    restore_config,
    restore_movies,
    restore_tasks_and_schedules,
    stats_to_dict,
)
from backend.app.modules.backup.schemas import (
    BackupExportRequest,
    BackupInspectResult,
    BackupRestoreRequest,
)
from shared.database.models.base import TZ


def backup_file_name(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return f"media-forge-backup-{moment.strftime('%Y%m%d-%H%M%S')}.mfbackup"


class BackupService:
    """Orchestrate export, inspect, restore, and local backup file handling."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def export_to_file(
        self,
        request: BackupExportRequest,
        output_dir: Path,
        owner_id: uuid.UUID,
        job_id: uuid.UUID | None = None,
    ) -> Path:
        """Export the selected groups into a timestamped ``.mfbackup`` archive."""
        from backend.app.modules.backup.jobs import backup_job_registry

        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / backup_file_name()
        groups = list(dict.fromkeys(request.groups))

        def report_progress(arcname: str, processed: int, total: int | None) -> None:
            if job_id is None:
                return
            if total is not None:
                backup_job_registry.mark_running(job_id, phase=arcname, total=total)
            else:
                backup_job_registry.update_progress(job_id, phase=arcname, processed=processed)

        with ZipFile(path, "w", compression=ZIP_DEFLATED) as zip_file:
            row_counts: dict[str, int] = {}
            if "movies" in groups:
                if job_id is not None:
                    backup_job_registry.mark_running(job_id, phase="movies")
                row_counts.update(
                    export_db_group(
                        self.db,
                        zip_file,
                        MOVIE_EXPORTS,
                        owner_id,
                        on_progress=report_progress if job_id is not None else None,
                    )
                )
            if "tasks" in groups:
                if job_id is not None:
                    backup_job_registry.mark_running(job_id, phase="tasks")
                row_counts.update(
                    export_db_group(
                        self.db,
                        zip_file,
                        TASK_EXPORTS,
                        owner_id,
                        on_progress=report_progress if job_id is not None else None,
                    )
                )
            if "config" in groups:
                if job_id is not None:
                    backup_job_registry.mark_running(job_id, phase="config")
                export_config_files(zip_file, include_sensitive=request.include_sensitive)

            write_manifest(
                zip_file,
                {
                    "format": BACKUP_FORMAT_NAME,
                    "version": BACKUP_FORMAT_VERSION,
                    "app_version": get_settings().app_version,
                    "created_at": datetime.now(TZ).isoformat(),
                    "groups": groups,
                    "include_sensitive": request.include_sensitive,
                    "row_counts": row_counts,
                    "source_timezone": str(TZ),
                },
            )
        return path

    def inspect_file(self, path: Path) -> BackupInspectResult:
        """Preflight-inspect an archive without writing anything to the database."""
        return inspect_backup_archive(path)

    def restore_from_file(
        self,
        path: Path,
        request: BackupRestoreRequest,
        owner_id: uuid.UUID,
        job_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Restore the selected groups from ``path`` in the requested mode."""
        from backend.app.modules.backup.jobs import backup_job_registry

        inspected = inspect_backup_archive(path)
        result: dict[str, Any] = {}
        partial = False
        with ZipFile(path) as zip_file:
            groups = list(dict.fromkeys(request.groups))
            if "movies" in groups:
                if job_id is not None:
                    backup_job_registry.mark_running(job_id, phase="movies")
                stats = restore_movies(self.db, zip_file, request.mode)
                result["movies"] = stats_to_dict(stats)
                partial = partial or bool(stats.errors)
                if job_id is not None:
                    backup_job_registry.update_progress(job_id, phase="movies", processed=stats.created + stats.updated)
            if "tasks" in groups:
                if job_id is not None:
                    backup_job_registry.mark_running(job_id, phase="tasks")
                stats = restore_tasks_and_schedules(self.db, zip_file, request.mode, owner_id)
                result["tasks"] = stats_to_dict(stats)
                partial = partial or bool(stats.errors)
                if job_id is not None:
                    backup_job_registry.update_progress(job_id, phase="tasks", processed=stats.created + stats.updated)
            if "config" in groups:
                if job_id is not None:
                    backup_job_registry.mark_running(job_id, phase="config")
                stats = restore_config(zip_file, include_sensitive_in_archive=inspected.include_sensitive)
                result["config"] = stats_to_dict(stats)
                partial = partial or bool(stats.errors)
        if partial:
            result["partial"] = True
        return result
