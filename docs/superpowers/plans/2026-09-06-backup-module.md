# Backup Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent backup module that exports, inspects, restores, and automatically schedules reusable Media Forge backup archives.

**Architecture:** The backend owns `.mfbackup` archive creation, stream-style JSONL processing, batched restore, automatic scheduling, local backup file management, and in-process job status. The frontend adds a `/content/backup` page under Content Management that calls `/api/backup` and never parses large backup files in the browser.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic, ZIP archives, JSON Lines, React 19, Vite, TypeScript, Ant Design 6, TanStack Query, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-06-backup-module-design.md`

## Global Constraints

- Do not create or use a Git worktree in this repository.
- Backend backup code lives under `backend/app/modules/backup/`.
- Backend API prefix is `/api/backup`.
- Frontend API code lives under `frontend/src/api/backup/`.
- Frontend page code lives under `frontend/src/pages/content/backup/`.
- Frontend route is `/content/backup`.
- Sidebar entry is `内容管理 / 数据备份`.
- Backup files use `.mfbackup` ZIP archives with `manifest.json` plus JSONL files.
- Movie export and restore must support tens or hundreds of thousands of records without a single giant JSON document.
- `movies.code` must remain unique during restore.
- Merge restore is the default; overwrite restore is also supported.
- Export and restore groups are selectable.
- Sensitive configuration export is opt-in and disabled by default.
- Automatic backups save locally, defaulting to `data/backups/`, with a configurable directory.
- Do not restore historical execution records: `crawl_runs`, `crawl_run_detail_tasks`, `crawler_schedule_runs`, `crawler_schedule_run_crawl_runs`, `storage_main_tasks`, or `storage_sub_tasks`.
- Do not back up users, auth tokens, active runtime state, Redis state, logs, or generated frontend/static build output.

---

## File Structure

Create backend module files:

- `backend/app/modules/backup/__init__.py`: package marker.
- `backend/app/modules/backup/schemas.py`: Pydantic request and response models.
- `backend/app/modules/backup/groups.py`: group constants, file names, and table mappings.
- `backend/app/modules/backup/paths.py`: backup directory resolution and path traversal protection.
- `backend/app/modules/backup/config.py`: read and write `data/configs/backup.conf`.
- `backend/app/modules/backup/jobs.py`: in-process job registry and backup operation lock.
- `backend/app/modules/backup/format.py`: `.mfbackup` ZIP, manifest, JSONL, checksum, and inspection helpers.
- `backend/app/modules/backup/exporters.py`: database and config export writers.
- `backend/app/modules/backup/restorers.py`: merge and overwrite restore logic.
- `backend/app/modules/backup/scheduler.py`: automatic backup scheduler.
- `backend/app/modules/backup/service.py`: orchestration for export, inspect, restore, file list, delete, and config.
- `backend/app/modules/backup/router.py`: `/api/backup` endpoints.

Modify backend files:

- `backend/app/main.py`: include backup router and start/shutdown backup scheduler in lifespan.
- `backend/tests/conftest.py`: patch backup scheduler startup/shutdown in API tests.

Create backend tests:

- `backend/tests/test_backup_format.py`
- `backend/tests/test_backup_export_restore.py`
- `backend/tests/test_backup_config_scheduler.py`
- `backend/tests/test_backup_api.py`

Create frontend files:

- `frontend/src/api/backup/types.ts`: API types.
- `frontend/src/api/backup/index.ts`: API functions.
- `frontend/src/pages/content/backup/BackupPage.tsx`: page container.
- `frontend/src/pages/content/backup/BackupPage.module.less`: page styles.
- `frontend/tests/backup-api.test.ts`
- `frontend/tests/backup-page.ui.test.tsx`

Modify frontend files:

- `frontend/src/api/queryKeys.ts`: backup query keys.
- `frontend/src/api/queryInvalidation.ts`: invalidation helper after restore.
- `frontend/src/routes/index.tsx`: add `/content/backup`.
- `frontend/src/routes/tags.ts`: add tag metadata.
- `frontend/src/layout/Sidebar/index.tsx`: add `数据备份` menu item and selected key handling.
- `frontend/README.md`: document the backup page and API module if the README route/module list is present.

---

### Task 1: Backend Backup Contracts, Config, And Job Registry

**Files:**
- Create: `backend/app/modules/backup/__init__.py`
- Create: `backend/app/modules/backup/groups.py`
- Create: `backend/app/modules/backup/schemas.py`
- Create: `backend/app/modules/backup/config.py`
- Create: `backend/app/modules/backup/jobs.py`
- Test: `backend/tests/test_backup_config_scheduler.py`

**Interfaces:**
- Produces: `BackupGroup = Literal["movies", "tasks", "config"]`
- Produces: `DEFAULT_BACKUP_GROUPS: tuple[str, ...]`
- Produces: `BackupConfigService.get_config() -> BackupConfig`
- Produces: `BackupConfigService.update_config(payload: BackupConfigUpdate) -> BackupConfig`
- Produces: `BackupJobRegistry.create(operation: BackupOperation) -> BackupJob`
- Produces: `BackupJobRegistry.get(job_id: uuid.UUID) -> BackupJob | None`
- Produces: `backup_operation_lock: threading.Lock`

- [ ] **Step 1: Write failing tests for config defaults and job state**

Add this test structure to `backend/tests/test_backup_config_scheduler.py`:

```python
from pathlib import Path

from backend.app.modules.backup.config import BackupConfigService
from backend.app.modules.backup.jobs import BackupJobRegistry
from backend.app.modules.backup.schemas import BackupConfigUpdate


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_backup_config_scheduler.py -v
```

Expected: FAIL with import errors for `backend.app.modules.backup`.

- [ ] **Step 3: Create schema, group, config, and job files**

Implement these concrete interfaces:

```python
# backend/app/modules/backup/groups.py
from typing import Literal

BackupGroup = Literal["movies", "tasks", "config"]
DEFAULT_BACKUP_GROUPS: tuple[BackupGroup, ...] = ("movies", "tasks", "config")
BACKUP_FORMAT_NAME = "media-forge-backup"
BACKUP_FORMAT_VERSION = 1
```

```python
# backend/app/modules/backup/schemas.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.app.modules.backup.groups import DEFAULT_BACKUP_GROUPS, BackupGroup

BackupOperation = Literal["export", "inspect", "restore", "auto_export", "delete"]
BackupJobStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
RestoreMode = Literal["merge", "overwrite"]
ScheduleType = Literal["daily", "weekly"]


class BackupConfig(BaseModel):
    enabled: bool = False
    backup_dir: str
    schedule_type: ScheduleType = "daily"
    time_of_day: str = "03:30"
    weekdays: list[int] = Field(default_factory=list)
    groups: list[BackupGroup] = Field(default_factory=lambda: list(DEFAULT_BACKUP_GROUPS))
    include_sensitive: bool = False
    retention_count: int = Field(default=10, ge=1, le=365)

    @field_validator("time_of_day")
    @classmethod
    def validate_time_of_day(cls, value: str) -> str:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("time_of_day must be HH:MM")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain values from 0 to 6")
        return sorted(set(value))


class BackupConfigUpdate(BaseModel):
    enabled: bool | None = None
    backup_dir: str | None = None
    schedule_type: ScheduleType | None = None
    time_of_day: str | None = None
    weekdays: list[int] | None = None
    groups: list[BackupGroup] | None = None
    include_sensitive: bool | None = None
    retention_count: int | None = Field(default=None, ge=1, le=365)


class BackupJob(BaseModel):
    id: UUID
    operation: BackupOperation
    status: BackupJobStatus = "pending"
    phase: str = "pending"
    processed: int = 0
    total: int | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class BackupFileInfo(BaseModel):
    name: str
    path: str
    size: int
    created_at: datetime
    groups: list[BackupGroup] = Field(default_factory=list)
    include_sensitive: bool = False


class BackupExportRequest(BaseModel):
    groups: list[BackupGroup] = Field(default_factory=lambda: list(DEFAULT_BACKUP_GROUPS))
    include_sensitive: bool = False


class BackupInspectResult(BaseModel):
    manifest: dict[str, Any]
    groups: list[BackupGroup]
    row_counts: dict[str, int]
    include_sensitive: bool


class BackupRestoreRequest(BaseModel):
    mode: RestoreMode = "merge"
    groups: list[BackupGroup] = Field(default_factory=lambda: list(DEFAULT_BACKUP_GROUPS))


class BackupJobResponse(BaseModel):
    job_id: UUID
```

```python
# backend/app/modules/backup/jobs.py
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
```

For `BackupConfigService`, write dotenv-style values to `data/configs/backup.conf` and use `RuntimeConfigPaths.from_env()` or `PROJECT_ROOT` only inside the default constructor so tests can pass `tmp_path`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest backend/tests/test_backup_config_scheduler.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/backup/__init__.py backend/app/modules/backup/groups.py backend/app/modules/backup/schemas.py backend/app/modules/backup/config.py backend/app/modules/backup/jobs.py backend/tests/test_backup_config_scheduler.py
git diff --cached --name-only
git commit -m "feat: add backup module contracts"
```

---

### Task 2: Backup Archive Format And Path Safety

**Files:**
- Create: `backend/app/modules/backup/paths.py`
- Create: `backend/app/modules/backup/format.py`
- Test: `backend/tests/test_backup_format.py`

**Interfaces:**
- Consumes: `BACKUP_FORMAT_NAME`, `BACKUP_FORMAT_VERSION`, `BackupGroup`
- Produces: `safe_backup_file_path(backup_dir: Path, name: str) -> Path`
- Produces: `write_jsonl(zip_file: ZipFile, arcname: str, rows: Iterable[dict[str, Any]]) -> int`
- Produces: `read_jsonl(zip_file: ZipFile, arcname: str) -> Iterator[dict[str, Any]]`
- Produces: `write_manifest(zip_file: ZipFile, manifest: dict[str, Any]) -> None`
- Produces: `inspect_backup_archive(path: Path) -> BackupInspectResult`

- [ ] **Step 1: Write failing archive tests**

Add these tests to `backend/tests/test_backup_format.py`:

```python
from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.app.modules.backup.format import (
    inspect_backup_archive,
    read_jsonl,
    write_jsonl,
    write_manifest,
)
from backend.app.modules.backup.paths import safe_backup_file_path


def test_jsonl_archive_round_trip(tmp_path: Path):
    archive = tmp_path / "sample.mfbackup"
    with ZipFile(archive, "w") as zip_file:
        write_manifest(zip_file, {
            "format": "media-forge-backup",
            "version": 1,
            "groups": ["movies"],
            "include_sensitive": False,
            "row_counts": {"data/movies.jsonl": 2},
        })
        count = write_jsonl(zip_file, "data/movies.jsonl", [{"id": "1"}, {"id": "2"}])

    assert count == 2
    with ZipFile(archive) as zip_file:
        assert list(read_jsonl(zip_file, "data/movies.jsonl")) == [{"id": "1"}, {"id": "2"}]

    inspected = inspect_backup_archive(archive)
    assert inspected.groups == ["movies"]
    assert inspected.row_counts == {"data/movies.jsonl": 2}


def test_safe_backup_file_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid backup file name"):
        safe_backup_file_path(tmp_path, "../escape.mfbackup")

    with pytest.raises(ValueError, match="Invalid backup file name"):
        safe_backup_file_path(tmp_path, "notes.txt")

    assert safe_backup_file_path(tmp_path, "ok.mfbackup") == tmp_path / "ok.mfbackup"


def test_inspect_rejects_archive_path_traversal(tmp_path: Path):
    archive = tmp_path / "bad.mfbackup"
    with ZipFile(archive, "w") as zip_file:
        write_manifest(zip_file, {
            "format": "media-forge-backup",
            "version": 1,
            "groups": ["movies"],
            "include_sensitive": False,
            "row_counts": {},
        })
        zip_file.writestr("../bad.jsonl", "{}\n")

    with pytest.raises(ValueError, match="Unsafe archive entry"):
        inspect_backup_archive(archive)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_backup_format.py -v
```

Expected: FAIL because `format.py` and `paths.py` do not exist.

- [ ] **Step 3: Implement archive helpers**

Use `zipfile.ZipFile`, `json`, and `hashlib.sha256`. Reject archive entries when `PurePosixPath(name).is_absolute()` is true or any path part is `..`.

Implement `read_jsonl` so line numbers appear in errors:

```python
def read_jsonl(zip_file: ZipFile, arcname: str) -> Iterator[dict[str, Any]]:
    with zip_file.open(arcname, "r") as raw:
        for line_number, raw_line in enumerate(raw, start=1):
            text = raw_line.decode("utf-8").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {arcname}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid JSONL object in {arcname}:{line_number}")
            yield payload
```

Implement `inspect_backup_archive(path)` so it only reads `manifest.json`, checks `format == "media-forge-backup"` and `version == 1`, checks all names for traversal, and returns `BackupInspectResult`.

- [ ] **Step 4: Run format tests**

Run:

```bash
python -m pytest backend/tests/test_backup_format.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/backup/paths.py backend/app/modules/backup/format.py backend/tests/test_backup_format.py
git diff --cached --name-only
git commit -m "feat: add backup archive format"
```

---

### Task 3: Manual Export Service For Database And Config Groups

**Files:**
- Create: `backend/app/modules/backup/exporters.py`
- Create: `backend/app/modules/backup/service.py`
- Modify: `backend/app/modules/backup/format.py`
- Test: `backend/tests/test_backup_export_restore.py`

**Interfaces:**
- Consumes: `write_jsonl`, `write_manifest`, `BackupExportRequest`, `BackupJobRegistry`
- Produces: `BackupService.export_to_file(request: BackupExportRequest, output_dir: Path, owner_id: uuid.UUID, job_id: uuid.UUID | None = None) -> Path`
- Produces: `serialize_model_row(model: object, exclude: set[str] | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write failing export tests**

Add this first set of tests to `backend/tests/test_backup_export_restore.py`:

```python
from pathlib import Path
from zipfile import ZipFile

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.user import User
from backend.app.modules.backup.format import inspect_backup_archive, read_jsonl
from backend.app.modules.backup.schemas import BackupExportRequest
from backend.app.modules.backup.service import BackupService
from shared.database.models.content import Movie, MovieMagnet


def test_export_writes_selected_groups_without_runs(db_session, test_user: User, tmp_path: Path):
    movie = Movie(code="ABC-001", source_url="https://example.test/abc-001", source_name="javdb")
    magnet = MovieMagnet(movie=movie, dedupe_key="hash-1", magnet_url="magnet:?xt=urn:btih:hash")
    task = CrawlTask(name="Actors", owner_id=test_user.id, storage_location="/Movies")
    task.urls.append(CrawlTaskUrl(position=0, url="https://example.test/a", url_type="actors", final_url="https://example.test/a"))
    db_session.add_all([movie, magnet, task])
    db_session.commit()

    path = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["movies", "tasks"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    assert path.suffix == ".mfbackup"
    inspected = inspect_backup_archive(path)
    assert inspected.groups == ["movies", "tasks"]
    assert "data/movies.jsonl" in inspected.row_counts
    assert "data/crawl_tasks.jsonl" in inspected.row_counts
    assert "data/crawl_runs.jsonl" not in inspected.row_counts

    with ZipFile(path) as zip_file:
        movies = list(read_jsonl(zip_file, "data/movies.jsonl"))
        tasks = list(read_jsonl(zip_file, "data/crawl_tasks.jsonl"))
    assert movies[0]["code"] == "ABC-001"
    assert tasks[0]["owner_id"] == str(test_user.id)
```

- [ ] **Step 2: Run export test to verify it fails**

Run:

```bash
python -m pytest backend/tests/test_backup_export_restore.py::test_export_writes_selected_groups_without_runs -v
```

Expected: FAIL because `BackupService.export_to_file` is not implemented.

- [ ] **Step 3: Implement database export**

In `exporters.py`, create explicit model-to-file mappings:

```python
MOVIE_EXPORTS = (
    (Movie, "data/movies.jsonl", None),
    (MovieMagnet, "data/movie_magnets.jsonl", None),
    (MovieFilter, "data/movie_filters.jsonl", None),
)

TASK_EXPORTS = (
    (CrawlTask, "data/crawl_tasks.jsonl", lambda query, owner_id: query.filter(CrawlTask.owner_id == owner_id)),
    (CrawlTaskUrl, "data/crawl_task_urls.jsonl", None),
    (CrawlTaskTag, "data/crawl_task_tags.jsonl", lambda query, owner_id: query.filter(CrawlTaskTag.owner_id == owner_id)),
    (crawl_task_tag_links, "data/crawl_task_tag_links.jsonl", None),
    (CrawlerSchedule, "data/crawler_schedules.jsonl", lambda query, owner_id: query.filter(CrawlerSchedule.owner_id == owner_id)),
    (CrawlerScheduleTask, "data/crawler_schedule_tasks.jsonl", None),
)
```

For link tables, select rows with SQLAlchemy `select(table)` and write plain dictionaries. For ORM models, use `model.__table__.columns` and convert `uuid.UUID`, `datetime`, `date`, and `Decimal` to JSON-compatible values.

In `service.py`, create the timestamped file name and write manifest after the data files. Build `row_counts` from each `write_jsonl` call. If `groups` contains `config`, delegate config export to `export_config_files(zip_file, include_sensitive)`.

- [ ] **Step 4: Run export tests**

Run:

```bash
python -m pytest backend/tests/test_backup_export_restore.py::test_export_writes_selected_groups_without_runs -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/backup/exporters.py backend/app/modules/backup/service.py backend/app/modules/backup/format.py backend/tests/test_backup_export_restore.py
git diff --cached --name-only
git commit -m "feat: export backup archives"
```

---

### Task 4: Restore Inspection, Merge Restore, Overwrite Restore, And Code Conflicts

**Files:**
- Create: `backend/app/modules/backup/restorers.py`
- Modify: `backend/app/modules/backup/service.py`
- Test: `backend/tests/test_backup_export_restore.py`

**Interfaces:**
- Consumes: `read_jsonl`, `BackupRestoreRequest`, `BackupInspectResult`
- Produces: `BackupService.inspect_file(path: Path) -> BackupInspectResult`
- Produces: `BackupService.restore_from_file(path: Path, request: BackupRestoreRequest, owner_id: uuid.UUID, job_id: uuid.UUID | None = None) -> dict[str, Any]`
- Produces: `RestoreStats.created`, `updated`, `skipped`, `conflicts`, `errors`

- [ ] **Step 1: Write failing restore tests**

Append these tests to `backend/tests/test_backup_export_restore.py`:

```python
from backend.app.modules.backup.schemas import BackupRestoreRequest


def test_merge_restore_preserves_movie_code_uniqueness(db_session, test_user: User, tmp_path: Path):
    source_movie = Movie(code="ABC-001", source_url="https://backup.test/abc-001", source_name="javdb")
    db_session.add(source_movie)
    db_session.commit()
    backup = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["movies"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    db_session.delete(source_movie)
    conflicting_movie = Movie(code="ABC-001", source_url="https://local.test/different", source_name="javdb")
    db_session.add(conflicting_movie)
    db_session.commit()

    result = BackupService(db_session).restore_from_file(
        backup,
        BackupRestoreRequest(mode="merge", groups=["movies"]),
        owner_id=test_user.id,
    )

    assert result["movies"]["conflicts"] == 1
    assert db_session.query(Movie).filter(Movie.code == "ABC-001").count() == 1
    assert db_session.query(Movie).filter(Movie.source_url == "https://backup.test/abc-001").count() == 0


def test_overwrite_restore_clears_selected_movie_group(db_session, test_user: User, tmp_path: Path):
    kept_task = CrawlTask(name="Keep Task", owner_id=test_user.id, storage_location="/Movies")
    backup_movie = Movie(code="ABC-002", source_url="https://backup.test/abc-002", source_name="javdb")
    db_session.add_all([kept_task, backup_movie])
    db_session.commit()
    backup = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["movies"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    db_session.query(Movie).delete()
    db_session.add(Movie(code="LOCAL-001", source_url="https://local.test/one", source_name="javdb"))
    db_session.commit()

    result = BackupService(db_session).restore_from_file(
        backup,
        BackupRestoreRequest(mode="overwrite", groups=["movies"]),
        owner_id=test_user.id,
    )

    assert result["movies"]["created"] == 1
    assert db_session.query(Movie).filter(Movie.code == "LOCAL-001").count() == 0
    assert db_session.query(CrawlTask).filter(CrawlTask.name == "Keep Task").count() == 1
```

- [ ] **Step 2: Run restore tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_backup_export_restore.py::test_merge_restore_preserves_movie_code_uniqueness backend/tests/test_backup_export_restore.py::test_overwrite_restore_clears_selected_movie_group -v
```

Expected: FAIL because restore logic is missing.

- [ ] **Step 3: Implement restore helpers**

In `restorers.py`, define:

```python
@dataclass
class RestoreStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    conflicts: int = 0
    errors: int = 0
    conflict_samples: list[dict[str, Any]] = field(default_factory=list)
```

Implement `restore_movies(db, zip_file, mode, batch_size=1000)`:

- If mode is `overwrite`, delete `MovieMagnet`, `MovieFilter`, then `Movie`.
- For each movie row, find an existing movie by `id`, then non-empty `code`, then non-empty `source_url`.
- If `code` points to another movie, increment `conflicts`, append a sample with `code`, `incoming_id`, and `existing_id`, record the incoming movie ID in a skipped set, and do not insert.
- Insert or update using table column names only.
- Flush every batch and commit from `BackupService.restore_from_file` after each batch boundary.
- Restore magnets after movies by mapping incoming `movie_id` to resolved movie IDs; skip magnets whose movie was skipped.
- Rebuild `movie_filters` after movie import by calling the existing filter sync helper if one exists; otherwise compute actor, tag, director, maker, and series counts in the backup module.

Implement `restore_tasks_and_schedules(db, zip_file, mode, owner_id, batch_size=1000)`:

- If mode is `overwrite`, delete schedule links, schedules, task-tag links, task URLs, tasks, and owned tags for the current user.
- Restore owned task and tag rows using `owner_id` from the current user, not the archived owner ID.
- Rebuild link tables from old IDs to new IDs.
- Restore schedules with current `owner_id`.
- Recalculate schedule next-run values using the existing schedule service function if available; otherwise set `next_run_at` to `None` so the scheduler can recompute on load.

Implement `restore_config(zip_file, include_sensitive_in_manifest)`:

- Restore crawler config and movie filter config from archive files when present.
- Restore storage config through `StorageConfigService.update_config`.
- If sensitive data is absent, omit `api_token` and skip `javdb_cookies.json` so local secrets remain intact.

- [ ] **Step 4: Run restore tests**

Run:

```bash
python -m pytest backend/tests/test_backup_export_restore.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/backup/restorers.py backend/app/modules/backup/service.py backend/tests/test_backup_export_restore.py
git diff --cached --name-only
git commit -m "feat: restore backup archives"
```

---

### Task 5: Backend Router, Local Files, Jobs, Scheduler, And App Wiring

**Files:**
- Create: `backend/app/modules/backup/router.py`
- Create: `backend/app/modules/backup/scheduler.py`
- Modify: `backend/app/modules/backup/service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_backup_api.py`
- Test: `backend/tests/test_backup_config_scheduler.py`

**Interfaces:**
- Consumes: `BackupService`, `backup_job_registry`, `backup_operation_lock`
- Produces: `router = APIRouter(prefix="/api/backup", tags=["backup"])`
- Produces: `backup_scheduler.start() -> None`
- Produces: `backup_scheduler.shutdown() -> None`
- Produces: `backup_scheduler.refresh() -> None`
- Produces: `BackupService.list_files() -> list[BackupFileInfo]`
- Produces: `BackupService.delete_file(name: str) -> dict[str, bool]`

- [ ] **Step 1: Write failing API and scheduler tests**

Add to `backend/tests/test_backup_api.py`:

```python
from pathlib import Path

from backend.app.modules.backup.config import BackupConfigService


def test_backup_config_api_round_trip(client, auth_headers, tmp_path: Path, monkeypatch):
    config_file = tmp_path / "backup.conf"
    monkeypatch.setattr(
        "backend.app.modules.backup.router.get_backup_config_service",
        lambda: BackupConfigService(config_file=config_file, project_root=tmp_path),
    )

    response = client.put("/api/backup/config", headers=auth_headers, json={
        "enabled": True,
        "backup_dir": str(tmp_path / "backups"),
        "schedule_type": "daily",
        "time_of_day": "04:15",
        "groups": ["movies"],
        "include_sensitive": False,
        "retention_count": 2,
    })

    assert response.status_code == 200
    assert response.json()["data"]["enabled"] is True
    assert response.json()["data"]["groups"] == ["movies"]


def test_backup_file_delete_rejects_traversal(client, auth_headers):
    response = client.delete("/api/backup/files/..%2Fescape.mfbackup", headers=auth_headers)

    assert response.status_code in {400, 404}
```

Add to `backend/tests/test_backup_config_scheduler.py`:

```python
from backend.app.modules.backup.scheduler import BackupScheduler


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
```

- [ ] **Step 2: Run API and scheduler tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_backup_api.py backend/tests/test_backup_config_scheduler.py -v
```

Expected: FAIL because router and scheduler are not wired.

- [ ] **Step 3: Implement router and in-process job execution**

Router endpoint behavior:

```python
@router.post("/export", response_model=dict)
def start_export(body: BackupExportRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    job = backup_job_registry.create("export")
    service = BackupService(db)
    service.start_export_job(job.id, body, current_user.id)
    return success(data=BackupJobResponse(job_id=job.id).model_dump())
```

Use `threading.Thread(target=..., daemon=True)` in `BackupService.start_export_job` and `start_restore_job`. Each worker must acquire `backup_operation_lock` without blocking. If the lock cannot be acquired, mark the job skipped with reason `backup operation already running`.

Implement upload endpoints with `UploadFile`:

- `POST /inspect` saves upload to a temp file under `/tmp` or the app temp dir, inspects it, and deletes the temp file.
- `POST /restore` saves upload to a temp file, starts restore job, and deletes the temp file inside the worker after restore completes.

Local file endpoints call `safe_backup_file_path`.

- [ ] **Step 4: Implement scheduler and app lifespan wiring**

`BackupScheduler` should use `threading.Timer`. On `start`, read config and schedule the next enabled run. On `refresh`, cancel the current timer and schedule again. On `shutdown`, cancel and clear the timer.

In `backend/app/main.py`:

```python
from backend.app.modules.backup.router import router as backup_router
from backend.app.modules.backup.scheduler import backup_scheduler

app.include_router(backup_router)
```

In lifespan after PostgreSQL startup succeeds:

```python
backup_scheduler.start()
```

In shutdown:

```python
backup_scheduler.shutdown()
```

Patch both methods in `backend/tests/conftest.py` alongside the existing crawler schedule patches.

- [ ] **Step 5: Run backend backup tests**

Run:

```bash
python -m pytest backend/tests/test_backup_format.py backend/tests/test_backup_export_restore.py backend/tests/test_backup_config_scheduler.py backend/tests/test_backup_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/backup/router.py backend/app/modules/backup/scheduler.py backend/app/modules/backup/service.py backend/app/main.py backend/tests/conftest.py backend/tests/test_backup_api.py backend/tests/test_backup_config_scheduler.py
git diff --cached --name-only
git commit -m "feat: add backup API and scheduler"
```

---

### Task 6: Frontend Backup API Client And Query Keys

**Files:**
- Create: `frontend/src/api/backup/types.ts`
- Create: `frontend/src/api/backup/index.ts`
- Modify: `frontend/src/api/queryKeys.ts`
- Modify: `frontend/src/api/queryInvalidation.ts`
- Test: `frontend/tests/backup-api.test.ts`

**Interfaces:**
- Produces: `getBackupConfig(): Promise<BackupConfig>`
- Produces: `updateBackupConfig(payload: BackupConfigUpdate): Promise<BackupConfig>`
- Produces: `listBackupFiles(): Promise<BackupFileInfo[]>`
- Produces: `startBackupExport(payload: BackupExportRequest): Promise<BackupJobResponse>`
- Produces: `inspectBackupFile(file: File): Promise<BackupInspectResult>`
- Produces: `startBackupRestore(file: File, payload: BackupRestoreRequest): Promise<BackupJobResponse>`
- Produces: `restoreLocalBackup(name: string, payload: BackupRestoreRequest): Promise<BackupJobResponse>`
- Produces: `deleteBackupFile(name: string): Promise<{ deleted: boolean }>`
- Produces: `getBackupJob(jobId: string): Promise<BackupJob>`
- Produces: `getBackupDownloadUrl(name: string): string`

- [ ] **Step 1: Write failing API tests**

Add to `frontend/tests/backup-api.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { request } from '@/request'
import {
  getBackupConfig,
  getBackupDownloadUrl,
  startBackupExport,
  updateBackupConfig,
} from '@/api/backup'

vi.mock('@/request', () => ({
  request: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('backup api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reads and updates backup config', async () => {
    vi.mocked(request.get).mockResolvedValueOnce({ enabled: false, groups: ['movies'] })
    vi.mocked(request.put).mockResolvedValueOnce({ enabled: true, groups: ['movies'] })

    await expect(getBackupConfig()).resolves.toEqual({ enabled: false, groups: ['movies'] })
    await expect(updateBackupConfig({ enabled: true, groups: ['movies'] })).resolves.toEqual({ enabled: true, groups: ['movies'] })

    expect(request.get).toHaveBeenCalledWith('/api/backup/config')
    expect(request.put).toHaveBeenCalledWith('/api/backup/config', { enabled: true, groups: ['movies'] })
  })

  it('starts export and builds encoded download urls', async () => {
    vi.mocked(request.post).mockResolvedValueOnce({ job_id: 'job-1' })

    await expect(startBackupExport({ groups: ['movies'], include_sensitive: false })).resolves.toEqual({ job_id: 'job-1' })

    expect(request.post).toHaveBeenCalledWith('/api/backup/export', { groups: ['movies'], include_sensitive: false })
    expect(getBackupDownloadUrl('a b.mfbackup')).toBe('/api/backup/files/a%20b.mfbackup/download')
  })
})
```

- [ ] **Step 2: Run API test to verify it fails**

Run from `frontend/`:

```bash
pnpm test -- ../frontend/tests/backup-api.test.ts
```

Expected: FAIL because `@/api/backup` does not exist.

- [ ] **Step 3: Implement frontend API module**

Define types matching backend JSON names:

```typescript
export type BackupGroup = 'movies' | 'tasks' | 'config'
export type RestoreMode = 'merge' | 'overwrite'
export type BackupJobStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'

export interface BackupConfig {
  enabled: boolean
  backup_dir: string
  schedule_type: 'daily' | 'weekly'
  time_of_day: string
  weekdays: number[]
  groups: BackupGroup[]
  include_sensitive: boolean
  retention_count: number
}
```

Use `FormData` for upload endpoints:

```typescript
export function startBackupRestore(file: File, payload: BackupRestoreRequest): Promise<BackupJobResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('payload', JSON.stringify(payload))
  return request.post<BackupJobResponse>(`${BASE_URL}/restore`, form)
}
```

Add `queryKeys.backup.config()`, `queryKeys.backup.files()`, and `queryKeys.backup.job(jobId)`. Add an invalidation helper that invalidates backup files plus movies, crawler tasks, crawler schedules, crawler config, storage config, and movie filter config according to restored groups.

- [ ] **Step 4: Run frontend API test**

Run from `frontend/`:

```bash
pnpm test -- ../frontend/tests/backup-api.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/backup/types.ts frontend/src/api/backup/index.ts frontend/src/api/queryKeys.ts frontend/src/api/queryInvalidation.ts frontend/tests/backup-api.test.ts
git diff --cached --name-only
git commit -m "feat: add backup frontend api"
```

---

### Task 7: Backup Page UI

**Files:**
- Create: `frontend/src/pages/content/backup/BackupPage.tsx`
- Create: `frontend/src/pages/content/backup/BackupPage.module.less`
- Test: `frontend/tests/backup-page.ui.test.tsx`

**Interfaces:**
- Consumes: frontend API functions from Task 6
- Produces: default export `BackupPage`

- [ ] **Step 1: Write failing page tests**

Add to `frontend/tests/backup-page.ui.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'

import BackupPage from '@/pages/content/backup/BackupPage'

vi.mock('@/api/backup', () => ({
  getBackupConfig: vi.fn().mockResolvedValue({
    enabled: false,
    backup_dir: '/tmp/backups',
    schedule_type: 'daily',
    time_of_day: '03:30',
    weekdays: [],
    groups: ['movies', 'tasks', 'config'],
    include_sensitive: false,
    retention_count: 10,
  }),
  listBackupFiles: vi.fn().mockResolvedValue([]),
  startBackupExport: vi.fn(),
  inspectBackupFile: vi.fn(),
  startBackupRestore: vi.fn(),
  restoreLocalBackup: vi.fn(),
  deleteBackupFile: vi.fn(),
  getBackupJob: vi.fn(),
  getBackupDownloadUrl: vi.fn((name: string) => `/api/backup/files/${name}/download`),
  updateBackupConfig: vi.fn(),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      <App>{children}</App>
    </QueryClientProvider>
  )
}

describe('BackupPage', () => {
  it('renders manual restore and automatic backup areas', async () => {
    render(<BackupPage />, { wrapper })

    expect(await screen.findByText('手动备份')).toBeInTheDocument()
    expect(screen.getByText('恢复备份')).toBeInTheDocument()
    expect(screen.getByText('自动备份')).toBeInTheDocument()
    expect(screen.getAllByText('电影数据').length).toBeGreaterThan(0)
    expect(screen.getAllByText('任务与定时').length).toBeGreaterThan(0)
    expect(screen.getAllByText('配置').length).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: Run page test to verify it fails**

Run from `frontend/`:

```bash
pnpm test -- ../frontend/tests/backup-page.ui.test.tsx
```

Expected: FAIL because `BackupPage` does not exist.

- [ ] **Step 3: Implement page**

Use Ant Design `Card`, `Form`, `Checkbox.Group`, `Switch`, `Radio.Group`, `TimePicker`, `InputNumber`, `Upload`, `Table`, `Progress`, `Alert`, `Button`, `Modal`, and `Space`.

Use these labels:

```typescript
const groupOptions = [
  { label: '电影数据', value: 'movies' },
  { label: '任务与定时', value: 'tasks' },
  { label: '配置', value: 'config' },
]
```

Page state:

- manual export selected groups default to all groups
- manual export sensitive switch default false
- restore mode default `merge`
- restore groups default to inspected manifest groups
- automatic backup form populated from `getBackupConfig`
- backup file table populated from `listBackupFiles`
- job polling enabled while job status is `pending` or `running`

Confirm before:

- manual export with `include_sensitive: true`
- overwrite restore
- deleting a backup file

Use existing page style conventions: constrained page container, 8px radius cards, compact operational controls, no nested cards.

- [ ] **Step 4: Run page test**

Run from `frontend/`:

```bash
pnpm test -- ../frontend/tests/backup-page.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/content/backup/BackupPage.tsx frontend/src/pages/content/backup/BackupPage.module.less frontend/tests/backup-page.ui.test.tsx
git diff --cached --name-only
git commit -m "feat: add backup management page"
```

---

### Task 8: Frontend Route, Sidebar, Tags, README, And End-To-End Verification

**Files:**
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Modify: `frontend/README.md`
- Test: `frontend/tests/routes-tags.test.ts`
- Test: `frontend/tests/layout.ui.test.tsx`

**Interfaces:**
- Consumes: `BackupPage`
- Produces: route `/content/backup`
- Produces: menu selected key `/content/backup`
- Produces: route tag title `数据备份`

- [ ] **Step 1: Write failing route and sidebar tests**

In `frontend/tests/routes-tags.test.ts`, add:

```typescript
import { getRouteTagMeta } from '@/routes/tags'

it('returns backup route tag metadata', () => {
  expect(getRouteTagMeta('/content/backup')).toEqual({ title: '数据备份' })
})
```

In `frontend/tests/layout.ui.test.tsx`, add an assertion to the authenticated layout test:

```typescript
expect(screen.getByText('数据备份')).toBeInTheDocument()
```

- [ ] **Step 2: Run route and layout tests to verify they fail**

Run from `frontend/`:

```bash
pnpm test -- ../frontend/tests/routes-tags.test.ts ../frontend/tests/layout.ui.test.tsx
```

Expected: FAIL because the route tag and menu item are missing.

- [ ] **Step 3: Wire route, menu, and tags**

In `frontend/src/routes/index.tsx`, import and add:

```typescript
import BackupPage from '@/pages/content/backup/BackupPage'

const contentBackupRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/content/backup',
  component: BackupPage,
})
```

Add `contentBackupRoute` to the `layoutRoute.addChildren([...])` list.

In `frontend/src/routes/tags.ts`, add:

```typescript
{ pattern: /^\/content\/backup$/, meta: { title: '数据备份' } },
```

In `frontend/src/layout/Sidebar/index.tsx`, add `SaveOutlined` import and menu item:

```tsx
{
  key: '/content/backup',
  icon: <SaveOutlined />,
  label: '数据备份',
}
```

Update selected key logic so `/content/backup` selects `/content/backup`.

In `frontend/README.md`, add `/content/backup` to the route list and mention `frontend/src/api/backup/` if the existing README lists API modules.

- [ ] **Step 4: Run focused frontend tests**

Run from `frontend/`:

```bash
pnpm test -- ../frontend/tests/routes-tags.test.ts ../frontend/tests/layout.ui.test.tsx ../frontend/tests/backup-api.test.ts ../frontend/tests/backup-page.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Run full verification**

Run:

```bash
python -m pytest backend/tests/test_backup_format.py backend/tests/test_backup_export_restore.py backend/tests/test_backup_config_scheduler.py backend/tests/test_backup_api.py -v
```

Run from `frontend/`:

```bash
pnpm build
pnpm test -- ../frontend/tests/routes-tags.test.ts ../frontend/tests/layout.ui.test.tsx ../frontend/tests/backup-api.test.ts ../frontend/tests/backup-page.ui.test.tsx
```

Expected: all commands PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/index.tsx frontend/src/routes/tags.ts frontend/src/layout/Sidebar/index.tsx frontend/README.md frontend/tests/routes-tags.test.ts frontend/tests/layout.ui.test.tsx
git diff --cached --name-only
git commit -m "feat: route backup page"
```

---

## Final Verification

After all tasks are implemented and committed, run:

```bash
python -m pytest backend/tests/test_backup_format.py backend/tests/test_backup_export_restore.py backend/tests/test_backup_config_scheduler.py backend/tests/test_backup_api.py -v
```

Then run from `frontend/`:

```bash
pnpm build
pnpm test -- ../frontend/tests/backup-api.test.ts ../frontend/tests/backup-page.ui.test.tsx ../frontend/tests/routes-tags.test.ts ../frontend/tests/layout.ui.test.tsx
```

Inspect:

```bash
git status --short
git log --oneline -8
```

The final status should contain no unstaged source changes, and the recent log
should include commits for backend contracts, archive format, export, restore,
API/scheduler, frontend API, backup page, and route wiring.
