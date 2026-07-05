# Storage ListSubFiles Download Polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make normal storage download polling use CloudDrive2 `ListSubFileRequest/GetSubFiles` recursion under `/云下载/storage_子任务id`, so already-downloaded real files are found without `[Search]` virtual paths and later magnets are not attempted after success or skip.

**Architecture:** Add a list-only discovery path in `backend/app/modules/storage/worker/file_finder.py` and keep `SearchFiles + GetOriginalPath` only for explicit recovery. Then update `poll_downloaded_video_files()` in `backend/app/modules/storage/worker/steps.py` to use the list-only helper for normal polling and add a separate recovery helper for CloudDrive2 “任务已存在” cases.

**Tech Stack:** Python 3.12+, FastAPI backend, SQLAlchemy models, pytest, CloudDrive2 provider gateway.

---

## File Structure

- Modify `backend/app/modules/storage/worker/file_finder.py`
  - Keep existing search-based helpers for recovery.
  - Add list-only recursive discovery using `provider.list_files()`.
  - Add visited-path protection and structured `list_sub_files` log context.

- Modify `backend/app/modules/storage/worker/steps.py`
  - Change normal `poll_downloaded_video_files()` to call the list-only helper only.
  - Remove `/云下载` root search from normal polling.
  - Add explicit recovery after submit returns “任务已存在”.

- Modify `backend/tests/test_storage_file_finder_scope.py`
  - Add tests for recursive list discovery, no search calls, virtual path rejection, duplicate real path dedupe, and recursion loop protection.

- Modify `backend/tests/test_storage_worker_pipeline.py`
  - Update polling tests to expect `list_sub_files`.
  - Add tests for no root search during normal polling and recovery only on existing-task submit.

---

### Task 1: Add List-Only File Discovery

**Files:**
- Modify: `backend/app/modules/storage/worker/file_finder.py`
- Test: `backend/tests/test_storage_file_finder_scope.py`

- [ ] **Step 1: Write the failing test for recursive list discovery**

Append this test code to `backend/tests/test_storage_file_finder_scope.py`:

```python
def test_list_subfiles_discovery_accepts_nested_real_video_without_search() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.file_finder import find_listed_video_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False
        is_search_result: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Downloads/storage_sub":
                return [
                    RemoteFile("ACZD-165", "/Downloads/storage_sub/ACZD-165", 0, True),
                    RemoteFile("cover.jpg", "/Downloads/storage_sub/cover.jpg", 1024, False),
                ]
            if path == "/Downloads/storage_sub/ACZD-165":
                return [
                    RemoteFile(
                        "hhd800.com@ACZD-165.mp4",
                        "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                        4770615244,
                        False,
                    )
                ]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

    provider = Provider()

    result = find_listed_video_files(
        provider=provider,
        search_path="/Downloads/storage_sub",
        search_scope="task_download_folder",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert provider.search_calls == []
    assert provider.list_calls == [
        "/Downloads/storage_sub",
        "/Downloads/storage_sub/ACZD-165",
    ]
    assert result.accepted_files == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        }
    ]
    assert result.log_context["search_method"] == "list_sub_files"
    assert result.log_context["search_path"] == "/Downloads/storage_sub"
    assert result.log_context["search_scope"] == "task_download_folder"
    assert result.log_context["raw_entries"] == [
        {
            "current_path": "/Downloads/storage_sub",
            "name": "ACZD-165",
            "path": "/Downloads/storage_sub/ACZD-165",
            "size": 0,
            "is_dir": True,
        },
        {
            "current_path": "/Downloads/storage_sub",
            "name": "cover.jpg",
            "path": "/Downloads/storage_sub/cover.jpg",
            "size": 1024,
            "is_dir": False,
        },
        {
            "current_path": "/Downloads/storage_sub/ACZD-165",
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        },
    ]
    assert result.log_context["rejected_files"] == [
        {
            "name": "cover.jpg",
            "raw_path": "/Downloads/storage_sub/cover.jpg",
            "resolved_path": "/Downloads/storage_sub/cover.jpg",
            "size": 1024,
            "reason": "extension_not_allowed",
        }
    ]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py::test_list_subfiles_discovery_accepts_nested_real_video_without_search -q
```

Expected: FAIL with `ImportError` or `AttributeError` because `find_listed_video_files` does not exist yet.

- [ ] **Step 3: Implement the list-only helper**

Add these functions to `backend/app/modules/storage/worker/file_finder.py` after `_append_candidate()` and before `find_scoped_video_files()`:

```python
def _raw_entry_log(current_path: str, item: dict) -> dict:
    return {
        "current_path": current_path,
        "name": item["name"],
        "path": item["path"],
        "size": int(item.get("size") or 0),
        "is_dir": bool(item.get("is_dir", False)),
    }


def _list_real_files_recursive(
    *,
    provider,
    current_path: str,
    search_root: str,
    config: dict,
    raw_entries: list[dict],
    rejected: list[dict],
    visited: set[str],
    depth: int,
    max_depth: int,
) -> list[dict]:
    normalized_current = str(PurePosixPath(current_path))
    if normalized_current in visited:
        rejected.append({
            "name": PurePosixPath(normalized_current).name,
            "raw_path": normalized_current,
            "resolved_path": normalized_current,
            "size": 0,
            "reason": "recursive_loop",
        })
        return []
    if depth > max_depth:
        rejected.append({
            "name": PurePosixPath(normalized_current).name,
            "raw_path": normalized_current,
            "resolved_path": normalized_current,
            "size": 0,
            "reason": "max_depth_exceeded",
        })
        return []

    visited.add(normalized_current)
    found: list[dict] = []
    try:
        entries = provider.list_files(normalized_current)
    except Exception as exc:
        rejected.append({
            "name": PurePosixPath(normalized_current).name,
            "raw_path": normalized_current,
            "resolved_path": normalized_current,
            "size": 0,
            "reason": "list_error",
            "error": str(exc),
        })
        return found

    for entry in entries:
        item = _raw_file_to_dict(entry)
        raw_entries.append(_raw_entry_log(normalized_current, item))
        if _is_virtual_search_path(item["path"]):
            rejected.append(_rejected_file(item, item, "virtual_search_path"))
            continue
        if not _path_is_under(item["path"], search_root):
            rejected.append(_rejected_file(item, item, "outside_task_download_folder"))
            continue
        if item["is_dir"]:
            found.extend(_list_real_files_recursive(
                provider=provider,
                current_path=item["path"],
                search_root=search_root,
                config=config,
                raw_entries=raw_entries,
                rejected=rejected,
                visited=visited,
                depth=depth + 1,
                max_depth=max_depth,
            ))
            continue
        found.append(item)
    return found


def find_listed_video_files(
    *,
    provider,
    search_path: str,
    search_scope: str,
    movie_code: str,
    task_download_folder: str,
    config: dict,
) -> ScopedSearchResult:
    accepted: list[dict] = []
    rejected: list[dict] = []
    raw_entries: list[dict] = []
    seen: set[str] = set()
    max_depth = int(config.get("download_scan_max_depth", 10) or 10)

    listed_files = _list_real_files_recursive(
        provider=provider,
        current_path=search_path,
        search_root=task_download_folder,
        config=config,
        raw_entries=raw_entries,
        rejected=rejected,
        visited=set(),
        depth=0,
        max_depth=max_depth,
    )

    for listed in listed_files:
        _append_candidate(
            raw_candidate=listed,
            candidate=listed,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
        )

    return ScopedSearchResult(
        accepted_files=accepted,
        log_context={
            "search_path": search_path,
            "current_path": search_path,
            "search_scope": search_scope,
            "search_method": "list_sub_files",
            "raw_entries": raw_entries,
            "accepted_files": accepted,
            "rejected_files": rejected,
        },
    )
```

- [ ] **Step 4: Run the list-only test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py::test_list_subfiles_discovery_accepts_nested_real_video_without_search -q
```

Expected: PASS.

- [ ] **Step 5: Add rejection and recursion protection tests**

Append these tests to `backend/tests/test_storage_file_finder_scope.py`:

```python
def test_list_subfiles_discovery_rejects_virtual_and_duplicate_paths() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.file_finder import find_listed_video_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def list_files(self, path, force_refresh=False):
            return [
                RemoteFile(
                    "hhd800.com@ACZD-165.mp4",
                    "/Downloads/storage_sub/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
                    4770615244,
                    False,
                ),
                RemoteFile(
                    "hhd800.com@ACZD-165.mp4",
                    "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                    4770615244,
                    False,
                ),
                RemoteFile(
                    "hhd800.com@ACZD-165.mp4",
                    "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                    4770615244,
                    False,
                ),
            ]

    result = find_listed_video_files(
        provider=Provider(),
        search_path="/Downloads/storage_sub",
        search_scope="task_download_folder",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert result.accepted_files == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        }
    ]
    assert [item["reason"] for item in result.log_context["rejected_files"]] == [
        "virtual_search_path",
        "duplicate_resolved_path",
    ]


def test_list_subfiles_discovery_stops_recursive_directory_loops() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.file_finder import find_listed_video_files

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
            return [RemoteFile("loop", "/Downloads/storage_sub", 0, True)]

    provider = Provider()

    result = find_listed_video_files(
        provider=provider,
        search_path="/Downloads/storage_sub",
        search_scope="task_download_folder",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert result.accepted_files == []
    assert provider.list_calls == ["/Downloads/storage_sub"]
    assert result.log_context["rejected_files"] == [
        {
            "name": "storage_sub",
            "raw_path": "/Downloads/storage_sub",
            "resolved_path": "/Downloads/storage_sub",
            "size": 0,
            "reason": "recursive_loop",
        }
    ]
```

- [ ] **Step 6: Run file finder tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py -q
```

Expected: PASS for all tests in this file.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add backend/app/modules/storage/worker/file_finder.py backend/tests/test_storage_file_finder_scope.py
git commit -m "fix: add list-only storage file discovery"
```

---

### Task 2: Switch Normal Polling to ListSubFiles Only

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Replace the old root-search polling test with list-only behavior**

In `backend/tests/test_storage_worker_pipeline.py`, replace `test_poll_downloaded_video_files_searches_task_folder_before_download_root` with this test:

```python
def test_poll_downloaded_video_files_uses_list_subfiles_and_does_not_search_root(monkeypatch):
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Downloads/storage_sub":
                return [RemoteFile("ACZD-165", "/Downloads/storage_sub/ACZD-165", 0, True)]
            if path == "/Downloads/storage_sub/ACZD-165":
                return [
                    RemoteFile(
                        "hhd800.com@ACZD-165.mp4",
                        "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                        500 * 1024 * 1024,
                    )
                ]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_max_poll_count": 2,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()

    files = poll_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert [file["path"] for file in files] == [
        "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4"
    ]
    assert context.provider.search_calls == []
    assert context.provider.list_calls == [
        "/Downloads/storage_sub",
        "/Downloads/storage_sub/ACZD-165",
    ]
    assert [log["context"]["search_method"] for log in context.logs if log["message"] == "查找下载文件"] == [
        "list_sub_files",
    ]
```

- [ ] **Step 2: Run the polling test and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_uses_list_subfiles_and_does_not_search_root -q
```

Expected: FAIL because `poll_downloaded_video_files()` still calls search-based `find_scoped_video_files()`.

- [ ] **Step 3: Update `poll_downloaded_video_files()` normal path**

In `backend/app/modules/storage/worker/steps.py`, replace the body of `poll_downloaded_video_files()` with:

```python
def poll_downloaded_video_files(context, search_terms: list[str], task_download_folder: str, download_root: str) -> list[dict]:
    from backend.app.modules.storage.worker.file_finder import find_listed_video_files

    config = context.config
    movie_code = getattr(context.subtask, "movie_code", search_terms[0] if search_terms else "")
    max_poll_count = int(config.get("download_max_poll_count", 10) or 10)
    poll_min = float(config.get("download_poll_interval_min", 5.0) or 0)
    poll_max = float(config.get("download_poll_interval_max", poll_min) or poll_min)
    if poll_max < poll_min:
        poll_max = poll_min

    for poll_index in range(1, max_poll_count + 1):
        result = find_listed_video_files(
            provider=context.provider,
            search_path=task_download_folder,
            search_scope="task_download_folder",
            movie_code=movie_code,
            task_download_folder=task_download_folder,
            config=config,
        )
        result.log_context["poll_index"] = poll_index
        result.log_context["max_poll_count"] = max_poll_count
        _log_search_result(context, result)
        if result.accepted_files:
            return result.accepted_files

        context.log(
            "INFO",
            f"轮询 #{poll_index}: 任务下载目录未发现可用视频文件，等待中",
            {"poll_index": poll_index, "max_poll_count": max_poll_count, "search_path": task_download_folder},
            step="waiting_download",
        )
        if poll_index < max_poll_count:
            time.sleep(random.uniform(poll_min, poll_max))

    context.log(
        "WARNING",
        f"轮询次数超过上限: {max_poll_count}/{max_poll_count}，任务目录未发现可用视频文件，跳过当前磁力",
        {"max_poll_count": max_poll_count, "task_download_folder": task_download_folder},
        step="waiting_download",
    )
    return []
```

`download_root` remains in the signature for existing call sites but is not used in normal polling.

- [ ] **Step 4: Update the old task-folder success test**

In `backend/tests/test_storage_worker_pipeline.py`, update `test_poll_downloaded_video_files_does_not_search_root_when_task_folder_has_file` so its provider uses `list_files()` instead of `search_files()`:

```python
def test_poll_downloaded_video_files_does_not_search_root_when_task_folder_has_file(monkeypatch):
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 500 * 1024 * 1024)]

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_max_poll_count": 3,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }

        def log(self, level, message, context=None, *, step=None, event=None):
            return {}

    context = Context()

    files = poll_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert [file["path"] for file in files] == ["/Downloads/storage_sub/ACZD-165.mp4"]
    assert context.provider.search_calls == []
    assert context.provider.list_calls == ["/Downloads/storage_sub"]
```

- [ ] **Step 5: Add exhaustion test proving root is not searched**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_poll_downloaded_video_files_does_not_search_download_root_after_poll_exhaustion(monkeypatch):
    from backend.app.modules.storage.worker.steps import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_max_poll_count": 2,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()

    files = poll_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert files == []
    assert context.provider.search_calls == []
    assert context.provider.list_calls == ["/Downloads/storage_sub", "/Downloads/storage_sub"]
    assert context.logs[-1]["message"] == "轮询次数超过上限: 2/2，任务目录未发现可用视频文件，跳过当前磁力"
```

- [ ] **Step 6: Run polling tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_uses_list_subfiles_and_does_not_search_root \
  backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_does_not_search_root_when_task_folder_has_file \
  backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_does_not_search_download_root_after_poll_exhaustion \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: use list subfiles for normal storage polling"
```

---

### Task 3: Add Explicit Recovery for Existing CloudDrive2 Tasks

**Files:**
- Modify: `backend/app/modules/storage/worker/file_finder.py`
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Write a failing recovery test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_uses_recovery_only_when_submit_task_exists(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []
            self.renamed: list[tuple[str, str]] = []
            self.moved: list[tuple[list[str], str]] = []
            self.deleted: list[str] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Downloads/storage_sub":
                return [
                    RemoteFile("ACZD-165", "/Downloads/storage_sub/ACZD-165", 0, True),
                ]
            if path == "/Downloads/storage_sub/ACZD-165":
                return [
                    RemoteFile(
                        "hhd800.com@ACZD-165.mp4",
                        "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                        500 * 1024 * 1024,
                    )
                ]
            if path == "/Movies/A/ACZD-165":
                return []
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

        def find_file(self, path):
            return None

        def rename_file(self, old_path, new_name):
            self.renamed.append((old_path, new_name))

        def move_files(self, source_paths, target_folder):
            self.moved.append((source_paths, target_folder))

        def delete_file(self, path):
            self.deleted.append(path)

    class Subtask:
        id = "storage_sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        target_locations = ["A"]
        selected_storage_location = None
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "queued"
        step = "prepare"
        result = {}

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_root_folder": "/Downloads",
                "target_folder": "/Movies",
                "download_max_poll_count": 1,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
                "use_task_subfolder": True,
                "auto_create_target_folder": True,
            }
            self.logs: list[dict] = []

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            return None

    context = Context()

    success = execute_current_magnet_attempt(
        context,
        {
            "id": "m1",
            "magnet_url": "magnet:?xt=urn:btih:first",
            "tags": [],
            "weight": 100,
            "selected": True,
        },
    )

    assert success is True
    assert context.provider.search_calls == []
    assert "/Downloads/storage_sub" in context.provider.list_calls
    assert context.provider.renamed == [
        ("/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4", "ACZD-165.mp4")
    ]
    assert context.provider.moved == [
        (["/Downloads/storage_sub/ACZD-165/ACZD-165.mp4"], "/Movies/A/ACZD-165")
    ]
    assert any(log["context"].get("search_scope") == "recovery_task_download_folder" for log in context.logs)
```

- [ ] **Step 2: Run the recovery test and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_uses_recovery_only_when_submit_task_exists -q
```

Expected: FAIL because existing-task submit currently falls through to normal polling and does not produce `recovery_task_download_folder` log context.

- [ ] **Step 3: Add recovery helper in `file_finder.py`**

Add this function after `find_listed_video_files()`:

```python
def find_recovery_video_files(
    *,
    provider,
    search_terms: list[str],
    task_download_folder: str,
    download_root: str,
    movie_code: str,
    config: dict,
) -> ScopedSearchResult:
    task_result = find_listed_video_files(
        provider=provider,
        search_path=task_download_folder,
        search_scope="recovery_task_download_folder",
        movie_code=movie_code,
        task_download_folder=task_download_folder,
        config=config,
    )
    if task_result.accepted_files:
        return task_result

    root_result = find_scoped_video_files(
        provider=provider,
        search_terms=search_terms,
        search_path=download_root,
        search_scope="recovery_download_root",
        movie_code=movie_code,
        task_download_folder=download_root,
        config=config,
    )
    return root_result
```

This keeps `SearchFiles + GetOriginalPath` out of normal polling and allows it only in the explicit recovery flow.

- [ ] **Step 4: Update `execute_current_magnet_attempt()` to call recovery explicitly**

In `backend/app/modules/storage/worker/steps.py`, add this helper near `_log_search_result()`:

```python
def recover_existing_downloaded_video_files(context, search_terms: list[str], task_download_folder: str, download_root: str) -> list[dict]:
    from backend.app.modules.storage.worker.file_finder import find_recovery_video_files

    movie_code = getattr(context.subtask, "movie_code", search_terms[0] if search_terms else "")
    result = find_recovery_video_files(
        provider=context.provider,
        search_terms=search_terms,
        task_download_folder=task_download_folder,
        download_root=download_root,
        movie_code=movie_code,
        config=context.config,
    )
    result.log_context["recovery_reason"] = "submit_task_exists"
    _log_search_result(context, result)
    return result.accepted_files
```

Then change `execute_current_magnet_attempt()` around the submit block:

```python
    submit_task_exists = False
    try:
        context.log(
            "INFO",
            "准备提交磁力到 CloudDrive2",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder},
            step="submit_magnet",
        )
        ensure_directory_chain(provider, download_folder)
        result = provider.submit_offline_download(magnet_url, download_folder)
        context.log(
            "INFO",
            "磁力链接已提交",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder, "result_paths": getattr(result, "result_paths", [])},
            step="submit_magnet",
        )
    except Exception as exc:
        message = str(exc)
        if "10008" not in message and "任务已存在" not in message:
            context.log("ERROR", f"提交磁力失败: {exc}", {"magnet_id": magnet.get("id")}, step="submit_magnet")
            return False
        submit_task_exists = True
        context.log("WARNING", "磁力链接已存在 (code 10008)，搜索现有下载中", {"magnet_id": magnet.get("id")}, step="submit_magnet")
```

Then change the download wait block:

```python
    context.set_step("waiting_download")
    search_terms = [subtask.movie_code]
    if submit_task_exists:
        found_files = recover_existing_downloaded_video_files(
            context,
            search_terms=search_terms,
            task_download_folder=download_folder,
            download_root=download_root,
        )
    else:
        found_files = poll_downloaded_video_files(
            context,
            search_terms=search_terms,
            task_download_folder=download_folder,
            download_root=download_root,
        )
```

- [ ] **Step 5: Run the recovery test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_uses_recovery_only_when_submit_task_exists -q
```

Expected: PASS.

- [ ] **Step 6: Add recovery root-search test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_recover_existing_downloaded_video_files_searches_root_after_task_folder_empty() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import recover_existing_downloaded_video_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False
        is_search_result: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []
            self.original_path_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return [
                RemoteFile(
                    "hhd800.com@ACZD-165.mp4",
                    "/Downloads/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
                    500 * 1024 * 1024,
                    False,
                    True,
                )
            ]

        def get_original_path(self, path):
            self.original_path_calls.append(path)
            return "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4"

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()

    files = recover_existing_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert files == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 500 * 1024 * 1024,
            "is_dir": False,
        }
    ]
    assert context.provider.list_calls == ["/Downloads/storage_sub"]
    assert context.provider.search_calls == [("ACZD-165", "/Downloads")]
    assert context.provider.original_path_calls == ["/Downloads/[Search]ACZD-165/hhd800.com@ACZD-165.mp4"]
    assert context.logs[0]["context"]["search_scope"] == "recovery_download_root"
    assert context.logs[0]["context"]["original_path_results"] == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "raw_path": "/Downloads/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
            "original_path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
        }
    ]
```

- [ ] **Step 7: Run recovery tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_uses_recovery_only_when_submit_task_exists \
  backend/tests/test_storage_worker_pipeline.py::test_recover_existing_downloaded_video_files_searches_root_after_task_folder_empty \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add backend/app/modules/storage/worker/file_finder.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: isolate storage recovery search"
```

---

### Task 4: Run Full Storage Worker Verification

**Files:**
- Verify only; no source edits expected.

- [ ] **Step 1: Run focused storage tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_file_finder_scope.py \
  backend/tests/test_storage_worker_pipeline.py \
  backend/tests/test_storage_worker_service.py \
  backend/tests/test_storage_runtime_redis.py \
  backend/tests/test_storage_tasks_api.py \
  -q
```

Expected: PASS. Existing `StarletteDeprecationWarning` may appear and does not block this plan.

- [ ] **Step 2: Inspect logs-related assertions manually**

Run:

```bash
rg -n "\"search_method\": \"search_files\"|search_scope.*download_root|original_path_results|list_sub_files" backend/tests backend/app/modules/storage/worker
```

Expected:

- Normal polling tests assert `list_sub_files`.
- Recovery tests assert `recovery_download_root` and `original_path_results`.
- No normal polling test expects `download_root`.

- [ ] **Step 3: Commit verification-only updates if any test names or assertions were adjusted**

If Task 4 required no edits, do not commit. If assertion-only edits were necessary, run:

```bash
git add backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify storage list subfiles polling"
```

---

## Self-Review

Spec coverage:

- Normal polling uses `ListSubFileRequest/GetSubFiles`: Task 1 and Task 2.
- Polling searches only `/云下载/storage_子任务id`: Task 2.
- Recursive child directory traversal with visited-path protection: Task 1.
- `SearchFiles` not called during normal polling: Task 1 and Task 2 tests assert `search_calls == []`.
- Poll success stops polling and continues normal pipeline: Task 2 keeps `poll_downloaded_video_files()` returning immediately on accepted files; existing pipeline tests cover later magnet stop after success.
- Poll exhaustion starts next magnet without root search: Task 2 exhaustion test.
- Recovery search is separate and uses `GetOriginalPath`: Task 3.
- Virtual paths never accepted: Task 1 and existing `scan_found_files` tests.
- Logs show `search_method=list_sub_files`, `raw_entries`, accepted and rejected files: Task 1 and Task 2.
- `/115open/115open/...` path issue is prevented by keeping normal polling on real list paths and confining search results to recovery: Task 2 and Task 3.

No incomplete markers remain. Function names introduced in the plan are consistent: `find_listed_video_files`, `find_recovery_video_files`, and `recover_existing_downloaded_video_files`.
