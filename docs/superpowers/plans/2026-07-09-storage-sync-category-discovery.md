# Storage Sync Category Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make manual movie storage status sync detect videos manually placed one category directory below the configured CloudDrive target root.

**Architecture:** Keep exact target-folder scanning as the first pass. Add a bounded fallback in the storage scan module that lists immediate child category directories under `config["target_folder"]`, probes known code-folder suffixes, and reuses the existing video validation before returning discovered locations in the current result shape.

**Tech Stack:** Python 3.12+, FastAPI backend, SQLAlchemy models, pytest tests, existing CloudDrive2 provider gateway interface.

## Global Constraints

- Preserve existing exact-folder sync behavior before fallback discovery.
- Fallback discovery scans only one category directory below `target_folder`.
- Do not change storage task download, move, copy, rename, or target planning behavior.
- Do not add frontend configuration or arbitrary recursive scan depth.
- Use existing video validation: configured extensions, minimum video size, and movie-code filename prefix.
- CloudDrive listing failures stay non-fatal and skip only the failing path.

---

## File Structure

- Modify `backend/app/modules/content/movies/storage_scan.py`: add bounded category discovery helpers and invoke them only when exact scanning finds no matching videos.
- Modify `backend/tests/test_content_movies_api.py`: add a regression test for `/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4` discovery while preserving existing sync tests.

No new runtime modules are needed. The scan module already owns provider listing, entry normalization, video matching, checked target collection, and found location construction.

### Task 1: Category Fallback Discovery

**Files:**
- Modify: `backend/app/modules/content/movies/storage_scan.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes: `scan_movie_storage_locations(movie: Movie, provider, config: dict, folders: list[dict], source: str) -> tuple[list[str], list[dict]]`
- Consumes: `is_matching_video(movie: Movie, item: dict, config: dict) -> bool`
- Produces: unchanged `scan_movie_storage_locations(...)` signature and result shape.
- Produces: helper `_scan_category_fallback(movie: Movie, provider, config: dict, source: str, checked_targets: list[str]) -> list[dict]`

- [ ] **Step 1: Write the failing regression test**

Add this test after `test_sync_movie_storage_status_scans_target_folders_and_records_locations` in `backend/tests/test_content_movies_api.py`:

```python
def test_sync_movie_storage_status_discovers_manual_category_folder(db_session, admin_user):
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
            if path == "/嘿嘿/日本":
                return [
                    RemoteFile("巨乳|熟女|BBW", "/嘿嘿/日本/巨乳|熟女|BBW", 0, True),
                    RemoteFile("loose.txt", "/嘿嘿/日本/loose.txt", 1, False),
                ]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U":
                return [
                    RemoteFile(
                        "ALDN-206-U.mp4",
                        "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4",
                        500 * 1024 * 1024,
                    ),
                ]
            return []

    provider = Provider()
    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    movie = Movie(
        code="ALDN-206",
        source_name="manual category sync movie",
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
        provider=provider,
        config={
            "target_folder": "/嘿嘿/日本",
            "video_extensions": [".mp4", ".mkv"],
            "minimum_video_size_mb": 100,
        },
        source="manual_sync",
    )

    assert result.status == "stored"
    assert result.found_count == 1
    assert "/嘿嘿/日本/A/ALDN-206" in result.checked_targets
    assert "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U" in result.checked_targets
    assert movie.storage_summary["storage_status"] == "stored"
    assert movie.storage_summary["locations"] == [
        {
            "path": "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4",
            "target_folder": "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U",
            "storage_location": "巨乳|熟女|BBW",
            "file_name": "ALDN-206-U.mp4",
            "size": 500 * 1024 * 1024,
            "exists": True,
            "source": "manual_sync",
        }
    ]
```

- [ ] **Step 2: Run the failing regression test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_discovers_manual_category_folder -v
```

Expected: FAIL because `result.status` is `not_stored` and the fallback category folder is not scanned.

- [ ] **Step 3: Add fallback discovery helpers**

In `backend/app/modules/content/movies/storage_scan.py`, replace the file with this implementation:

```python
from __future__ import annotations

from pathlib import PurePosixPath

from shared.database.models.content import Movie

KNOWN_STORAGE_SUFFIXES = ("", "-C", "-U", "-UC")


def remote_entry_to_dict(entry, target_folder: str) -> dict:
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


def is_matching_video(movie: Movie, item: dict, config: dict) -> bool:
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


def scan_movie_storage_locations(
    movie: Movie,
    provider,
    config: dict,
    folders: list[dict],
    source: str,
) -> tuple[list[str], list[dict]]:
    checked_targets: list[str] = []
    found_locations: list[dict] = []
    for folder in folders:
        target_folder = str(folder["target_folder"])
        checked_targets.append(target_folder)
        try:
            entries = provider.list_files(target_folder)
        except Exception:
            entries = []
        found_locations.extend(
            _matching_locations_from_entries(
                movie=movie,
                entries=entries,
                config=config,
                target_folder=target_folder,
                storage_location=str(folder.get("storage_location") or ""),
                source=source,
            )
        )
    if not found_locations:
        found_locations.extend(_scan_category_fallback(movie, provider, config, source, checked_targets))
    return checked_targets, found_locations


def _scan_category_fallback(
    movie: Movie,
    provider,
    config: dict,
    source: str,
    checked_targets: list[str],
) -> list[dict]:
    target_root = str(config.get("target_folder") or "").rstrip("/")
    code = str(movie.code or "").upper()
    if not target_root or not code:
        return []

    try:
        root_entries = provider.list_files(target_root)
    except Exception:
        return []

    found_locations: list[dict] = []
    for entry in root_entries:
        category = remote_entry_to_dict(entry, target_root)
        if not category["is_dir"] or not category["name"]:
            continue
        category_folder = category["path"] or str(PurePosixPath(target_root) / category["name"])
        for suffix in KNOWN_STORAGE_SUFFIXES:
            code_folder_name = f"{code}{suffix}"
            code_folder = str(PurePosixPath(category_folder) / code_folder_name)
            checked_targets.append(code_folder)
            try:
                entries = provider.list_files(code_folder)
            except Exception:
                entries = []
            found_locations.extend(
                _matching_locations_from_entries(
                    movie=movie,
                    entries=entries,
                    config=config,
                    target_folder=code_folder,
                    storage_location=category["name"],
                    source=source,
                )
            )
    return found_locations


def _matching_locations_from_entries(
    *,
    movie: Movie,
    entries,
    config: dict,
    target_folder: str,
    storage_location: str,
    source: str,
) -> list[dict]:
    locations: list[dict] = []
    for entry in entries:
        item = remote_entry_to_dict(entry, target_folder)
        if is_matching_video(movie, item, config):
            locations.append({
                "path": item["path"],
                "target_folder": target_folder,
                "storage_location": storage_location,
                "file_name": item["name"],
                "size": item["size"],
                "exists": True,
                "source": source,
            })
    return locations
```

- [ ] **Step 4: Run the focused regression test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_discovers_manual_category_folder -v
```

Expected: PASS.

- [ ] **Step 5: Run adjacent storage sync tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_scans_target_folders_and_records_locations backend/tests/test_content_movies_api.py::test_storage_scan_ignores_small_non_video_and_provider_errors backend/tests/test_content_movies_api.py::test_sync_movie_storage_status_discovers_manual_category_folder -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Run broader backend storage-related tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py backend/tests/test_storage_worker_service.py backend/tests/test_storage_worker_target_files.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit implementation**

Run:

```bash
git add backend/app/modules/content/movies/storage_scan.py backend/tests/test_content_movies_api.py
git commit -m "fix: discover category folders during storage sync"
```

Expected: commit succeeds with only the implementation and regression test staged.
