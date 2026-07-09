# Storage Index Cache Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local CloudDrive storage index so bulk movie storage sync matches local JSONL data instead of force-refreshing thousands of remote folders.

**Architecture:** Add a focused `backend/app/modules/storage/index/` package that owns index paths, JSONL records, metadata, traversal, and read-only lookup. Keep CloudDrive2 access in one refresh service that uses `GetSubFiles` level-by-level with `forceRefresh=false` by default; the refresh writes accepted records incrementally to `storage_index.jsonl.tmp`, then atomically replaces `storage_index.jsonl` only after completion. Movie bulk sync consumes only the completed index and does not issue per-movie remote listings.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic/dataclasses, JSON/JSONL files under `RuntimeConfigPaths.config_dir`, existing CloudDrive2 gateway, pytest, React/TypeScript for minimal storage index status controls.

## Global Constraints

- Do not recursively force-refresh every movie or code-folder candidate during bulk sync.
- Do not depend on undocumented CloudDrive2 internals for file listings.
- Do not change storage task download, move, copy, rename, or target planning behavior.
- Do not require a frontend redesign; only add controls or status indicators directly needed for index refresh and sync clarity.
- Bulk sync must not force-refresh CloudDrive2.
- Running refreshes write partial records only to `storage_index.jsonl.tmp`.
- Bulk sync must never read `storage_index.jsonl.tmp`; it reads only completed `storage_index.jsonl`.
- Existing `storage_summary` records remain valid.
- File-based metadata is sufficient for the initial implementation.

---

## File Structure

- Create `backend/app/modules/storage/index/__init__.py`: package marker.
- Create `backend/app/modules/storage/index/models.py`: dataclasses for index records and metadata.
- Create `backend/app/modules/storage/index/store.py`: file path resolution, running JSONL temp writes, atomic completed-index replacement, metadata reads, index lookup.
- Create `backend/app/modules/storage/index/refresh.py`: CloudDrive traversal from `target_folder -> category -> code folder -> video file`.
- Create `backend/app/modules/storage/index/router.py`: `POST /api/storage/index/refresh` and `GET /api/storage/index/status`.
- Modify `shared/runtime_config.py`: expose index file and metadata file paths.
- Modify `backend/app/main.py`: include the storage index router.
- Modify `backend/app/modules/content/movies/storage_sync_service.py`: choose index-backed sync for bulk requests and preserve bounded remote sync for small selections.
- Modify `backend/app/modules/content/movies/schemas.py`: add explicit sync mode and index metadata fields to request/response models.
- Modify frontend storage API/page files only after backend tests pass, keeping UI minimal.

### Task 1: Index File Store

**Files:**
- Modify: `shared/runtime_config.py`
- Create: `backend/app/modules/storage/index/__init__.py`
- Create: `backend/app/modules/storage/index/models.py`
- Create: `backend/app/modules/storage/index/store.py`
- Test: `backend/tests/test_storage_index_store.py`

**Interfaces:**
- Produces: `StorageIndexRecord`
- Produces: `StorageIndexMetadata`
- Produces: `StorageIndexStore.begin_temp_index() -> Path`
- Produces: `StorageIndexStore.append_temp_record(record) -> None`
- Produces: `StorageIndexStore.finalize_temp_index(metadata) -> StorageIndexMetadata`
- Produces: `StorageIndexStore.load_index_by_code() -> dict[str, list[StorageIndexRecord]]`
- Produces: `StorageIndexStore.read_metadata() -> StorageIndexMetadata`

- [ ] **Step 1: Write failing store tests**

Create `backend/tests/test_storage_index_store.py`:

```python
from datetime import datetime, timezone

from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.runtime_config import RuntimeConfigPaths


def test_storage_index_store_streams_temp_then_finalizes_completed_index(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )
    store = StorageIndexStore(paths)
    metadata = StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="completed",
        started_at="2026-07-09T00:00:00+00:00",
        completed_at="2026-07-09T00:01:00+00:00",
        category_count=1,
        code_folder_count=1,
        video_count=1,
        force_refresh_mode="none",
        errors=[],
    )
    record = StorageIndexRecord(
        code="ALDN-206",
        path="/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4",
        target_folder="/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U",
        storage_location="巨乳|熟女|BBW",
        file_name="ALDN-206-U.mp4",
        size=524288000,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )

    temp_path = store.begin_temp_index()
    store.append_temp_record(record)

    assert temp_path.exists()
    assert temp_path.read_text(encoding="utf-8").strip()
    assert not paths.storage_index_file.exists()

    store.finalize_temp_index(metadata)

    assert not temp_path.exists()
    assert paths.storage_index_file.exists()
    assert paths.storage_index_meta_file.exists()
    assert store.read_metadata().status == "completed"
    assert store.load_index_by_code()["ALDN-206"][0].path == record.path


def test_storage_index_store_does_not_load_running_temp_index(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )
    store = StorageIndexStore(paths)
    store.begin_temp_index()
    store.write_running_metadata(StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="running",
        started_at="2026-07-09T00:00:00+00:00",
        current_path="/嘿嘿/日本/巨乳|熟女|BBW",
        video_count=1,
    ))

    try:
        store.load_index_by_code()
    except Exception as exc:
        assert "存储索引不存在或尚未完成" in str(exc)
    else:
        raise AssertionError("running temp index must not be loaded for bulk sync")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py -v
```

Expected: FAIL with import errors for missing `storage.index` modules or missing `RuntimeConfigPaths` fields.

- [ ] **Step 3: Add runtime paths**

In `shared/runtime_config.py`, extend `RuntimeConfigPaths`:

```python
@dataclass(frozen=True)
class RuntimeConfigPaths:
    config_dir: Path
    database_file: Path
    redis_file: Path
    storage_file: Path
    storage_index_file: Path
    storage_index_meta_file: Path

    @classmethod
    def from_env(cls) -> "RuntimeConfigPaths":
        configured_dir = os.getenv(CONFIG_DIR_ENV)
        config_dir = Path(configured_dir).expanduser() if configured_dir else PROJECT_ROOT / "data/configs"
        return cls(
            config_dir=config_dir,
            database_file=config_dir / "database.conf",
            redis_file=config_dir / "redis.conf",
            storage_file=config_dir / "storage.conf",
            storage_index_file=config_dir / "storage_index.jsonl",
            storage_index_meta_file=config_dir / "storage_index.meta.json",
        )
```

- [ ] **Step 4: Add models**

Create `backend/app/modules/storage/index/models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


IndexStatus = Literal["never_built", "running", "completed", "failed"]


@dataclass(frozen=True)
class StorageIndexRecord:
    code: str
    path: str
    target_folder: str
    storage_location: str
    file_name: str
    size: int
    indexed_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StorageIndexRecord":
        return cls(
            code=str(data["code"]),
            path=str(data["path"]),
            target_folder=str(data["target_folder"]),
            storage_location=str(data.get("storage_location") or ""),
            file_name=str(data["file_name"]),
            size=int(data.get("size") or 0),
            indexed_at=str(data["indexed_at"]),
        )


@dataclass(frozen=True)
class StorageIndexMetadata:
    target_folder: str
    status: IndexStatus
    started_at: str | None = None
    completed_at: str | None = None
    category_count: int = 0
    code_folder_count: int = 0
    video_count: int = 0
    force_refresh_mode: str = "none"
    current_path: str | None = None
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def never_built(cls) -> "StorageIndexMetadata":
        return cls(target_folder="", status="never_built")

    @classmethod
    def from_dict(cls, data: dict) -> "StorageIndexMetadata":
        return cls(
            target_folder=str(data.get("target_folder") or ""),
            status=str(data.get("status") or "never_built"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            category_count=int(data.get("category_count") or 0),
            code_folder_count=int(data.get("code_folder_count") or 0),
            video_count=int(data.get("video_count") or 0),
            force_refresh_mode=str(data.get("force_refresh_mode") or "none"),
            current_path=data.get("current_path"),
            errors=list(data.get("errors") or []),
        )
```

- [ ] **Step 5: Add store**

Create `backend/app/modules/storage/index/store.py`:

```python
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from shared.runtime_config import RuntimeConfigPaths
from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord


class StorageIndexMissingError(RuntimeError):
    pass


class StorageIndexStore:
    def __init__(self, paths: RuntimeConfigPaths | None = None) -> None:
        self.paths = paths or RuntimeConfigPaths.from_env()

    def read_metadata(self) -> StorageIndexMetadata:
        path = self.paths.storage_index_meta_file
        if not path.exists():
            return StorageIndexMetadata.never_built()
        return StorageIndexMetadata.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def write_running_metadata(self, metadata: StorageIndexMetadata) -> None:
        self._write_json_atomic(self.paths.storage_index_meta_file, metadata.to_dict())

    @property
    def temp_index_file(self) -> Path:
        return self.paths.storage_index_file.with_suffix(self.paths.storage_index_file.suffix + ".tmp")

    def begin_temp_index(self) -> Path:
        temp_path = self.temp_index_file
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text("", encoding="utf-8")
        return temp_path

    def append_temp_record(self, record: StorageIndexRecord) -> None:
        temp_path = self.temp_index_file
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with temp_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            handle.flush()

    def finalize_temp_index(self, metadata: StorageIndexMetadata) -> StorageIndexMetadata:
        temp_path = self.temp_index_file
        if not temp_path.exists():
            temp_path.write_text("", encoding="utf-8")
        temp_path.replace(self.paths.storage_index_file)
        self._write_json_atomic(self.paths.storage_index_meta_file, metadata.to_dict())
        return metadata

    def load_index_by_code(self) -> dict[str, list[StorageIndexRecord]]:
        metadata = self.read_metadata()
        if metadata.status != "completed" or not self.paths.storage_index_file.exists():
            raise StorageIndexMissingError("存储索引不存在或尚未完成，请先刷新存储索引")
        grouped: dict[str, list[StorageIndexRecord]] = defaultdict(list)
        with self.paths.storage_index_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = StorageIndexRecord.from_dict(json.loads(line))
                grouped[record.code].append(record)
        return dict(grouped)

    def _write_json_atomic(self, path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
```

Create `backend/app/modules/storage/index/__init__.py` as an empty package marker.

- [ ] **Step 6: Run store tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add shared/runtime_config.py backend/app/modules/storage/index/__init__.py backend/app/modules/storage/index/models.py backend/app/modules/storage/index/store.py backend/tests/test_storage_index_store.py
git commit -m "feat: add storage index file store"
```

### Task 2: CloudDrive Index Refresh Service

**Files:**
- Create: `backend/app/modules/storage/index/refresh.py`
- Test: `backend/tests/test_storage_index_refresh.py`

**Interfaces:**
- Consumes: `StorageIndexStore`
- Produces: `StorageIndexRefreshService.refresh(config: dict, provider, force_refresh_mode: str = "none") -> StorageIndexMetadata`

- [ ] **Step 1: Write failing refresh test**

Create `backend/tests/test_storage_index_refresh.py`:

```python
from dataclasses import dataclass

from backend.app.modules.storage.index.refresh import StorageIndexRefreshService
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.runtime_config import RuntimeConfigPaths


@dataclass
class RemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False


def test_refresh_builds_index_without_force_refreshing_code_folders(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )

    class Provider:
        def __init__(self) -> None:
            self.calls = []

        def list_files(self, path, force_refresh=False):
            self.calls.append((path, force_refresh))
            if path == "/嘿嘿/日本":
                return [RemoteFile("巨乳|熟女|BBW", "/嘿嘿/日本/巨乳|熟女|BBW", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW":
                return [RemoteFile("ALDN-206-U", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U":
                return [RemoteFile("ALDN-206-U.mp4", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4", 500 * 1024 * 1024)]
            return []

    provider = Provider()
    service = StorageIndexRefreshService(StorageIndexStore(paths))

    metadata = service.refresh(
        {"target_folder": "/嘿嘿/日本", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        provider,
    )

    assert metadata.status == "completed"
    assert metadata.video_count == 1
    assert all(force_refresh is False for _path, force_refresh in provider.calls)
    assert not StorageIndexStore(paths).temp_index_file.exists()
    grouped = StorageIndexStore(paths).load_index_by_code()
    assert grouped["ALDN-206"][0].storage_location == "巨乳|熟女|BBW"


def test_refresh_writes_running_records_to_temp_jsonl(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )
    store = StorageIndexStore(paths)

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/嘿嘿/日本":
                assert store.temp_index_file.exists()
                return [RemoteFile("巨乳|熟女|BBW", "/嘿嘿/日本/巨乳|熟女|BBW", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW":
                return [RemoteFile("ALDN-206-U", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U":
                return [RemoteFile("ALDN-206-U.mp4", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4", 500 * 1024 * 1024)]
            return []

    StorageIndexRefreshService(store).refresh(
        {"target_folder": "/嘿嘿/日本", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        Provider(),
    )

    assert paths.storage_index_file.exists()
    assert "ALDN-206-U.mp4" in paths.storage_index_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_refresh.py -v
```

Expected: FAIL because `StorageIndexRefreshService` is missing.

- [ ] **Step 3: Implement refresh service**

Create `backend/app/modules/storage/index/refresh.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath

from backend.app.modules.content.movies.storage_scan import is_matching_video, remote_entry_to_dict
from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.database.models.content import Movie


class StorageIndexRefreshService:
    def __init__(self, store: StorageIndexStore | None = None) -> None:
        self.store = store or StorageIndexStore()

    def refresh(self, config: dict, provider, *, force_refresh_mode: str = "none") -> StorageIndexMetadata:
        target_root = str(config.get("target_folder") or "/Movies").rstrip("/")
        started_at = datetime.now(timezone.utc).isoformat()
        self.store.write_running_metadata(StorageIndexMetadata(target_folder=target_root, status="running", started_at=started_at))
        errors: list[dict] = []
        category_count = 0
        code_folder_count = 0
        video_count = 0
        self.store.begin_temp_index()

        try:
            categories = self._safe_list(provider, target_root, force_refresh=False, errors=errors)
            for category_entry in categories:
                category = remote_entry_to_dict(category_entry, target_root)
                if not category["is_dir"] or not category["name"]:
                    continue
                category_count += 1
                category_folder = category["path"] or str(PurePosixPath(target_root) / category["name"])
                code_folders = self._safe_list(provider, category_folder, force_refresh=False, errors=errors)
                for code_entry in code_folders:
                    code_folder_item = remote_entry_to_dict(code_entry, category_folder)
                    if not code_folder_item["is_dir"] or not code_folder_item["name"]:
                        continue
                    code_folder_count += 1
                    code_folder = code_folder_item["path"] or str(PurePosixPath(category_folder) / code_folder_item["name"])
                    self.store.write_running_metadata(StorageIndexMetadata(
                        target_folder=target_root,
                        status="running",
                        started_at=started_at,
                        category_count=category_count,
                        code_folder_count=code_folder_count,
                        video_count=video_count,
                        force_refresh_mode=force_refresh_mode,
                        current_path=code_folder,
                        errors=errors,
                    ))
                    files = self._safe_list(provider, code_folder, force_refresh=False, errors=errors)
                    for record in self._records_from_files(files, code_folder, category["name"], config, started_at):
                        self.store.append_temp_record(record)
                        video_count += 1
        except Exception as exc:
            failed = StorageIndexMetadata(target_folder=target_root, status="failed", started_at=started_at, errors=[{"path": target_root, "error": str(exc)}])
            self.store.write_running_metadata(failed)
            raise

        completed = StorageIndexMetadata(
            target_folder=target_root,
            status="completed",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            category_count=category_count,
            code_folder_count=code_folder_count,
            video_count=video_count,
            force_refresh_mode=force_refresh_mode,
            errors=errors,
        )
        return self.store.finalize_temp_index(completed)

    def _safe_list(self, provider, path: str, *, force_refresh: bool, errors: list[dict]):
        try:
            return provider.list_files(path, force_refresh=force_refresh)
        except TypeError:
            try:
                return provider.list_files(path)
            except Exception as exc:
                errors.append({"path": path, "error": str(exc)})
                return []
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
            return []

    def _records_from_files(self, files, code_folder: str, storage_location: str, config: dict, indexed_at: str) -> list[StorageIndexRecord]:
        records: list[StorageIndexRecord] = []
        folder_name = PurePosixPath(code_folder).name
        base_code = _base_code_from_folder(folder_name)
        movie_stub = Movie(code=base_code)
        for file_entry in files:
            item = remote_entry_to_dict(file_entry, code_folder)
            if not is_matching_video(movie_stub, item, config):
                continue
            records.append(StorageIndexRecord(
                code=base_code,
                path=item["path"],
                target_folder=code_folder,
                storage_location=storage_location,
                file_name=item["name"],
                size=item["size"],
                indexed_at=indexed_at,
            ))
        return records


def _base_code_from_folder(folder_name: str) -> str:
    upper = folder_name.upper()
    for suffix in ("-UC", "-C", "-U"):
        if upper.endswith(suffix):
            return upper[: -len(suffix)]
    return upper
```

- [ ] **Step 4: Run refresh tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_refresh.py backend/tests/test_storage_index_store.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add backend/app/modules/storage/index/refresh.py backend/tests/test_storage_index_refresh.py
git commit -m "feat: build storage index from clouddrive"
```

### Task 3: Index-Backed Movie Sync

**Files:**
- Modify: `backend/app/modules/content/movies/storage_sync_service.py`
- Test: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes: `StorageIndexStore.load_index_by_code()`
- Produces: bulk sync path that updates `storage_summary` without remote per-movie listings.

- [ ] **Step 1: Write failing index-backed sync test**

Append to `backend/tests/test_content_movies_api.py`:

```python
def test_bulk_storage_sync_uses_index_without_remote_listing(db_session, admin_user, tmp_path, monkeypatch):
    from shared.runtime_config import RuntimeConfigPaths
    from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord
    from backend.app.modules.storage.index.store import StorageIndexStore
    from backend.app.modules.content.movies.storage_sync_service import sync_movies_storage_statuses
    from shared.database.models.content import Movie

    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )
    store = StorageIndexStore(paths)
    store.begin_temp_index()
    store.append_temp_record(
        StorageIndexRecord(
            "ALDN-206",
            "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4",
            "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U",
            "巨乳|熟女|BBW",
            "ALDN-206-U.mp4",
            500 * 1024 * 1024,
            "2026-07-09T00:00:00+00:00",
        )
    )
    store.finalize_temp_index(
        StorageIndexMetadata("/嘿嘿/日本", "completed", completed_at="2026-07-09T00:00:00+00:00", video_count=1)
    )
    monkeypatch.setattr("backend.app.modules.content.movies.storage_sync_service.StorageIndexStore", lambda: store)
    monkeypatch.setattr("backend.app.modules.storage.tasks.events.publish_movie_storage_updated", lambda *args, **kwargs: None)

    movie = Movie(code="ALDN-206", source_name="indexed movie", storage_summary={})
    db_session.add(movie)
    db_session.commit()

    payload = sync_movies_storage_statuses(db_session, user_id=str(admin_user.id), movies=[movie])

    assert payload.stored_count == 1
    assert movie.storage_summary["locations"][0]["path"].endswith("ALDN-206-U.mp4")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_bulk_storage_sync_uses_index_without_remote_listing -v
```

Expected: FAIL because bulk sync still opens the CloudDrive provider and does not read the index.

- [ ] **Step 3: Implement index matching in sync service**

In `backend/app/modules/content/movies/storage_sync_service.py`, import the store and status helper:

```python
from backend.app.modules.content.movies.storage_status import STORAGE_STATUS_NOT_STORED, set_movie_storage_status
from backend.app.modules.storage.index.store import StorageIndexMissingError, StorageIndexStore
```

Add:

```python
def _sync_movies_from_index(db: Session, movies: list[Movie]) -> list:
    index = StorageIndexStore().load_index_by_code()
    results = []
    for movie in movies:
        code = str(movie.code or "").upper()
        locations = [
            {
                "path": record.path,
                "target_folder": record.target_folder,
                "storage_location": record.storage_location,
                "file_name": record.file_name,
                "size": record.size,
                "exists": True,
                "source": "storage_index",
            }
            for record in index.get(code, [])
        ]
        status = STORAGE_STATUS_STORED if locations else STORAGE_STATUS_NOT_STORED
        set_movie_storage_status(movie, status, source="storage_index", locations=locations)
        results.append(type("IndexSyncResult", (), {
            "movie_id": str(movie.id),
            "status": status,
            "found_count": len(locations),
            "checked_targets": [],
            "locations": locations,
        })())
    return results
```

Then in `sync_movies_storage_statuses`, use index for bulk:

```python
    try:
        results = _sync_movies_from_index(db, movies)
    except StorageIndexMissingError:
        if len(movies) > 1:
            raise
        with service.open_provider() as (config, provider):
            results = [sync_movie_storage_status(db=db, movie=movie, provider=provider, config=config, source="manual_sync") for movie in movies]
```

Keep the existing response shape.

- [ ] **Step 4: Run index sync tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_bulk_storage_sync_uses_index_without_remote_listing backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_api_syncs_selected_movies -v
```

Expected: PASS. Keep single-movie remote fallback behavior intact and assert bulk sync uses the index.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add backend/app/modules/content/movies/storage_sync_service.py backend/tests/test_content_movies_api.py
git commit -m "feat: sync movie storage status from index"
```

### Task 4: Storage Index API and Minimal UI

**Files:**
- Create: `backend/app/modules/storage/index/router.py`
- Modify: `backend/app/main.py`
- Modify: frontend storage API/page files discovered with `rg -n "storage-sync|StorageConfig|storage config|storage tasks" frontend/src frontend/tests -S`
- Test: `backend/tests/test_storage_index_api.py`

**Interfaces:**
- Produces: `POST /api/storage/index/refresh`
- Produces: `GET /api/storage/index/status`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_storage_index_api.py`:

```python
from http import HTTPStatus

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_storage_index_status_returns_never_built(client: TestClient, admin_user, tmp_path, monkeypatch):
    from shared.runtime_config import RuntimeConfigPaths
    paths = RuntimeConfigPaths(tmp_path, tmp_path / "database.conf", tmp_path / "redis.conf", tmp_path / "storage.conf", tmp_path / "storage_index.jsonl", tmp_path / "storage_index.meta.json")
    monkeypatch.setattr("backend.app.modules.storage.index.store.RuntimeConfigPaths.from_env", lambda: paths)

    response = client.get("/api/storage/index/status", headers=auth_headers(client, admin_user))

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["status"] == "never_built"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_api.py -v
```

Expected: FAIL with route not found.

- [ ] **Step 3: Add router**

Create `backend/app/modules/storage/index/router.py`:

```python
from fastapi import APIRouter, Depends

from backend.app.core.dependencies import CurrentUser, get_storage_config_service
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.index.refresh import StorageIndexRefreshService
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/index", tags=["storage-index"])


@router.get("/status")
def get_storage_index_status(_current_user: CurrentUser) -> dict:
    return success(data=StorageIndexStore().read_metadata().to_dict())


@router.post("/refresh")
def refresh_storage_index(
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    with service.open_provider() as (config, provider):
        metadata = StorageIndexRefreshService().refresh(config, provider)
    return success(data=metadata.to_dict())
```

Modify `backend/app/main.py`:

```python
from backend.app.modules.storage.index.router import router as storage_index_router

app.include_router(storage_index_router)
```

- [ ] **Step 4: Run API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Add minimal frontend controls**

Locate files:

```bash
rg -n "storage-sync|StorageConfig|storage config|存储" frontend/src frontend/tests -S
```

Add API functions named:

```ts
export async function fetchStorageIndexStatus(): Promise<StorageIndexMetadata>
export async function refreshStorageIndex(): Promise<StorageIndexMetadata>
```

Render status text and a refresh button near existing storage sync controls. Use existing Ant Design button/message patterns. Do not redesign the page.

- [ ] **Step 6: Run backend and frontend checks**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py backend/tests/test_storage_index_refresh.py backend/tests/test_storage_index_api.py backend/tests/test_content_movies_api.py -v
cd frontend && npm test -- --run
```

Expected: backend selected tests PASS; frontend tests PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add backend/app/modules/storage/index/router.py backend/app/main.py backend/tests/test_storage_index_api.py frontend/src frontend/tests
git commit -m "feat: expose storage index refresh"
```
