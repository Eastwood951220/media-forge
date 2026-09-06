from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.modules.backup.config import BackupConfigService
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
from backend.app.modules.backup.jobs import (
    backup_job_registry,
    backup_operation_lock,
)
from backend.app.modules.backup.paths import safe_backup_file_path
from backend.app.modules.backup.restorers import (
    restore_config,
    restore_movies,
    restore_tasks_and_schedules,
    stats_to_dict,
)
from backend.app.modules.backup.schemas import (
    BackupExportRequest,
    BackupFileInfo,
    BackupInspectResult,
    BackupRestoreRequest,
)
from shared.database.models.base import TZ

logger = logging.getLogger(__name__)


def backup_file_name(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return f"media-forge-backup-{moment.strftime('%Y%m%d-%H%M%S')}.mfbackup"


def prune_backup_files(backup_dir: Path, retention_count: int) -> int:
    """Delete the oldest backup files beyond ``retention_count``."""
    if retention_count < 1 or not backup_dir.is_dir():
        return 0
    files = sorted(backup_dir.glob("*.mfbackup"), key=lambda item: item.stat().st_mtime)
    removable = files[: max(0, len(files) - retention_count)]
    for path in removable:
        try:
            path.unlink()
        except OSError:
            logger.warning("Failed to remove old backup file %s", path)
    return len(removable)


class BackupService:
    """Orchestrate export, inspect, restore, and local backup file handling."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def export_to_file(
        self,
        request: BackupExportRequest,
        output_dir: Path,
        owner_id: uuid.UUID | None,
        job_id: uuid.UUID | None = None,
    ) -> Path:
        """Export the selected groups into a timestamped ``.mfbackup`` archive."""
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

    # -- In-process background jobs -------------------------------------

    def start_export_job(
        self,
        job_id: uuid.UUID,
        request: BackupExportRequest,
        owner_id: uuid.UUID,
    ) -> None:
        """Kick off a manual export in a daemon thread and return immediately."""
        thread = threading.Thread(
            target=self._run_export_job,
            args=(job_id, request, owner_id),
            name=f"backup-export-{job_id}",
            daemon=True,
        )
        thread.start()

    def _run_export_job(
        self,
        job_id: uuid.UUID,
        request: BackupExportRequest,
        owner_id: uuid.UUID,
    ) -> None:
        if not backup_operation_lock.acquire(blocking=False):
            backup_job_registry.mark_skipped(
                job_id, reason="backup operation already running"
            )
            return
        try:
            config = BackupConfigService().get_config()
            output_dir = Path(config.backup_dir)
            from shared.database.session import get_session_factory

            factory = get_session_factory()
            with factory() as db:
                path = BackupService(db).export_to_file(
                    request, output_dir, owner_id, job_id=job_id
                )
            backup_job_registry.mark_succeeded(
                job_id, result={"file_name": path.name}
            )
        except Exception as exc:
            logger.exception("Backup export job failed: %s", exc)
            backup_job_registry.mark_failed(job_id, error=str(exc))
        finally:
            backup_operation_lock.release()

    def start_restore_job(
        self,
        job_id: uuid.UUID,
        path: Path,
        request: BackupRestoreRequest,
        owner_id: uuid.UUID,
        delete_after: bool = False,
    ) -> None:
        """Kick off a restore in a daemon thread and return immediately."""
        thread = threading.Thread(
            target=self._run_restore_job,
            args=(job_id, path, request, owner_id, delete_after),
            name=f"backup-restore-{job_id}",
            daemon=True,
        )
        thread.start()

    def _run_restore_job(
        self,
        job_id: uuid.UUID,
        path: Path,
        request: BackupRestoreRequest,
        owner_id: uuid.UUID,
        delete_after: bool,
    ) -> None:
        if not backup_operation_lock.acquire(blocking=False):
            backup_job_registry.mark_skipped(
                job_id, reason="backup operation already running"
            )
            if delete_after:
                path.unlink(missing_ok=True)
            return
        try:
            from shared.database.session import get_session_factory

            factory = get_session_factory()
            with factory() as db:
                result = BackupService(db).restore_from_file(
                    path, request, owner_id, job_id=job_id
                )
            backup_job_registry.mark_succeeded(job_id, result=result)
        except Exception as exc:
            logger.exception("Backup restore job failed: %s", exc)
            backup_job_registry.mark_failed(job_id, error=str(exc))
        finally:
            if delete_after:
                path.unlink(missing_ok=True)
            backup_operation_lock.release()

    # -- Local backup files ---------------------------------------------

    def list_files(self) -> list[BackupFileInfo]:
        """List ``.mfbackup`` files in the configured backup directory."""
        config = BackupConfigService().get_config()
        backup_dir = Path(config.backup_dir)
        if not backup_dir.is_dir():
            return []
        infos: list[BackupFileInfo] = []
        files = sorted(backup_dir.glob("*.mfbackup"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in files:
            groups: list[str] = []
            include_sensitive = False
            try:
                inspected = inspect_backup_archive(path)
                groups = list(inspected.groups)
                include_sensitive = inspected.include_sensitive
            except ValueError:
                # Corrupt or foreign archives still show up for deletion.
                pass
            infos.append(
                BackupFileInfo(
                    name=path.name,
                    path=str(path),
                    size=path.stat().st_size,
                    created_at=datetime.fromtimestamp(path.stat().st_mtime, tz=TZ),
                    groups=groups,
                    include_sensitive=include_sensitive,
                )
            )
        return infos

    def delete_file(self, name: str) -> dict[str, bool]:
        """Delete one local backup file; ``ValueError`` rejects bad names."""
        config = BackupConfigService().get_config()
        backup_dir = Path(config.backup_dir)
        path = safe_backup_file_path(backup_dir, name)
        if not path.is_file():
            return {"deleted": False}
        path.unlink()
        return {"deleted": True}
