from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.app.modules.backup.schemas import BackupJob, BackupOperation

backup_operation_lock = threading.Lock()


class BackupJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, BackupJob] = {}
        self._lock = threading.Lock()

    def create(self, operation: BackupOperation) -> BackupJob:
        now = datetime.now(timezone.utc)
        job = BackupJob(id=uuid.uuid4(), operation=operation, created_at=now, updated_at=now)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: uuid.UUID) -> BackupJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def mark_running(self, job_id: uuid.UUID, *, phase: str, total: int | None = None) -> None:
        self._mutate(job_id, status="running", phase=phase, total=total)

    def update_progress(self, job_id: uuid.UUID, *, processed: int, phase: str | None = None) -> None:
        values: dict[str, Any] = {"processed": processed}
        if phase is not None:
            values["phase"] = phase
        self._mutate(job_id, **values)

    def mark_succeeded(self, job_id: uuid.UUID, *, result: dict[str, Any]) -> None:
        self._mutate(job_id, status="succeeded", phase="done", result=result)

    def mark_failed(self, job_id: uuid.UUID, *, error: str) -> None:
        self._mutate(job_id, status="failed", error=error)

    def mark_skipped(self, job_id: uuid.UUID, *, reason: str) -> None:
        self._mutate(job_id, status="skipped", phase="skipped", error=reason)

    def _mutate(self, job_id: uuid.UUID, **values: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            updated = job.model_copy(update={**values, "updated_at": datetime.now(timezone.utc)})
            self._jobs[job_id] = updated


backup_job_registry = BackupJobRegistry()
