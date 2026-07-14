# Movie Storage Index Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move storage index actions to the movie list, support full/incremental tree indexes, make normal storage sync index-only, and add one-row CD2 sync actions that update the index.

**Architecture:** Keep the existing storage index API boundary but change the store from JSONL records to a tree JSON document with a stable `load_index_by_code()` flattening interface. Add explicit index refresh modes and split movie storage sync into index-only bulk/filter sync plus single-movie CD2 sync. On the frontend, remove the index card from storage config, add a movie-list index Dropdown, rename toolbar sync to index sync, and add per-row `CD2同步`.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, Vitest 3, React Testing Library.

## Global Constraints

- Project scope remains the Media Forge refactor and optimization of `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.
- No database schema changes.
- No background job queue for index refresh.
- No multi-row CD2 sync.
- No CloudDrive2 sync in the movie-list toolbar.
- Normal movie-list storage sync reads only the local tree index.
- CD2 sync exists only as a per-row movie table action and updates the index tree.
- Incremental index refresh may list category and code-folder directories, but must not list videos inside old code folders already present in the index tree.

---

## File Structure

- Modify `backend/app/modules/storage/index/models.py`
  - Add typed tree structures while preserving `StorageIndexRecord` and `StorageIndexMetadata`.
- Modify `backend/app/modules/storage/index/store.py`
  - Replace JSONL temp append/finalize with tree JSON read/write/upsert.
  - Keep `load_index_by_code()` as the compatibility read interface.
- Modify `backend/app/modules/storage/index/refresh.py`
  - Add `mode: "full" | "incremental"`.
  - Full rebuilds the tree; incremental skips existing code folders.
- Modify `backend/app/modules/storage/index/router.py`
  - Accept refresh request body `{ mode: "full" | "incremental" }`.
- Modify `backend/app/modules/content/movies/storage_sync_service.py`
  - Make existing bulk/filter sync index-only.
  - Add single-movie CD2 sync helper that updates movie status and upserts found locations into the index tree.
- Modify `backend/app/modules/content/movies/router.py`
  - Add `POST /api/content/movies/{movie_id}/storage-sync/cd2`.
- Modify backend tests:
  - `backend/tests/test_storage_index_store.py`
  - `backend/tests/test_storage_index_refresh.py`
  - `backend/tests/test_storage_index_api.py`
  - `backend/tests/test_content_movies_api.py`
- Modify `frontend/src/api/storage/storageIndex/index.ts` and `types.ts`
  - Add refresh mode request.
- Modify `frontend/src/api/movie/index.ts`
  - Add single-row CD2 sync API.
- Modify `frontend/src/pages/storage/config/StorageConfigPage.tsx`
  - Remove storage index card and related state.
- Modify `frontend/src/pages/content/movies/MovieListPage.tsx`
  - Add storage index Dropdown.
  - Rename toolbar sync to `索引同步`.
  - Wire row CD2 sync into columns.
- Modify `frontend/src/pages/content/movies/components/MovieTable.tsx`
  - Add optional `onCd2Sync(movie)` row action.
- Modify frontend tests:
  - `frontend/tests/storage-config.ui.test.tsx`
  - `frontend/tests/movie-list.ui.test.tsx`
  - `frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx`

### Task 1: Tree Storage Index Store

**Files:**
- Modify: `backend/app/modules/storage/index/models.py`
- Modify: `backend/app/modules/storage/index/store.py`
- Modify: `backend/tests/test_storage_index_store.py`

**Interfaces:**
- Consumes: `StorageIndexRecord(code, path, target_folder, storage_location, file_name, size, indexed_at)`.
- Produces:
  - `StorageIndexStore.begin_temp_index(target_folder: str | None = None) -> Path`
  - `StorageIndexStore.write_temp_tree(tree: dict) -> None`
  - `StorageIndexStore.read_index_tree() -> dict`
  - `StorageIndexStore.finalize_temp_index(metadata: StorageIndexMetadata) -> StorageIndexMetadata`
  - `StorageIndexStore.load_index_by_code() -> dict[str, list[StorageIndexRecord]]`
  - `StorageIndexStore.upsert_records(records: list[StorageIndexRecord], target_folder: str) -> None`

- [ ] **Step 1: Write failing tree store tests**

Replace `backend/tests/test_storage_index_store.py` with:

```python
from datetime import datetime, timezone

import pytest

from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord
from backend.app.modules.storage.index.store import StorageIndexMissingError, StorageIndexStore
from shared.runtime_config import RuntimeConfigPaths


def paths_for(tmp_path):
    return RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )


def record(code="ALDN-206", folder="/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U"):
    return StorageIndexRecord(
        code=code,
        path=f"{folder}/ALDN-206-U.mp4",
        target_folder=folder,
        storage_location="巨乳|熟女|BBW",
        file_name="ALDN-206-U.mp4",
        size=524288000,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )


def completed_metadata() -> StorageIndexMetadata:
    return StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="completed",
        started_at="2026-07-09T00:00:00+00:00",
        completed_at="2026-07-09T00:01:00+00:00",
        category_count=1,
        code_folder_count=1,
        video_count=1,
        force_refresh_mode="full",
        errors=[],
    )


def test_storage_index_store_writes_tree_and_flattens_by_code(tmp_path):
    store = StorageIndexStore(paths_for(tmp_path))
    item = record()
    tree = store.tree_from_records("/嘿嘿/日本", [item], indexed_at=item.indexed_at)

    store.begin_temp_index("/嘿嘿/日本")
    store.write_temp_tree(tree)
    store.finalize_temp_index(completed_metadata())

    saved_tree = store.read_index_tree()
    assert saved_tree["version"] == 1
    assert saved_tree["target_folder"] == "/嘿嘿/日本"
    assert "巨乳|熟女|BBW" in saved_tree["categories"]
    assert store.load_index_by_code()["ALDN-206"][0].path == item.path


def test_storage_index_store_upserts_records_into_existing_tree(tmp_path):
    store = StorageIndexStore(paths_for(tmp_path))
    first = record()
    second = StorageIndexRecord(
        code="BBBB-001",
        path="/嘿嘿/日本/新分类/BBBB-001/BBBB-001.mp4",
        target_folder="/嘿嘿/日本/新分类/BBBB-001",
        storage_location="新分类",
        file_name="BBBB-001.mp4",
        size=734003200,
        indexed_at="2026-07-10T00:00:00+00:00",
    )

    store.begin_temp_index("/嘿嘿/日本")
    store.write_temp_tree(store.tree_from_records("/嘿嘿/日本", [first], indexed_at=first.indexed_at))
    store.finalize_temp_index(completed_metadata())

    store.upsert_records([second], target_folder="/嘿嘿/日本")

    grouped = store.load_index_by_code()
    assert grouped["ALDN-206"][0].path == first.path
    assert grouped["BBBB-001"][0].path == second.path


def test_storage_index_store_does_not_load_running_temp_index(tmp_path):
    store = StorageIndexStore(paths_for(tmp_path))
    store.begin_temp_index("/嘿嘿/日本")
    store.write_running_metadata(StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="running",
        started_at="2026-07-09T00:00:00+00:00",
        current_path="/嘿嘿/日本/巨乳|熟女|BBW",
        video_count=1,
    ))

    with pytest.raises(StorageIndexMissingError, match="存储索引不存在或尚未完成"):
        store.load_index_by_code()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py -v
```

Expected: FAIL because the store has no tree APIs.

- [ ] **Step 3: Implement tree helpers**

In `backend/app/modules/storage/index/store.py`, replace the file body with:

```python
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from shared.runtime_config import RuntimeConfigPaths
from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord


class StorageIndexMissingError(RuntimeError):
    pass


class StorageIndexStore:
    TREE_VERSION = 1

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
    def temp_index_file(self):
        return self.paths.storage_index_file.with_suffix(self.paths.storage_index_file.suffix + ".tmp")

    def begin_temp_index(self, target_folder: str | None = None):
        temp_path = self.temp_index_file
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        if target_folder is None:
            temp_path.write_text("", encoding="utf-8")
        else:
            self.write_temp_tree(self.empty_tree(target_folder, indexed_at=None))
        return temp_path

    def append_temp_record(self, record: StorageIndexRecord) -> None:
        tree = self._read_tree_file(self.temp_index_file) if self.temp_index_file.exists() and self.temp_index_file.read_text(encoding="utf-8").strip() else self.empty_tree("", record.indexed_at)
        self._insert_record(tree, record)
        self.write_temp_tree(tree)

    def write_temp_tree(self, tree: dict[str, Any]) -> None:
        self._write_json_atomic(self.temp_index_file, tree)

    def finalize_temp_index(self, metadata: StorageIndexMetadata) -> StorageIndexMetadata:
        temp_path = self.temp_index_file
        if not temp_path.exists() or not temp_path.read_text(encoding="utf-8").strip():
            self.write_temp_tree(self.empty_tree(metadata.target_folder, metadata.completed_at or metadata.started_at))
        temp_path.replace(self.paths.storage_index_file)
        self._write_json_atomic(self.paths.storage_index_meta_file, metadata.to_dict())
        return metadata

    def read_index_tree(self) -> dict[str, Any]:
        metadata = self.read_metadata()
        if metadata.status != "completed" or not self.paths.storage_index_file.exists():
            raise StorageIndexMissingError("存储索引不存在或尚未完成，请先刷新存储索引")
        return self._read_tree_file(self.paths.storage_index_file)

    def load_index_by_code(self) -> dict[str, list[StorageIndexRecord]]:
        tree = self.read_index_tree()
        grouped: dict[str, list[StorageIndexRecord]] = defaultdict(list)
        for category_name, category in (tree.get("categories") or {}).items():
            for _folder_name, code_folder in (category.get("code_folders") or {}).items():
                code = str(code_folder.get("code") or "").upper()
                target_folder = str(code_folder.get("path") or "")
                for video in code_folder.get("videos") or []:
                    record = StorageIndexRecord(
                        code=code,
                        path=str(video["path"]),
                        target_folder=target_folder,
                        storage_location=str(category_name),
                        file_name=str(video["file_name"]),
                        size=int(video.get("size") or 0),
                        indexed_at=str(video["indexed_at"]),
                    )
                    grouped[record.code].append(record)
        return dict(grouped)

    def upsert_records(self, records: list[StorageIndexRecord], target_folder: str) -> None:
        try:
            tree = self.read_index_tree()
        except StorageIndexMissingError:
            tree = self.empty_tree(target_folder, indexed_at=None)
        for record in records:
            self._insert_record(tree, record)
        self._write_json_atomic(self.paths.storage_index_file, tree)

    def tree_from_records(self, target_folder: str, records: list[StorageIndexRecord], *, indexed_at: str | None) -> dict[str, Any]:
        tree = self.empty_tree(target_folder, indexed_at=indexed_at)
        for record in records:
            self._insert_record(tree, record)
        return tree

    def empty_tree(self, target_folder: str, indexed_at: str | None) -> dict[str, Any]:
        return {
            "version": self.TREE_VERSION,
            "target_folder": target_folder,
            "indexed_at": indexed_at,
            "categories": {},
        }

    def known_code_folder_paths(self) -> set[str]:
        try:
            tree = self.read_index_tree()
        except StorageIndexMissingError:
            return set()
        paths: set[str] = set()
        for category in (tree.get("categories") or {}).values():
            for code_folder in (category.get("code_folders") or {}).values():
                path = str(code_folder.get("path") or "")
                if path:
                    paths.add(path)
        return paths

    def _insert_record(self, tree: dict[str, Any], record: StorageIndexRecord) -> None:
        category = tree.setdefault("categories", {}).setdefault(record.storage_location, {
            "path": str(PurePosixPath(record.target_folder).parent),
            "code_folders": {},
        })
        folder_name = PurePosixPath(record.target_folder).name
        code_folder = category.setdefault("code_folders", {}).setdefault(folder_name, {
            "path": record.target_folder,
            "code": record.code,
            "videos": [],
        })
        videos = code_folder.setdefault("videos", [])
        videos[:] = [video for video in videos if video.get("path") != record.path]
        videos.append({
            "path": record.path,
            "file_name": record.file_name,
            "size": record.size,
            "indexed_at": record.indexed_at,
        })

    def _read_tree_file(self, path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json_atomic(self, path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
```

- [ ] **Step 4: Run store tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/storage/index/store.py backend/tests/test_storage_index_store.py
git commit -m "feat: store storage index as tree"
```

### Task 2: Full And Incremental Index Refresh

**Files:**
- Modify: `backend/app/modules/storage/index/refresh.py`
- Modify: `backend/app/modules/storage/index/router.py`
- Modify: `backend/tests/test_storage_index_refresh.py`
- Modify: `backend/tests/test_storage_index_api.py`

**Interfaces:**
- Consumes: `StorageIndexStore.known_code_folder_paths()`, `write_temp_tree(tree)`, `tree_from_records(...)`.
- Produces:
  - `StorageIndexRefreshService.refresh(config, provider, *, mode: str = "full", force_refresh_mode: str | None = None) -> StorageIndexMetadata`
  - `POST /api/storage/index/refresh` accepts JSON body `{"mode": "full"}` or `{"mode": "incremental"}`.

- [ ] **Step 1: Replace refresh service tests**

Replace `backend/tests/test_storage_index_refresh.py` with:

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


def paths_for(tmp_path):
    return RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )


def test_full_refresh_builds_tree_index(tmp_path):
    paths = paths_for(tmp_path)

    class Provider:
        def __init__(self) -> None:
            self.calls = []

        def list_files(self, path, force_refresh=False):
            self.calls.append(path)
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
        mode="full",
    )

    assert metadata.status == "completed"
    assert metadata.force_refresh_mode == "full"
    assert metadata.video_count == 1
    tree = StorageIndexStore(paths).read_index_tree()
    assert tree["categories"]["巨乳|熟女|BBW"]["code_folders"]["ALDN-206-U"]["videos"][0]["file_name"] == "ALDN-206-U.mp4"
    assert "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U" in provider.calls


def test_incremental_refresh_skips_old_code_folder_videos_and_scans_new_folders(tmp_path):
    paths = paths_for(tmp_path)
    store = StorageIndexStore(paths)

    class FullProvider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies":
                return [RemoteFile("A", "/Movies/A", 0, True)]
            if path == "/Movies/A":
                return [RemoteFile("OLD-001", "/Movies/A/OLD-001", 0, True)]
            if path == "/Movies/A/OLD-001":
                return [RemoteFile("OLD-001.mp4", "/Movies/A/OLD-001/OLD-001.mp4", 500 * 1024 * 1024)]
            return []

    StorageIndexRefreshService(store).refresh(
        {"target_folder": "/Movies", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        FullProvider(),
        mode="full",
    )

    class IncrementalProvider:
        def __init__(self) -> None:
            self.calls = []

        def list_files(self, path, force_refresh=False):
            self.calls.append(path)
            if path == "/Movies":
                return [RemoteFile("A", "/Movies/A", 0, True)]
            if path == "/Movies/A":
                return [
                    RemoteFile("OLD-001", "/Movies/A/OLD-001", 0, True),
                    RemoteFile("NEW-002", "/Movies/A/NEW-002", 0, True),
                ]
            if path == "/Movies/A/NEW-002":
                return [RemoteFile("NEW-002.mp4", "/Movies/A/NEW-002/NEW-002.mp4", 500 * 1024 * 1024)]
            if path == "/Movies/A/OLD-001":
                raise AssertionError("incremental refresh must not scan old code folder videos")
            return []

    provider = IncrementalProvider()
    metadata = StorageIndexRefreshService(store).refresh(
        {"target_folder": "/Movies", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        provider,
        mode="incremental",
    )

    grouped = store.load_index_by_code()
    assert metadata.force_refresh_mode == "incremental"
    assert "OLD-001" in grouped
    assert "NEW-002" in grouped
    assert "/Movies/A/OLD-001" not in provider.calls
```

- [ ] **Step 2: Add refresh API mode test**

Append to `backend/tests/test_storage_index_api.py`:

```python
def test_storage_index_refresh_accepts_incremental_mode(client: TestClient, admin_user, monkeypatch):
    from backend.app.modules.storage.index.models import StorageIndexMetadata

    captured = {}

    class Service:
        def open_provider(self):
            class Context:
                def __enter__(self):
                    return {"target_folder": "/Movies"}, object()
                def __exit__(self, exc_type, exc, tb):
                    return False
            return Context()

    class RefreshService:
        def refresh(self, config, provider, *, mode="full", force_refresh_mode=None):
            captured["mode"] = mode
            return StorageIndexMetadata(target_folder="/Movies", status="completed", force_refresh_mode=mode)

    monkeypatch.setattr("backend.app.modules.storage.index.router.StorageIndexRefreshService", RefreshService)
    monkeypatch.setattr("backend.app.core.dependencies.get_storage_config_service", lambda: Service())

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "incremental"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    assert captured["mode"] == "incremental"
    assert response.json()["data"]["force_refresh_mode"] == "incremental"
```

- [ ] **Step 3: Run tests to verify failures**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_refresh.py backend/tests/test_storage_index_api.py -v
```

Expected: FAIL because refresh mode and tree writing are not implemented yet.

- [ ] **Step 4: Implement refresh modes**

In `backend/app/modules/storage/index/refresh.py`, update `refresh()` to accept `mode` and build records before writing a tree:

```python
    def refresh(self, config: dict, provider, *, mode: str = "full", force_refresh_mode: str | None = None) -> StorageIndexMetadata:
        if mode not in {"full", "incremental"}:
            raise ValueError("mode must be full or incremental")
        force_refresh_mode = force_refresh_mode or mode
        target_root = str(config.get("target_folder") or "/Movies").rstrip("/")
        started_at = datetime.now(timezone.utc).isoformat()
        self.store.write_running_metadata(StorageIndexMetadata(target_folder=target_root, status="running", started_at=started_at, force_refresh_mode=force_refresh_mode))
        errors: list[dict] = []
        category_count = 0
        code_folder_count = 0
        records: list[StorageIndexRecord] = []
        known_code_folders = self.store.known_code_folder_paths() if mode == "incremental" else set()
        existing_records = []
        if mode == "incremental" and known_code_folders:
            for rows in self.store.load_index_by_code().values():
                existing_records.extend(rows)
        self.store.begin_temp_index(target_root)

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
                        video_count=len(existing_records) + len(records),
                        force_refresh_mode=force_refresh_mode,
                        current_path=code_folder,
                        errors=errors,
                    ))
                    if mode == "incremental" and code_folder in known_code_folders:
                        continue
                    files = self._safe_list(provider, code_folder, force_refresh=False, errors=errors)
                    records.extend(self._records_from_files(files, code_folder, category["name"], config, started_at))
        except Exception as exc:
            failed = StorageIndexMetadata(target_folder=target_root, status="failed", started_at=started_at, force_refresh_mode=force_refresh_mode, errors=[{"path": target_root, "error": str(exc)}])
            self.store.write_running_metadata(failed)
            raise

        all_records = [*existing_records, *records] if mode == "incremental" else records
        self.store.write_temp_tree(self.store.tree_from_records(target_root, all_records, indexed_at=started_at))
        completed = StorageIndexMetadata(
            target_folder=target_root,
            status="completed",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            category_count=category_count,
            code_folder_count=code_folder_count,
            video_count=len(all_records),
            force_refresh_mode=force_refresh_mode,
            errors=errors,
        )
        return self.store.finalize_temp_index(completed)
```

- [ ] **Step 5: Implement refresh API body**

In `backend/app/modules/storage/index/router.py`, add:

```python
from pydantic import BaseModel, Field


class StorageIndexRefreshRequest(BaseModel):
    mode: str = Field(default="full", pattern="^(full|incremental)$")
```

Change the endpoint signature:

```python
def refresh_storage_index(
    body: StorageIndexRefreshRequest | None = None,
    _current_user: CurrentUser = None,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
```

Use:

```python
    refresh_mode = body.mode if body is not None else "full"
    with service.open_provider() as (config, provider):
        metadata = StorageIndexRefreshService().refresh(config, provider, mode=refresh_mode)
```

If the optional-body signature causes FastAPI dependency issues, use a required default object instead:

```python
def refresh_storage_index(
    body: StorageIndexRefreshRequest = StorageIndexRefreshRequest(),
    _current_user: CurrentUser = None,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
```

- [ ] **Step 6: Run refresh tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py backend/tests/test_storage_index_refresh.py backend/tests/test_storage_index_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/storage/index/refresh.py backend/app/modules/storage/index/router.py backend/tests/test_storage_index_refresh.py backend/tests/test_storage_index_api.py
git commit -m "feat: add full and incremental storage indexing"
```

### Task 3: Index-Only Bulk Sync And Single-Row CD2 Sync

**Files:**
- Modify: `backend/app/modules/content/movies/storage_sync_service.py`
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes:
  - `sync_movies_storage_statuses(db, user_id, movies, config_service=None)` for index-only sync.
  - `sync_movie_storage_status(...)` for direct CD2 scan.
  - `StorageIndexStore.upsert_records(records, target_folder)`.
- Produces:
  - Existing `POST /api/content/movies/storage-sync` is index-only.
  - New `POST /api/content/movies/{movie_id}/storage-sync/cd2`.

- [ ] **Step 1: Add backend tests**

Append to `backend/tests/test_content_movies_api.py`:

```python
def test_index_storage_sync_fails_without_completed_index(db_session, admin_user, tmp_path, monkeypatch):
    from shared.runtime_config import RuntimeConfigPaths
    from backend.app.modules.storage.index.store import StorageIndexStore
    from backend.app.modules.content.movies.storage_sync_service import sync_movies_storage_statuses
    from shared.database.models.content import Movie

    paths = RuntimeConfigPaths(tmp_path, tmp_path / "database.conf", tmp_path / "redis.conf", tmp_path / "storage.conf", tmp_path / "storage_index.jsonl", tmp_path / "storage_index.meta.json")
    store = StorageIndexStore(paths)
    monkeypatch.setattr("backend.app.modules.content.movies.storage_sync_service.StorageIndexStore", lambda: store)

    class ConfigService:
        def open_provider(self):
            raise AssertionError("index sync must not open CloudDrive2")

    movie = Movie(code="NOINDEX-001", source_name="missing index", storage_summary={})
    db_session.add(movie)
    db_session.commit()

    try:
        sync_movies_storage_statuses(db_session, user_id=str(admin_user.id), movies=[movie], config_service=ConfigService())
    except Exception as exc:
        assert "存储索引不存在或尚未完成" in str(exc)
    else:
        raise AssertionError("missing index must fail")
```

Append a CD2 row-sync API test:

```python
def test_cd2_single_movie_storage_sync_updates_index(client: TestClient, admin_user, tmp_path, monkeypatch):
    from dataclasses import dataclass
    from contextlib import contextmanager
    from shared.runtime_config import RuntimeConfigPaths
    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.storage.index.store import StorageIndexStore
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    paths = RuntimeConfigPaths(tmp_path, tmp_path / "database.conf", tmp_path / "redis.conf", tmp_path / "storage.conf", tmp_path / "storage_index.jsonl", tmp_path / "storage_index.meta.json")
    store = StorageIndexStore(paths)
    monkeypatch.setattr("backend.app.modules.content.movies.storage_sync_service.StorageIndexStore", lambda: store)
    monkeypatch.setattr("backend.app.modules.storage.tasks.events.publish_movie_storage_updated", lambda *args, **kwargs: None)

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/CD2-001":
                return [RemoteFile("CD2-001.mp4", "/Movies/A/CD2-001/CD2-001.mp4", 500 * 1024 * 1024)]
            return []

    class ConfigService:
        @contextmanager
        def open_provider(self):
            yield {"target_folder": "/Movies", "video_extensions": [".mp4"], "minimum_video_size_mb": 100}, Provider()

    monkeypatch.setattr("backend.app.modules.content.movies.router.StorageConfigService", ConfigService, raising=False)
    monkeypatch.setattr("backend.app.modules.content.movies.storage_sync_service.StorageConfigService", ConfigService)

    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    movie = Movie(code="CD2-001", source_name="cd2 sync", source_task_ids=[], storage_summary={})
    session.add_all([crawl_task, movie])
    session.flush()
    movie.source_task_ids = [crawl_task.id]
    movie_id = str(movie.id)
    session.commit()
    session.close()

    response = client.post(f"/api/content/movies/{movie_id}/storage-sync/cd2", headers=headers)

    assert response.status_code == HTTPStatus.OK
    payload = response.json()["data"]
    assert payload["status"] == "stored"
    assert StorageIndexStore(paths).load_index_by_code()["CD2-001"][0].path == "/Movies/A/CD2-001/CD2-001.mp4"
```

- [ ] **Step 2: Run tests to verify failures**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -k "storage_sync" -v
```

Expected: FAIL because index-only missing-index behavior and CD2 row endpoint are not implemented.

- [ ] **Step 3: Make existing sync index-only**

In `backend/app/modules/content/movies/storage_sync_service.py`, remove the single-movie CD2 fallback from `sync_movies_storage_statuses()`:

```python
    results = _sync_movies_from_index(db, movies)
```

Delete this fallback block:

```python
    try:
        results = _sync_movies_from_index(db, movies)
    except StorageIndexMissingError:
        if len(movies) > 1:
            raise
        with service.open_provider() as (config, provider):
            results = [sync_movie_storage_status(db=db, movie=movie, provider=provider, config=config, source="manual_sync") for movie in movies]
```

Keep `config_service` in the signature for backward test compatibility, but do not call it.

- [ ] **Step 4: Add direct CD2 sync helper**

Add to `backend/app/modules/content/movies/storage_sync_service.py`:

```python
def _records_from_locations(movie: Movie, locations: list[dict], indexed_at: str) -> list:
    from backend.app.modules.storage.index.models import StorageIndexRecord

    records = []
    code = str(movie.code or "").upper()
    for location in locations:
        records.append(StorageIndexRecord(
            code=code,
            path=str(location["path"]),
            target_folder=str(location["target_folder"]),
            storage_location=str(location.get("storage_location") or ""),
            file_name=str(location.get("file_name") or ""),
            size=int(location.get("size") or 0),
            indexed_at=indexed_at,
        ))
    return records
```

Add:

```python
def sync_single_movie_storage_status_from_cd2(
    db: Session,
    *,
    user_id: str,
    movie: Movie,
    config_service=None,
) -> dict:
    from datetime import datetime, timezone
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.events import publish_movie_storage_updated

    service = config_service or StorageConfigService()
    with service.open_provider() as (config, provider):
        result = sync_movie_storage_status(db=db, movie=movie, provider=provider, config=config, source="cd2_manual_sync")

    indexed_at = datetime.now(timezone.utc).isoformat()
    records = _records_from_locations(movie, result.locations, indexed_at)
    if records:
        StorageIndexStore().upsert_records(records, target_folder=str(config.get("target_folder") or ""))

    db.commit()
    publish_movie_storage_updated(db, user_id, movie.id)
    return {
        "movie_id": result.movie_id,
        "status": result.status,
        "found_count": result.found_count,
        "checked_targets": result.checked_targets,
        "locations": result.locations,
    }
```

- [ ] **Step 5: Add router endpoint**

In `backend/app/modules/content/movies/router.py`, add:

```python
@router.post("/{movie_id}/storage-sync/cd2")
def sync_single_movie_storage_status_from_cd2(
    movie_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    from backend.app.modules.content.movies.storage_sync_service import (
        sync_single_movie_storage_status_from_cd2 as sync_single_movie_storage_status_from_cd2_service,
    )

    movie = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="影片不存在")
    payload = sync_single_movie_storage_status_from_cd2_service(
        db,
        user_id=str(current_user.id),
        movie=movie,
    )
    return success(data=payload)
```

- [ ] **Step 6: Run backend sync tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -k "storage_sync" -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/content/movies/storage_sync_service.py backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "feat: split index and cd2 movie storage sync"
```

### Task 4: Move Index Controls To Movie List Frontend

**Files:**
- Modify: `frontend/src/api/storage/storageIndex/index.ts`
- Modify: `frontend/src/api/storage/storageIndex/types.ts`
- Modify: `frontend/src/api/movie/index.ts`
- Modify: `frontend/src/pages/storage/config/StorageConfigPage.tsx`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Modify: `frontend/tests/storage-config.ui.test.tsx`
- Modify: `frontend/tests/movie-list.ui.test.tsx`
- Modify: `frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx`

**Interfaces:**
- Consumes:
  - `refreshStorageIndex(mode: 'full' | 'incremental')`.
  - `syncMovieStorageStatus(payload)`.
  - `syncMovieStorageStatusFromCd2(movieId: string)`.
- Produces:
  - Movie-list Dropdown `存储索引` with `全量索引` and `增量索引`.
  - Toolbar button `索引同步`.
  - Row action `CD2同步`.

- [ ] **Step 1: Update frontend tests first**

In `frontend/tests/storage-config.ui.test.tsx`, add to `renders storage config sections from the original project`:

```tsx
    expect(screen.queryByText('存储索引')).not.toBeInTheDocument()
```

In `frontend/tests/movie-list.ui.test.tsx`, update the API mock import to include storage index and CD2 sync:

```ts
import { refreshStorageIndex } from '../src/api/storage/storageIndex'
```

Add mock:

```ts
vi.mock('../src/api/storage/storageIndex', () => ({
  refreshStorageIndex: vi.fn().mockResolvedValue({
    target_folder: '/Movies',
    status: 'completed',
    started_at: '2026-07-10T00:00:00Z',
    completed_at: '2026-07-10T00:01:00Z',
    category_count: 1,
    code_folder_count: 1,
    video_count: 1,
    force_refresh_mode: 'full',
    current_path: null,
    errors: [],
  }),
}))
```

Extend movie API mock:

```ts
  syncMovieStorageStatus: vi.fn().mockResolvedValue({ total: 1, stored_count: 1, not_stored_count: 0, results: [] }),
  syncMovieStorageStatusFromCd2: vi.fn().mockResolvedValue({ movie_id: 'movie-1', status: 'stored', found_count: 1, checked_targets: [], locations: [] }),
```

Add imports:

```ts
  syncMovieStorageStatus,
  syncMovieStorageStatusFromCd2,
```

Add test:

```tsx
  it('renders storage index dropdown and triggers full and incremental index refresh', async () => {
    renderPage()

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /存储索引/ }))
    await userEvent.click(await screen.findByText('全量索引'))
    await userEvent.click(screen.getByRole('button', { name: /存储索引/ }))
    await userEvent.click(await screen.findByText('增量索引'))

    expect(refreshStorageIndex).toHaveBeenNthCalledWith(1, 'full')
    expect(refreshStorageIndex).toHaveBeenNthCalledWith(2, 'incremental')
  })
```

Add test:

```tsx
  it('uses index sync from toolbar and cd2 sync only from row actions', async () => {
    renderPage()

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /索引同步/ }))

    expect(syncMovieStorageStatus).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /CD2同步/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /CD2同步/ }))

    expect(syncMovieStorageStatusFromCd2).toHaveBeenCalledWith('movie-1')
    expect(screen.queryByRole('button', { name: /批量CD2/ })).not.toBeInTheDocument()
  })
```

In `frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx`, add:

```ts
import { syncMovieStorageStatusFromCd2 } from '@/api/movie'
```

Mock it:

```ts
  syncMovieStorageStatusFromCd2: vi.fn().mockResolvedValue({ movie_id: 'movie-1', status: 'stored', found_count: 1, checked_targets: [], locations: [] }),
```

Add:

```ts
  it('calls single movie cd2 sync by movie id', async () => {
    const result = await syncMovieStorageStatusFromCd2('movie-1')
    expect(syncMovieStorageStatusFromCd2).toHaveBeenCalledWith('movie-1')
    expect(result.status).toBe('stored')
  })
```

- [ ] **Step 2: Run frontend tests to verify failures**

Run:

```bash
cd frontend && npm test -- tests/storage-config.ui.test.tsx tests/movie-list.ui.test.tsx src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
```

Expected: FAIL because UI and API functions do not exist yet.

- [ ] **Step 3: Update frontend APIs**

In `frontend/src/api/storage/storageIndex/index.ts`, change:

```ts
export type StorageIndexRefreshMode = 'full' | 'incremental'

export function refreshStorageIndex(mode: StorageIndexRefreshMode): Promise<StorageIndexMetadata> {
  return request.post<StorageIndexMetadata>(`${BASE_URL}/refresh`, { mode })
}
```

In `frontend/src/api/movie/index.ts`, add:

```ts
export function syncMovieStorageStatusFromCd2(movieId: string): Promise<MovieStorageSyncResult> {
  return request.post<MovieStorageSyncResult>(`${BASE_URL}/${movieId}/storage-sync/cd2`)
}
```

- [ ] **Step 4: Remove storage index card from config page**

In `frontend/src/pages/storage/config/StorageConfigPage.tsx`, remove:

```ts
  SyncOutlined,
```

Remove imports from `@/api/storage/storageIndex`.

Remove state:

```ts
  const [indexStatus, setIndexStatus] = useState<StorageIndexMetadata | null>(null)
  const [refreshing, setRefreshing] = useState(false)
```

Remove `loadIndexStatus()`, remove its `useEffect()` call, remove `handleRefreshIndex()`, and delete the final `<Card title="存储索引" ...>...</Card>`.

- [ ] **Step 5: Add row CD2 action to columns**

In `frontend/src/pages/content/movies/components/MovieTable.tsx`, update imports:

```ts
import { Button, Space, Tag } from 'antd'
```

Extend options:

```ts
  onCd2Sync?: (movie: Movie) => void
```

Update function signature:

```ts
export function createMovieColumns({ onViewDetail, onPush, onDelete, onCd2Sync }: MovieColumnsOptions): ColumnsType<Movie> {
```

Increase action width:

```ts
      width: 220,
```

Add before delete:

```tsx
          {onCd2Sync && (
            <Button type="link" size="small" onClick={() => onCd2Sync(record)}>
              CD2同步
            </Button>
          )}
```

- [ ] **Step 6: Wire movie list toolbar and row action**

In `frontend/src/pages/content/movies/MovieListPage.tsx`, update imports:

```ts
import { Button, Dropdown, Space } from 'antd'
import { DatabaseOutlined, DownOutlined, SyncOutlined } from '@ant-design/icons'
import { refreshStorageIndex, type StorageIndexRefreshMode } from '@/api/storage/storageIndex'
import { syncMovieStorageStatusFromCd2 } from '@/api/movie'
```

Add state:

```ts
  const [indexRefreshing, setIndexRefreshing] = useState<StorageIndexRefreshMode | null>(null)
  const [cd2SyncingId, setCd2SyncingId] = useState<string | null>(null)
```

Add handlers:

```ts
  const handleRefreshStorageIndex = useCallback(async (mode: StorageIndexRefreshMode) => {
    setIndexRefreshing(mode)
    try {
      const metadata = await refreshStorageIndex(mode)
      message.success(`${mode === 'full' ? '全量' : '增量'}索引完成：${metadata.video_count} 个视频`)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '刷新索引失败')
    } finally {
      setIndexRefreshing(null)
    }
  }, [message])

  const handleCd2Sync = useCallback(async (movie: Movie) => {
    setCd2SyncingId(movie._id)
    try {
      const result = await syncMovieStorageStatusFromCd2(movie._id)
      message.success(`CD2同步完成：${result.status === 'stored' ? '已存储' : '未存储'}`)
      list.reload()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'CD2同步失败')
    } finally {
      setCd2SyncingId(null)
    }
  }, [list.reload, message])
```

Use `App.useApp()` at the top of `MovieListPage()`:

```ts
  const { message } = App.useApp()
```

Add `App` to the Ant Design import.

Update columns:

```ts
  const columns = useMemo(
    () => createMovieColumns({
      onViewDetail: detail.showDetail,
      onPush: push.openSinglePush,
      onDelete: (movie) => actions.confirmDeleteMovies([movie]),
      onCd2Sync: handleCd2Sync,
      cd2SyncingId,
    }),
    [detail.showDetail, push.openSinglePush, actions.confirmDeleteMovies, handleCd2Sync, cd2SyncingId],
  )
```

If `cd2SyncingId` is added to column options, add it to `MovieColumnsOptions` and use `loading={cd2SyncingId === record._id}` on the CD2 button.

Add Dropdown in `toolbarLeft` before `索引同步`:

```tsx
            <Dropdown
              menu={{
                items: [
                  { key: 'full', label: '全量索引', icon: <DatabaseOutlined /> },
                  { key: 'incremental', label: '增量索引', icon: <SyncOutlined /> },
                ],
                onClick: ({ key }) => void handleRefreshStorageIndex(key as StorageIndexRefreshMode),
              }}
            >
              <Button size="small" loading={indexRefreshing !== null}>
                存储索引 <DownOutlined />
              </Button>
            </Dropdown>
```

Rename toolbar sync button text:

```tsx
              索引同步
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
cd frontend && npm test -- tests/storage-config.ui.test.tsx tests/movie-list.ui.test.tsx src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/storage/storageIndex/index.ts frontend/src/api/storage/storageIndex/types.ts frontend/src/api/movie/index.ts frontend/src/pages/storage/config/StorageConfigPage.tsx frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/components/MovieTable.tsx frontend/tests/storage-config.ui.test.tsx frontend/tests/movie-list.ui.test.tsx frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
git commit -m "feat: move storage index actions to movie list"
```

### Task 5: Full Verification

**Files:**
- Verify all files changed by Tasks 1-4.

**Interfaces:**
- Consumes completed backend and frontend implementation.
- Produces verified build and targeted test results.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_index_store.py \
  backend/tests/test_storage_index_refresh.py \
  backend/tests/test_storage_index_api.py \
  backend/tests/test_content_movies_api.py -k "storage_sync or storage_index" \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd frontend && npm test -- tests/storage-config.ui.test.tsx tests/movie-list.ui.test.tsx src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run backend import smoke test**

Run:

```bash
source .venv/bin/activate
python - <<'PY'
from backend.app.modules.storage.index.store import StorageIndexStore
from backend.app.modules.storage.index.refresh import StorageIndexRefreshService
from backend.app.modules.content.movies.storage_sync_service import sync_single_movie_storage_status_from_cd2

assert StorageIndexStore.TREE_VERSION == 1
assert callable(StorageIndexRefreshService().refresh)
assert callable(sync_single_movie_storage_status_from_cd2)
print("ok")
PY
```

Expected: prints `ok`.

- [ ] **Step 5: Commit verification fixes if needed**

If verification required fixes:

```bash
git add backend/app/modules/storage/index backend/app/modules/content/movies frontend/src/api frontend/src/pages/content/movies frontend/src/pages/storage/config backend/tests frontend/tests frontend/src/pages/content/movies/__tests__
git commit -m "fix: stabilize storage index action verification"
```

If no files changed during verification, do not create an empty commit.

## Self-Review

- Spec coverage: Task 1 implements tree JSON storage; Task 2 implements full/incremental refresh; Task 3 makes normal sync index-only and adds single-row CD2 sync; Task 4 moves UI controls and adds row action; Task 5 verifies the whole path.
- Placeholder scan: no forbidden placeholder wording remains.
- Type consistency: `StorageIndexRecord` remains the compatibility record type, `load_index_by_code()` remains the stable sync interface, and frontend APIs match the backend endpoints.
