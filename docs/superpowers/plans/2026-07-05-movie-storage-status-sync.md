# Movie Storage Status Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a movie-list storage status sync feature with three statuses: `未存储`, `入库中`, and `已存储`.

**Architecture:** Store the canonical movie storage state in `movie.storage_summary.storage_status`, while mirroring it to `last_status` for compatibility with existing filters and realtime payloads. A backend sync service computes target folders from storage config and each movie's `source_task_ids -> CrawlTask.storage_location`, scans CloudDrive2 folders with `provider.list_files`, records each found video path in `storage_summary.locations`, and publishes `movie.storage.updated`. The movie list page adds a sync action: selected rows sync those movies; no selection syncs all movies matching the current filters.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, CloudDrive2 provider gateway, pytest, React 19, TypeScript, Ant Design 6, Vitest.

---

## File Structure

- Create `backend/app/modules/content/movies/storage_status.py`
  - Defines canonical statuses `not_stored`, `storing`, and `stored`.
  - Builds candidate target folders from `target_folder`, `storage_location`, movie code, and known storage suffixes.
  - Scans target folders with `provider.list_files`.
  - Updates `movie.storage_summary`.
- Modify `backend/app/modules/content/movies/router.py`
  - Return `storage_status` in movie payloads.
  - Filter by the new three-state status values.
  - Add `POST /api/content/movies/storage-sync`.
- Modify `backend/app/modules/content/movies/schemas.py`
  - Add request and response models for storage sync.
- Modify `backend/app/modules/storage/tasks/service.py`
  - Set movie status to `storing` when push subtasks are created.
  - Keep existing storage task metadata in `storage_summary`.
- Modify `backend/app/modules/storage/worker/runner.py`
  - After each successful storage subtask completes, rescan the subtask target folders and set the related movie to `stored` only if a video is found.
  - For failed subtasks, set status back to `not_stored` when no stored location is found.
- Modify `backend/app/modules/storage/tasks/events.py`
  - Keep using `movie.storage.updated`; payload includes the updated `storage_summary`.
- Modify backend tests:
  - `backend/tests/test_content_movies_api.py`
  - `backend/tests/test_storage_tasks_api.py`
  - `backend/tests/test_storage_worker_service.py`
- Modify `frontend/src/api/movie/types.ts`
  - Add `MovieStorageStatus`.
  - Add `storage_status` to `Movie`.
  - Tighten `storage_summary` fields.
- Modify `frontend/src/api/movie/index.ts`
  - Add `syncMovieStorageStatus(payload)`.
- Modify movie list frontend:
  - `frontend/src/pages/content/movies/MovieListPage.tsx`
  - `frontend/src/pages/content/movies/components/MovieTable.tsx`
  - `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`
  - `frontend/src/pages/content/movies/hooks/useMovieList.ts`
  - `frontend/src/pages/content/movies/utils/movieFilter.ts`
  - `frontend/src/pages/content/movies/constants/movieOptions.ts`
- Add or update frontend tests near existing movie page tests.

## Behavior Rules

- Canonical storage statuses:
  - `not_stored`: 未存储
  - `storing`: 入库中
  - `stored`: 已存储
- A movie with empty `storage_summary` is displayed and filtered as `not_stored`.
- Clicking single push or batch push immediately marks related movies as `storing`.
- When a related storage subtask finishes successfully, the worker scans the subtask `target_paths`. If any expected video file exists in any target folder, the movie becomes `stored`.
- If a successful subtask finishes but no expected target video exists, the movie becomes `not_stored`.
- Manual sync from the movie list:
  - If one or more rows are selected, only selected movies are synced.
  - If no rows are selected, all movies matching the current filters are synced; pagination is ignored.
  - Sync scans target folders derived from each movie's source crawler tasks and storage config.
  - Each found video file adds one entry to `storage_summary.locations`.
  - Existing location entries are deduplicated by full file path.
- Manual sync does not create storage push tasks and does not move, copy, rename, or delete CloudDrive files.
- A movie becomes `stored` when at least one matching video file is found.
- A movie remains or becomes `not_stored` when no matching video file is found.

## Storage Summary Shape

Use this shape in `movie.storage_summary`:

```json
{
  "storage_status": "stored",
  "last_status": "stored",
  "locations": [
    {
      "path": "/Movies/A/ABC-001/ABC-001-C.mp4",
      "target_folder": "/Movies/A/ABC-001",
      "storage_location": "A",
      "file_name": "ABC-001-C.mp4",
      "size": 524288000,
      "exists": true,
      "source": "manual_sync"
    }
  ],
  "synced_at": "2026-07-05T10:00:00+00:00",
  "last_main_task_id": "main-task-id",
  "last_sub_task_id": "sub-task-id",
  "storage_mode": "single"
}
```

## Task 1: Backend Storage Status Sync Core

**Files:**
- Create: `backend/app/modules/content/movies/storage_status.py`
- Test: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write the failing core helper test**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_sync_movie_storage_status_scans_target_folders_and_records_locations(db_session, admin_user):
    from dataclasses import dataclass

    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.content.movies.storage_status import sync_movie_storage_status
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ABC-001":
                return [
                    RemoteFile("ABC-001-C.mp4", "/Movies/A/ABC-001/ABC-001-C.mp4", 500 * 1024 * 1024),
                ]
            return []

    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    movie = Movie(
        code="abc-001",
        source_name="sync movie",
        source_task_ids=[],
        storage_summary={},
    )
    db_session.add_all([crawl_task, movie])
    db_session.flush()
    movie.source_task_ids = [crawl_task.id]
    db_session.commit()

    result = sync_movie_storage_status(
        db=db_session,
        movie=movie,
        provider=Provider(),
        config={
            "target_folder": "/Movies",
            "video_extensions": [".mp4", ".mkv"],
            "minimum_video_size_mb": 100,
        },
        source="manual_sync",
    )

    assert result.status == "stored"
    assert result.found_count == 1
    assert movie.storage_summary["storage_status"] == "stored"
    assert movie.storage_summary["last_status"] == "stored"
    assert movie.storage_summary["locations"] == [
        {
            "path": "/Movies/A/ABC-001/ABC-001-C.mp4",
            "target_folder": "/Movies/A/ABC-001",
            "storage_location": "A",
            "file_name": "ABC-001-C.mp4",
            "size": 500 * 1024 * 1024,
            "exists": True,
            "source": "manual_sync",
        }
    ]
```

- [ ] **Step 2: Run the helper test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_scans_target_folders_and_records_locations -q
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `backend.app.modules.content.movies.storage_status`.

- [ ] **Step 3: Create the sync helper module**

Create `backend/app/modules/content/movies/storage_status.py` with this content:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie

STORAGE_STATUS_NOT_STORED = "not_stored"
STORAGE_STATUS_STORING = "storing"
STORAGE_STATUS_STORED = "stored"
STORAGE_STATUSES = {
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORING,
    STORAGE_STATUS_STORED,
}
KNOWN_STORAGE_SUFFIXES = ("", "-C", "-U", "-UC")


@dataclass
class MovieStorageSyncResult:
    movie_id: str
    status: str
    found_count: int
    checked_targets: list[str]
    locations: list[dict]


def normalized_movie_storage_status(movie: Movie) -> str:
    summary = dict(movie.storage_summary or {})
    status = str(summary.get("storage_status") or summary.get("last_status") or "")
    if status == "completed":
        return STORAGE_STATUS_STORED
    if status in {"queued", "running", "pending", "waiting_download", "moving"}:
        return STORAGE_STATUS_STORING
    if status in STORAGE_STATUSES:
        return status
    return STORAGE_STATUS_NOT_STORED


def set_movie_storage_status(
    movie: Movie,
    status: str,
    *,
    source: str,
    locations: list[dict] | None = None,
    main_task_id: str | None = None,
    sub_task_id: str | None = None,
    storage_mode: str | None = None,
) -> None:
    if status not in STORAGE_STATUSES:
        raise ValueError(f"Unsupported storage status: {status}")
    summary = dict(movie.storage_summary or {})
    if locations is not None:
        summary["locations"] = _dedupe_locations(locations)
    else:
        summary.setdefault("locations", [])
    summary["storage_status"] = status
    summary["last_status"] = status
    summary["status_source"] = source
    summary["synced_at"] = datetime.now(timezone.utc).isoformat()
    if main_task_id:
        summary["last_main_task_id"] = main_task_id
    if sub_task_id:
        summary["last_sub_task_id"] = sub_task_id
    if storage_mode:
        summary["storage_mode"] = storage_mode
    movie.storage_summary = summary


def build_movie_storage_target_folders(db: Session, movie: Movie, config: dict) -> list[dict]:
    target_root = str(config.get("target_folder") or "/Movies").rstrip("/")
    code = str(movie.code or "").upper()
    if not code:
        return []
    storage_locations = _storage_locations_for_movie(db, movie)
    folders: list[dict] = []
    seen: set[str] = set()
    for storage_location in storage_locations:
        for suffix in KNOWN_STORAGE_SUFFIXES:
            folder_name = f"{code}{suffix}"
            target_folder = f"{target_root}/{storage_location}/{folder_name}"
            if target_folder in seen:
                continue
            seen.add(target_folder)
            folders.append({
                "target_folder": target_folder,
                "storage_location": storage_location,
                "folder_name": folder_name,
            })
    return folders


def sync_movie_storage_status(
    *,
    db: Session,
    movie: Movie,
    provider,
    config: dict,
    source: str,
    target_folders: list[dict] | None = None,
    main_task_id: str | None = None,
    sub_task_id: str | None = None,
    storage_mode: str | None = None,
) -> MovieStorageSyncResult:
    folders = target_folders if target_folders is not None else build_movie_storage_target_folders(db, movie, config)
    checked_targets: list[str] = []
    found_locations: list[dict] = []
    for folder in folders:
        target_folder = str(folder["target_folder"])
        checked_targets.append(target_folder)
        try:
            entries = provider.list_files(target_folder)
        except Exception:
            entries = []
        for entry in entries:
            item = _remote_entry_to_dict(entry, target_folder)
            if _is_matching_video(movie, item, config):
                found_locations.append({
                    "path": item["path"],
                    "target_folder": target_folder,
                    "storage_location": str(folder.get("storage_location") or ""),
                    "file_name": item["name"],
                    "size": item["size"],
                    "exists": True,
                    "source": source,
                })
    status = STORAGE_STATUS_STORED if found_locations else STORAGE_STATUS_NOT_STORED
    set_movie_storage_status(
        movie,
        status,
        source=source,
        locations=found_locations,
        main_task_id=main_task_id,
        sub_task_id=sub_task_id,
        storage_mode=storage_mode,
    )
    return MovieStorageSyncResult(
        movie_id=str(movie.id),
        status=status,
        found_count=len(found_locations),
        checked_targets=checked_targets,
        locations=found_locations,
    )


def target_folder_specs_from_subtask(subtask) -> list[dict]:
    specs: list[dict] = []
    target_locations = list(getattr(subtask, "target_locations", None) or [])
    for index, target_folder in enumerate(list(getattr(subtask, "target_paths", None) or [])):
        specs.append({
            "target_folder": target_folder,
            "storage_location": target_locations[index] if index < len(target_locations) else "",
            "folder_name": PurePosixPath(str(target_folder)).name,
        })
    return specs


def _storage_locations_for_movie(db: Session, movie: Movie) -> list[str]:
    locations: list[str] = []
    for raw_task_id in movie.source_task_ids or []:
        try:
            task_id = raw_task_id if isinstance(raw_task_id, uuid.UUID) else uuid.UUID(str(raw_task_id))
        except (TypeError, ValueError):
            continue
        crawl_task = db.get(CrawlTask, task_id)
        if crawl_task and crawl_task.storage_location and crawl_task.storage_location not in locations:
            locations.append(crawl_task.storage_location)
    return locations


def _remote_entry_to_dict(entry, target_folder: str) -> dict:
    path = getattr(entry, "full_path", "") or getattr(entry, "fullPathName", "")
    name = getattr(entry, "name", "") or PurePosixPath(path).name
    if not path:
        path = str(PurePosixPath(target_folder) / name)
    return {
        "name": name,
        "path": path,
        "size": int(getattr(entry, "size", 0) or 0),
        "is_dir": bool(getattr(entry, "is_directory", False) or getattr(entry, "isDirectory", False)),
    }


def _is_matching_video(movie: Movie, item: dict, config: dict) -> bool:
    if item["is_dir"]:
        return False
    ext = PurePosixPath(item["name"]).suffix.lower()
    allowed_exts = {str(value).lower() for value in config.get("video_extensions", [".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov"])}
    if ext not in allowed_exts:
        return False
    min_bytes = int(config.get("minimum_video_size_mb", 100) or 100) * 1024 * 1024
    if int(item.get("size") or 0) < min_bytes:
        return False
    code = str(movie.code or "").upper()
    return bool(code and item["name"].upper().startswith(code))


def _dedupe_locations(locations: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for location in locations:
        path = str(location.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        deduped.append(location)
    return deduped
```

- [ ] **Step 4: Run the helper test and verify it passes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_scans_target_folders_and_records_locations -q
```

Expected: PASS.

- [ ] **Step 5: Commit the sync core**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/content/movies/storage_status.py backend/tests/test_content_movies_api.py
git commit -m "feat: add movie storage status sync core"
```

Expected: commit succeeds.

## Task 2: Movie Payload And Three-State Filtering

**Files:**
- Modify: `backend/app/modules/content/movies/router.py`
- Test: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write the failing payload and filter test**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_movie_payload_and_filter_use_three_storage_statuses(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    session.add_all([
        Movie(code="SYNC-100", source_url="https://example.test/1", source_name="默认未存储", storage_summary={}),
        Movie(code="SYNC-200", source_url="https://example.test/2", source_name="入库中", storage_summary={"storage_status": "storing"}),
        Movie(code="SYNC-300", source_url="https://example.test/3", source_name="已存储", storage_summary={"storage_status": "stored"}),
    ])
    session.commit()
    session.close()

    not_stored = client.get("/api/content/movies?storage_status=not_stored", headers=headers)
    storing = client.get("/api/content/movies?storage_status=storing", headers=headers)
    stored = client.get("/api/content/movies?storage_status=stored", headers=headers)

    assert [row["code"] for row in not_stored.json()["rows"]] == ["SYNC-100"]
    assert not_stored.json()["rows"][0]["storage_status"] == "not_stored"
    assert [row["code"] for row in storing.json()["rows"]] == ["SYNC-200"]
    assert storing.json()["rows"][0]["storage_status"] == "storing"
    assert [row["code"] for row in stored.json()["rows"]] == ["SYNC-300"]
    assert stored.json()["rows"][0]["storage_status"] == "stored"
```

- [ ] **Step 2: Run the payload and filter test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_movie_payload_and_filter_use_three_storage_statuses -q
```

Expected: FAIL because `storage_status` is not returned in the movie payload.

- [ ] **Step 3: Update movie payload and filter logic**

In `backend/app/modules/content/movies/router.py`, add this import:

```python
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
```

In `_movie_payload()`, before building `payload`, add:

```python
    storage_status = normalized_movie_storage_status(movie)
```

Then add this key to `payload`:

```python
        "storage_status": storage_status,
```

In `_movie_matches_python()`, replace the storage status block:

```python
    last_status = (movie.storage_summary or {}).get("last_status")
    if storage_status == "not_stored":
        return not last_status
    if storage_status and last_status != storage_status:
        return False
```

with:

```python
    normalized_storage_status = normalized_movie_storage_status(movie)
    if storage_status and normalized_storage_status != storage_status:
        return False
```

- [ ] **Step 4: Run affected content movie tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py::test_movie_payload_and_filter_use_three_storage_statuses \
  backend/tests/test_content_movies_api.py::test_list_movies_not_stored_filter \
  backend/tests/test_content_movies_api.py::test_list_movies_supports_original_filter_contract \
  -q
```

Expected: `test_movie_payload_and_filter_use_three_storage_statuses` and `test_list_movies_not_stored_filter` PASS. `test_list_movies_supports_original_filter_contract` FAILS because it still sends the old `completed` status.

- [ ] **Step 5: Update old filter contract test to the new status**

In `backend/tests/test_content_movies_api.py`, in `seed_filter_movies()`, change:

```python
storage_summary={"last_status": "completed"},
```

to:

```python
storage_summary={"storage_status": "stored", "last_status": "stored"},
```

In `test_list_movies_supports_original_filter_contract()`, change:

```python
"storage_status": "completed",
```

to:

```python
"storage_status": "stored",
```

In `test_list_movies_not_stored_filter()`, change the stored movie summary:

```python
storage_summary={"last_status": "completed"}
```

to:

```python
storage_summary={"storage_status": "stored", "last_status": "stored"}
```

- [ ] **Step 6: Run affected content movie tests again**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py::test_movie_payload_and_filter_use_three_storage_statuses \
  backend/tests/test_content_movies_api.py::test_list_movies_not_stored_filter \
  backend/tests/test_content_movies_api.py::test_list_movies_supports_original_filter_contract \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit payload and filter changes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "feat: use three-state movie storage status"
```

Expected: commit succeeds.

## Task 3: Manual Sync API For Selected Or Filtered Movies

**Files:**
- Modify: `backend/app/modules/content/movies/schemas.py`
- Modify: `backend/app/modules/content/movies/router.py`
- Test: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write the failing selected-movie sync API test**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_sync_movie_storage_status_api_syncs_selected_movies(client: TestClient, admin_user, monkeypatch):
    from dataclasses import dataclass

    from backend.app.models.crawl_task import CrawlTask
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/SYNC-API-001":
                return [RemoteFile("SYNC-API-001.mp4", "/Movies/A/SYNC-API-001/SYNC-API-001.mp4", 500 * 1024 * 1024)]
            return []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            self.provider = Provider()

        def list_files(self, path, force_refresh=False):
            return self.provider.list_files(path, force_refresh)

    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    movie = Movie(code="SYNC-API-001", source_name="selected sync", source_task_ids=[], storage_summary={})
    session.add_all([crawl_task, movie])
    session.flush()
    movie.source_task_ids = [crawl_task.id]
    movie_id = str(movie.id)
    session.commit()
    session.close()

    monkeypatch.setattr(
        "backend.app.modules.content.movies.router.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {
                "target_folder": "/Movies",
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            },
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.post(
        "/api/content/movies/storage-sync",
        json={"movie_ids": [movie_id]},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["stored_count"] == 1
    assert payload["not_stored_count"] == 0
    assert payload["results"][0]["movie_id"] == movie_id
    assert payload["results"][0]["status"] == "stored"

    detail = client.get(f"/api/content/movies/{movie_id}", headers=headers).json()["data"]
    assert detail["storage_status"] == "stored"
    assert detail["storage_summary"]["locations"][0]["path"] == "/Movies/A/SYNC-API-001/SYNC-API-001.mp4"
```

- [ ] **Step 2: Write the failing filtered sync API test**

Append this test to `backend/tests/test_content_movies_api.py`:

```python
def test_sync_movie_storage_status_api_uses_filters_when_no_selection(client: TestClient, admin_user, monkeypatch):
    from dataclasses import dataclass

    from backend.app.models.crawl_task import CrawlTask
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/SYNC-FILTER-001":
                return [RemoteFile("SYNC-FILTER-001.mp4", "/Movies/A/SYNC-FILTER-001/SYNC-FILTER-001.mp4", 500 * 1024 * 1024)]
            return []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            self.provider = Provider()

        def list_files(self, path, force_refresh=False):
            return self.provider.list_files(path, force_refresh)

    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    matched = Movie(code="SYNC-FILTER-001", source_name="matched selected name", source_task_ids=[], storage_summary={})
    ignored = Movie(code="SYNC-FILTER-002", source_name="ignored name", source_task_ids=[], storage_summary={})
    session.add_all([crawl_task, matched, ignored])
    session.flush()
    matched.source_task_ids = [crawl_task.id]
    ignored.source_task_ids = [crawl_task.id]
    matched_id = str(matched.id)
    ignored_id = str(ignored.id)
    session.commit()
    session.close()

    monkeypatch.setattr(
        "backend.app.modules.content.movies.router.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {
                "target_folder": "/Movies",
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            },
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.post(
        "/api/content/movies/storage-sync",
        json={"filters": {"search": "matched"}},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["results"][0]["movie_id"] == matched_id
    assert client.get(f"/api/content/movies/{matched_id}", headers=headers).json()["data"]["storage_status"] == "stored"
    assert client.get(f"/api/content/movies/{ignored_id}", headers=headers).json()["data"]["storage_status"] == "not_stored"
```

- [ ] **Step 3: Run the sync API tests and verify they fail**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_api_syncs_selected_movies \
  backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_api_uses_filters_when_no_selection \
  -q
```

Expected: FAIL with `404` for `/api/content/movies/storage-sync`.

- [ ] **Step 4: Add sync request and response schemas**

In `backend/app/modules/content/movies/schemas.py`, add these models after `MovieDetailRead`:

```python
class MovieStorageSyncFilters(BaseModel):
    search: str | None = None
    source_task_id: str | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    actors: str | None = None
    actors_not: str | None = None
    actors_count_min: int | None = None
    actors_count_max: int | None = None
    tags: str | None = None
    tags_not: str | None = None
    director: str | None = None
    director_not: str | None = None
    maker: str | None = None
    maker_not: str | None = None
    series: str | None = None
    series_not: str | None = None
    release_date_from: str | None = None
    release_date_to: str | None = None
    created_at_from: str | None = None
    created_at_to: str | None = None
    storage_status: str | None = None


class MovieStorageSyncRequest(BaseModel):
    movie_ids: list[uuid.UUID] = []
    filters: MovieStorageSyncFilters | None = None


class MovieStorageSyncResponse(BaseModel):
    total: int
    stored_count: int
    not_stored_count: int
    results: list[dict[str, Any]]
```

- [ ] **Step 5: Add the sync endpoint**

In `backend/app/modules/content/movies/router.py`, add these imports:

```python
from backend.app.modules.content.movies.schemas import MovieStorageSyncRequest
from backend.app.modules.content.movies.storage_status import (
    STORAGE_STATUS_STORED,
    sync_movie_storage_status,
)
from backend.app.modules.storage.config.service import StorageConfigService
```

Add this route before `@router.get("/{movie_id}")` so it does not conflict with the path parameter route:

```python
@router.post("/storage-sync")
def sync_movie_storage_statuses(
    body: MovieStorageSyncRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Movie).options(selectinload(Movie.magnets))
    if body.movie_ids:
        movies = query.filter(Movie.id.in_(body.movie_ids)).all()
    else:
        filters = body.filters.model_dump() if body.filters else {}
        rows = query.all()
        movies = [
            movie for movie in rows
            if _movie_matches_python(
                movie,
                search=filters.get("search"),
                source_task_id=filters.get("source_task_id"),
                rating_min=filters.get("rating_min"),
                rating_max=filters.get("rating_max"),
                actors=filters.get("actors"),
                actors_not=filters.get("actors_not"),
                actors_count_min=filters.get("actors_count_min"),
                actors_count_max=filters.get("actors_count_max"),
                tags=filters.get("tags"),
                tags_not=filters.get("tags_not"),
                director=filters.get("director"),
                director_not=filters.get("director_not"),
                maker=filters.get("maker"),
                maker_not=filters.get("maker_not"),
                series=filters.get("series"),
                series_not=filters.get("series_not"),
                release_date_from=filters.get("release_date_from"),
                release_date_to=filters.get("release_date_to"),
                created_at_from=filters.get("created_at_from"),
                created_at_to=filters.get("created_at_to"),
                storage_status=filters.get("storage_status"),
            )
        ]

    config_service = StorageConfigService()
    config = config_service.get_raw_config()
    client = config_service.provider_factory.create(config)
    provider = config_service.gateway_class(client)
    try:
        results = [
            sync_movie_storage_status(
                db=db,
                movie=movie,
                provider=provider,
                config=config,
                source="manual_sync",
            )
            for movie in movies
        ]
        db.commit()
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    from backend.app.modules.storage.tasks.events import publish_movie_storage_updated
    for movie in movies:
        publish_movie_storage_updated(db, str(current_user.id), movie.id)

    stored_count = sum(1 for result in results if result.status == STORAGE_STATUS_STORED)
    return success(data={
        "total": len(results),
        "stored_count": stored_count,
        "not_stored_count": len(results) - stored_count,
        "results": [
            {
                "movie_id": result.movie_id,
                "status": result.status,
                "found_count": result.found_count,
                "checked_targets": result.checked_targets,
                "locations": result.locations,
            }
            for result in results
        ],
    })
```

- [ ] **Step 6: Run the sync API tests and verify they pass**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_api_syncs_selected_movies \
  backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_api_uses_filters_when_no_selection \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit the sync API**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/content/movies/schemas.py backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "feat: add movie storage sync api"
```

Expected: commit succeeds.

## Task 4: Mark Movies As Storing When Push Is Created

**Files:**
- Modify: `backend/app/modules/storage/tasks/service.py`
- Test: `backend/tests/test_storage_tasks_api.py`

- [ ] **Step 1: Write the failing push status test**

Append this test to `backend/tests/test_storage_tasks_api.py`:

```python
def test_storage_push_marks_movie_as_storing(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="store-queue-001")

    response = client.post(
        "/api/storage/tasks/push",
        json={
            "movie_id": str(movie.id),
            "storage_mode": "single",
            "selected_storage_location": "A",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    db_session.refresh(movie)
    assert movie.storage_summary["storage_status"] == "storing"
    assert movie.storage_summary["last_status"] == "storing"
```

- [ ] **Step 2: Run the push status test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_tasks_api.py::test_storage_push_marks_movie_as_storing -q
```

Expected: FAIL because storage push currently writes subtask status such as `queued`.

- [ ] **Step 3: Update storage task service to use canonical status**

In `backend/app/modules/storage/tasks/service.py`, add imports:

```python
from backend.app.modules.content.movies.storage_status import (
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORING,
    set_movie_storage_status,
)
```

Replace `_update_movie_storage_summary()` with:

```python
    def _update_movie_storage_summary(
        self,
        movie: Movie,
        main_task: StorageMainTask,
        subtask: StorageSubTask,
        storage_mode: str,
        user_id: uuid.UUID,
    ) -> None:
        status = STORAGE_STATUS_STORING if subtask.status == "queued" else STORAGE_STATUS_NOT_STORED
        set_movie_storage_status(
            movie,
            status,
            source="storage_push",
            main_task_id=str(main_task.id),
            sub_task_id=str(subtask.id),
            storage_mode=storage_mode,
        )
```

- [ ] **Step 4: Run storage task API tests for push creation**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_tasks_api.py::test_single_push_creates_main_and_subtask \
  backend/tests/test_storage_tasks_api.py::test_batch_push_creates_skipped_subtask_for_missing_magnet \
  backend/tests/test_storage_tasks_api.py::test_storage_push_marks_movie_as_storing \
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit push status update**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/tasks/service.py backend/tests/test_storage_tasks_api.py
git commit -m "feat: mark movies storing on storage push"
```

Expected: commit succeeds.

## Task 5: Sync Movie Status When Storage Worker Finishes A Subtask

**Files:**
- Modify: `backend/app/modules/storage/worker/runner.py`
- Test: `backend/tests/test_storage_worker_service.py`

- [ ] **Step 1: Write the failing worker success sync test**

Append this test to `backend/tests/test_storage_worker_service.py`:

```python
def test_storage_worker_syncs_movie_to_stored_after_successful_subtask(db_session, test_user, monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.storage.worker.runner import process_main_task
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    movie = Movie(code="WORK-001", source_name="worker movie", storage_summary={"storage_status": "storing", "last_status": "storing"})
    db_session.add(movie)
    db_session.flush()
    main = StorageMainTask(
        alias="worker-sync",
        display_name="worker-sync",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        created_by=test_user.id,
        config_snapshot={
            "target_folder": "/Movies",
            "video_extensions": [".mp4"],
            "minimum_video_size_mb": 100,
        },
    )
    db_session.add(main)
    db_session.flush()
    sub = StorageSubTask(
        main_task_id=main.id,
        movie_id=movie.id,
        movie_code="WORK-001",
        movie_title="worker movie",
        status="queued",
        step="prepare",
        storage_mode="single",
        target_locations=["A"],
        target_paths=["/Movies/A/WORK-001"],
    )
    db_session.add(sub)
    db_session.commit()

    class Runtime:
        def should_stop(self, task_id):
            return False

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/WORK-001":
                return [RemoteFile("WORK-001.mp4", "/Movies/A/WORK-001/WORK-001.mp4", 500 * 1024 * 1024)]
            return []

    class Factory:
        def create(self, config):
            return object()

    class ConfigService:
        provider_factory = Factory()

    def fake_gateway(client):
        return Provider()

    def fake_execute(context):
        context.subtask.status = "completed"
        context.subtask.step = "done"
        context.subtask.target_paths = ["/Movies/A/WORK-001"]
        context.subtask.target_locations = ["A"]

    monkeypatch.setattr("shared.integrations.storage_providers.clouddrive2.gateway.CloudDrive2Gateway", fake_gateway, raising=False)
    monkeypatch.setattr("backend.app.modules.storage.worker.steps.execute_subtask_pipeline", fake_execute, raising=False)

    assert process_main_task(Runtime(), Factory(), ConfigService(), str(main.id)) is True

    db_session.expire_all()
    refreshed = db_session.get(Movie, movie.id)
    assert refreshed.storage_summary["storage_status"] == "stored"
    assert refreshed.storage_summary["locations"][0]["path"] == "/Movies/A/WORK-001/WORK-001.mp4"
```

- [ ] **Step 2: Run the worker sync test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py::test_storage_worker_syncs_movie_to_stored_after_successful_subtask -q
```

Expected: FAIL because `process_main_task()` does not sync `movie.storage_summary` after subtask completion.

- [ ] **Step 3: Add worker sync helper inside runner**

In `backend/app/modules/storage/worker/runner.py`, add this helper above `process_main_task()`:

```python
def _sync_movie_storage_after_subtask(db: Session, context) -> None:
    from backend.app.modules.content.movies.storage_status import (
        STORAGE_STATUS_NOT_STORED,
        set_movie_storage_status,
        sync_movie_storage_status,
        target_folder_specs_from_subtask,
    )
    from backend.app.modules.storage.tasks.events import publish_movie_storage_updated
    from shared.database.models.content import Movie

    movie = db.get(Movie, context.subtask.movie_id)
    if movie is None:
        return
    if context.subtask.status == "completed":
        sync_movie_storage_status(
            db=db,
            movie=movie,
            provider=context.provider,
            config=context.config,
            source="storage_worker",
            target_folders=target_folder_specs_from_subtask(context.subtask),
            main_task_id=str(context.main_task.id),
            sub_task_id=str(context.subtask.id),
            storage_mode=context.subtask.storage_mode,
        )
    elif context.subtask.status in {"failed", "skipped"}:
        set_movie_storage_status(
            movie,
            STORAGE_STATUS_NOT_STORED,
            source="storage_worker",
            main_task_id=str(context.main_task.id),
            sub_task_id=str(context.subtask.id),
            storage_mode=context.subtask.storage_mode,
        )
    db.flush()
    publish_movie_storage_updated(db, context.owner_id, movie.id)
```

- [ ] **Step 4: Call the helper after subtask execution**

In `process_main_task()`, after `context.publish_subtask()` in the successful `try` block, add:

```python
                _sync_movie_storage_after_subtask(db, context)
```

In the `except Exception as exc:` block, after `context.publish_subtask()`, add:

```python
                _sync_movie_storage_after_subtask(db, context)
```

- [ ] **Step 5: Run the worker sync test and verify it passes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py::test_storage_worker_syncs_movie_to_stored_after_successful_subtask -q
```

Expected: PASS.

- [ ] **Step 6: Commit worker completion sync**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_service.py
git commit -m "feat: sync movie status after storage worker"
```

Expected: commit succeeds.

## Task 6: Frontend Types, API, And Three-State Display

**Files:**
- Modify: `frontend/src/api/movie/types.ts`
- Modify: `frontend/src/api/movie/index.ts`
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Modify: `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`
- Modify: `frontend/src/pages/content/movies/constants/movieOptions.ts`

- [ ] **Step 1: Add frontend storage status types and API**

In `frontend/src/api/movie/types.ts`, add this type near the top:

```typescript
export type MovieStorageStatus = 'not_stored' | 'storing' | 'stored'
```

Add `storage_status` to `Movie`:

```typescript
  storage_status: MovieStorageStatus
```

Change `storage_summary.last_status` to:

```typescript
    last_status?: MovieStorageStatus
    storage_status?: MovieStorageStatus
```

In `frontend/src/api/movie/index.ts`, add `MovieStorageStatus` to the type import:

```typescript
import type { Movie, MovieListResponse, MovieStorageStatus } from './types'
```

Then add these interfaces and API function after `MovieQueryParams`:

```typescript
export interface MovieStorageSyncPayload {
  movie_ids?: string[]
  filters?: MovieQueryParams
}

export interface MovieStorageSyncResult {
  movie_id: string
  status: MovieStorageStatus
  found_count: number
  checked_targets: string[]
  locations: Record<string, unknown>[]
}

export interface MovieStorageSyncResponse {
  total: number
  stored_count: number
  not_stored_count: number
  results: MovieStorageSyncResult[]
}
```

Add this function after `fetchMovie()`:

```typescript
export function syncMovieStorageStatus(payload: MovieStorageSyncPayload): Promise<MovieStorageSyncResponse> {
  return request.post<MovieStorageSyncResponse>(`${BASE_URL}/storage-sync`, payload)
}
```

- [ ] **Step 2: Update table status display**

In `frontend/src/pages/content/movies/components/MovieTable.tsx`, replace `storageStatusColor` and `storageStatusText` with:

```typescript
const storageStatusColor: Record<string, string> = {
  not_stored: 'default',
  storing: 'processing',
  stored: 'success',
}

const storageStatusText: Record<string, string> = {
  not_stored: '未存储',
  storing: '入库中',
  stored: '已存储',
}
```

Replace the status render body:

```tsx
        const status = record.storage_summary?.last_status
        if (!status) return <Typography.Text type="secondary">-</Typography.Text>
        return <Tag color={storageStatusColor[status]}>{storageStatusText[status] || status}</Tag>
```

with:

```tsx
        const status = record.storage_status || record.storage_summary?.storage_status || 'not_stored'
        return <Tag color={storageStatusColor[status]}>{storageStatusText[status] || status}</Tag>
```

- [ ] **Step 3: Update storage status filter options**

In `frontend/src/pages/content/movies/constants/movieOptions.ts`, replace `MOVIE_STORAGE_STATUS_OPTIONS` with:

```typescript
export const MOVIE_STORAGE_STATUS_OPTIONS: SelectOption[] = [
    {value: "not_stored", label: "未存储"},
    {value: "storing", label: "入库中"},
    {value: "stored", label: "已存储"},
];
```

In `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`, add:

```typescript
import { MOVIE_STORAGE_STATUS_OPTIONS } from "../constants/movieOptions";
```

Then replace the inline `storageStatus` `options={[...]}` array with:

```tsx
options={MOVIE_STORAGE_STATUS_OPTIONS}
```

- [ ] **Step 4: Run frontend typecheck build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Commit frontend status display**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add frontend/src/api/movie/types.ts frontend/src/api/movie/index.ts frontend/src/pages/content/movies/components/MovieTable.tsx frontend/src/pages/content/movies/components/MovieFilterBar.tsx frontend/src/pages/content/movies/constants/movieOptions.ts
git commit -m "feat: show three-state movie storage status"
```

Expected: commit succeeds.

## Task 7: Frontend Movie List Sync Action And Realtime Updates

**Files:**
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Modify: `frontend/src/pages/content/movies/hooks/useMovieList.ts`
- Modify: `frontend/src/realtime/types.ts`
- Test: Add or modify a movie list test under `frontend/src/pages/content/movies/__tests__/`

- [ ] **Step 1: Add a page-level test for sync action payloads**

Create `frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx` with this content:

```typescript
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../MovieListPage'
import { fetchMovieFilterConfig, fetchMovies, syncMovieStorageStatus } from '@/api/movie'

vi.mock('@/api/movie', async () => {
  const actual = await vi.importActual<typeof import('@/api/movie')>('@/api/movie')
  return {
    ...actual,
    fetchMovieFilterConfig: vi.fn().mockResolvedValue({ filters: {} }),
    fetchMovies: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, limit: 20, total_pages: 1 }),
    syncMovieStorageStatus: vi.fn().mockResolvedValue({ total: 0, stored_count: 0, not_stored_count: 0, results: [] }),
    fetchFilters: vi.fn().mockResolvedValue([]),
  }
})

vi.mock('@/api/storage/storageTasks', () => ({
  getNextAlias: vi.fn().mockResolvedValue({ alias: '云存储_测试' }),
  createStoragePush: vi.fn(),
  createBatchStoragePush: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn().mockReturnValue(() => {}),
}))

describe('MovieListPage storage sync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('syncs selected movies when rows are selected', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({
      items: [
        {
          _id: 'movie-1',
          id: 'movie-1',
          code: 'ABC-001',
          source_url: '',
          source_name: 'Movie 1',
          cover: '',
          release_date: null,
          duration: 0,
          director: '',
          maker: '',
          series: '',
          rating: null,
          actors: [],
          tags: [],
          source_task_names: [],
          storage_locations: ['A'],
          marked: false,
          storage_status: 'not_stored',
          storage_summary: {},
          raw_detail: {},
          created_at: null,
          updated_at: null,
        },
      ],
      total: 1,
      page: 1,
      limit: 20,
      total_pages: 1,
    })

    render(<MovieListPage />)

    expect(await screen.findByText('ABC-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /select row/i }))
    fireEvent.click(screen.getByRole('button', { name: '同步存储状态' }))

    await waitFor(() => {
      expect(syncMovieStorageStatus).toHaveBeenCalledWith({ movie_ids: ['movie-1'] })
    })
  })
})
```

- [ ] **Step 2: Run the frontend sync test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
```

Expected: FAIL because the sync button is not implemented.

- [ ] **Step 3: Add realtime movie storage payload typing**

In `frontend/src/realtime/types.ts`, change `MovieStorageUpdatedPayload` to:

```typescript
export type MovieStorageUpdatedPayload = {
  movie_id: string
  storage_summary: Record<string, unknown>
}
```

This keeps the existing shape but makes it explicit for use in the movie list page.

- [ ] **Step 4: Add sync loading state to the movie list hook**

In `frontend/src/pages/content/movies/hooks/useMovieList.ts`, import `syncMovieStorageStatus`:

```typescript
import {fetchMovies, syncMovieStorageStatus} from "@/api/movie";
```

Add state near `loading`:

```typescript
    const [syncingStorage, setSyncingStorage] = useState(false);
```

Add this callback before `return`:

```typescript
    const syncStorageStatus = useCallback(async () => {
        if (!filterParams) return;
        setSyncingStorage(true);
        try {
            const selectedIds = selectedRowKeys.map((key) => String(key));
            const payload = selectedIds.length > 0
                ? {movie_ids: selectedIds}
                : {filters: filterParams};
            const result = await syncMovieStorageStatus(payload);
            message.success(`同步完成：已存储 ${result.stored_count} 条，未存储 ${result.not_stored_count} 条`);
            setSelectedRowKeys([]);
            await loadMovies();
        } catch (e: unknown) {
            message.error(getErrorMessage(e));
        } finally {
            setSyncingStorage(false);
        }
    }, [filterParams, loadMovies, message, selectedRowKeys]);
```

Add `syncingStorage` and `syncStorageStatus` to the returned object:

```typescript
        data, page, pageSize, sortBy, sortOrder, loading, syncingStorage, selectedRowKeys,
```

```typescript
        search, reload, syncStorageStatus, handlePageChange, handleShowSizeChange, handleSortChange, resetSort, updateMovie,
```

- [ ] **Step 5: Add realtime subscription and sync button to movie list page**

In `frontend/src/pages/content/movies/MovieListPage.tsx`, add imports:

```typescript
import { SyncOutlined } from '@ant-design/icons'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { MovieStorageUpdatedPayload, RealtimeEvent } from '@/realtime/types'
```

Add this `useEffect` after the existing URL detail effect:

```typescript
  useEffect(() => {
    connectRealtime()
    const unsubscribe = subscribeRealtime<MovieStorageUpdatedPayload>(
      'movie.storage.updated',
      (event: RealtimeEvent<MovieStorageUpdatedPayload>) => {
        list.updateMovie(event.payload.movie_id, (movie) => ({
          ...movie,
          storage_status: String(event.payload.storage_summary.storage_status || 'not_stored') as Movie['storage_status'],
          storage_summary: {
            ...movie.storage_summary,
            ...event.payload.storage_summary,
          },
        }))
      },
    )
    return unsubscribe
  }, [list.updateMovie])
```

Replace `toolbarLeft` with:

```tsx
        toolbarLeft={(
          <Space>
            {list.selectedRowKeys.length > 0 && (
              <Button type="primary" size="small" onClick={handleBulkPush}>
                批量推送
              </Button>
            )}
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={list.syncingStorage}
              onClick={() => void list.syncStorageStatus()}
            >
              同步存储状态
            </Button>
          </Space>
        )}
```

Also add `Space` to the Ant Design import:

```typescript
import { Button, Space } from 'antd'
```

- [ ] **Step 6: Run the frontend sync test**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
```

Expected: PASS. If the checkbox accessible name differs in the local Ant Design table, change the test click to `document.querySelector('.ant-table-selection-column input')` and assert the same API payload.

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 8: Commit movie list sync UI**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/hooks/useMovieList.ts frontend/src/realtime/types.ts frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
git commit -m "feat: sync movie storage status from list"
```

Expected: commit succeeds.

## Task 8: Full Verification

**Files:**
- Verify backend content movies, storage tasks, and storage worker files.
- Verify frontend movie list, API types, and realtime types.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py \
  backend/tests/test_storage_tasks_api.py \
  backend/tests/test_storage_worker_service.py \
  backend/tests/test_storage_realtime_events.py \
  -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Manual verification**

Start the backend and frontend:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run dev
```

Manual expected results:

```text
1. Movies with empty storage_summary show 未存储.
2. Selecting one or more movies and clicking 同步存储状态 sends only selected ids.
3. Clicking 同步存储状态 with no selection syncs all movies matching current filters.
4. When CloudDrive target folders contain matching videos, the movie row changes to 已存储.
5. Movie detail shows one storage location entry per found video.
6. Clicking 推送 or 批量推送 changes related movie rows to 入库中 after list refresh or realtime update.
7. After a successful storage subtask completes, the related movie is rescanned and becomes 已存储 only when a target video exists.
```

- [ ] **Step 5: Commit verification fixes if needed**

Run this only if verification changes tracked source files:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/content/movies/storage_status.py backend/app/modules/content/movies/router.py backend/app/modules/content/movies/schemas.py backend/app/modules/storage/tasks/service.py backend/app/modules/storage/worker/runner.py backend/tests/test_content_movies_api.py backend/tests/test_storage_tasks_api.py backend/tests/test_storage_worker_service.py frontend/src/api/movie/types.ts frontend/src/api/movie/index.ts frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/components/MovieTable.tsx frontend/src/pages/content/movies/components/MovieFilterBar.tsx frontend/src/pages/content/movies/hooks/useMovieList.ts frontend/src/pages/content/movies/constants/movieOptions.ts frontend/src/realtime/types.ts frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
git commit -m "fix: verify movie storage status sync"
```

Expected: commit succeeds when source files changed during verification.

## Self-Review

- Spec coverage: The plan adds manual sync on the movie list, supports selected movies and filtered-all sync when no selection exists, scans target folders from storage config plus `source_task_ids`, records every found video location, and sets the three requested statuses.
- Push integration: Storage push creation marks movies `storing`, and worker completion rescans target folders to mark `stored` only when files exist.
- Scope control: The plan does not create a separate storage sync task type, does not move files, and does not change CloudDrive storage contents.
- Type consistency: Backend uses `not_stored`, `storing`, and `stored` everywhere; frontend maps them to `未存储`, `入库中`, and `已存储`.
- Verification: Tests cover backend sync helpers, API sync behavior, push status changes, worker success sync, frontend API payloads, and the movie list sync button.

## Execution Options

1. Subagent-Driven (recommended) - Use `superpowers:subagent-driven-development` to dispatch one fresh worker per task, then review between tasks.
2. Inline Execution - Use `superpowers:executing-plans` to execute this plan in the current session with checkpoints.
