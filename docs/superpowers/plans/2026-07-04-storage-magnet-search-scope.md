# Storage Magnet Search Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make storage magnet processing search the current task folder first, search the download root only after that fails, log every search decision, and keep magnet submissions strictly sequential.

**Architecture:** Keep the current storage worker pipeline and Redis-backed main task execution. Move search filtering and audit payload creation into `backend/app/modules/storage/worker/file_finder.py`, then have `backend/app/modules/storage/worker/steps.py` call it in a two-stage poll: task download folder first, download root recovery second. Each search batch is written through the existing subtask JSONL logger via `context.log`.

**Tech Stack:** Python 3.12, FastAPI backend modules, SQLAlchemy storage task models, CloudDrive2 gateway abstraction, JSONL storage task logs, Pytest.

---

## Source Spec

Approved design: `docs/superpowers/specs/2026-07-04-storage-magnet-search-scope-design.md`

The implementation must preserve these decisions:

- Submit one magnet and finish its polling and pipeline before submitting the next magnet.
- Search `/云下载/storage_子任务id` first.
- Search `/云下载` only after task-folder polling reaches `download_max_poll_count`.
- Log search term, search path, search scope, search method, raw results, resolved results, accepted files, and rejected files.
- Reject root search results that belong to a different movie code.

## File Structure

- Modify `backend/app/modules/storage/worker/file_finder.py`: Add scoped search helpers, audit payloads, movie-code filtering, task-folder filtering, and rejected-file reasons.
- Modify `backend/app/modules/storage/worker/steps.py`: Change polling to task-folder-first and root-recovery-second; write search audit logs; remove target folders from download search scope.
- Create `backend/tests/test_storage_file_finder_scope.py`: Unit tests for scoped search filtering and audit payloads.
- Modify `backend/tests/test_storage_worker_pipeline.py`: Integration-style tests for poll order and magnet loop sequencing.

## Task 1: Scoped Search Unit Tests

**Files:**
- Create: `backend/tests/test_storage_file_finder_scope.py`

- [ ] **Step 1: Write failing tests for task-folder scoped search and logs**

Create `backend/tests/test_storage_file_finder_scope.py` with:

```python
from dataclasses import dataclass


@dataclass
class FakeRemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False
    is_search_result: bool = False


class ScopedSearchProvider:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str]] = []
        self.list_calls: list[str] = []
        self.original_paths = {
            "/Search/ACZD-165.mp4": "/Downloads/storage_sub/ACZD-165.mp4",
            "/Search/MIDA-628.mp4": "/Downloads/storage_old/MIDA-628.mp4",
        }

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        self.search_calls.append((term, path))
        return [
            FakeRemoteFile("ACZD-165.mp4", "/Search/ACZD-165.mp4", 500 * 1024 * 1024, False, True),
            FakeRemoteFile("MIDA-628.mp4", "/Search/MIDA-628.mp4", 500 * 1024 * 1024, False, True),
            FakeRemoteFile("ACZD-165.txt", "/Downloads/storage_sub/ACZD-165.txt", 1024, False, False),
        ]

    def get_original_path(self, path):
        return self.original_paths.get(path, "")

    def list_files(self, path, force_refresh=False):
        self.list_calls.append(path)
        return []


def test_scoped_search_logs_raw_resolved_accepted_and_rejected_files() -> None:
    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    provider = ScopedSearchProvider()

    result = find_scoped_video_files(
        provider=provider,
        search_terms=["ACZD-165"],
        search_path="/Downloads/storage_sub",
        search_scope="task_download_folder",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert provider.search_calls == [("ACZD-165", "/Downloads/storage_sub")]
    assert [file["path"] for file in result.accepted_files] == ["/Downloads/storage_sub/ACZD-165.mp4"]
    assert result.log_context["search_term"] == "ACZD-165"
    assert result.log_context["search_path"] == "/Downloads/storage_sub"
    assert result.log_context["search_scope"] == "task_download_folder"
    assert result.log_context["search_method"] == "search_files"
    assert result.log_context["raw_results"] == [
        {"name": "ACZD-165.mp4", "path": "/Search/ACZD-165.mp4", "size": 524288000},
        {"name": "MIDA-628.mp4", "path": "/Search/MIDA-628.mp4", "size": 524288000},
        {"name": "ACZD-165.txt", "path": "/Downloads/storage_sub/ACZD-165.txt", "size": 1024},
    ]
    assert result.log_context["resolved_results"] == [
        {"name": "ACZD-165.mp4", "path": "/Downloads/storage_sub/ACZD-165.mp4", "size": 524288000},
        {"name": "MIDA-628.mp4", "path": "/Downloads/storage_old/MIDA-628.mp4", "size": 524288000},
        {"name": "ACZD-165.txt", "path": "/Downloads/storage_sub/ACZD-165.txt", "size": 1024},
    ]
    assert result.log_context["accepted_files"] == [
        {"name": "ACZD-165.mp4", "path": "/Downloads/storage_sub/ACZD-165.mp4", "size": 524288000}
    ]
    assert result.log_context["rejected_files"] == [
        {
            "name": "MIDA-628.mp4",
            "path": "/Downloads/storage_old/MIDA-628.mp4",
            "size": 524288000,
            "reason": "movie_code_mismatch",
        },
        {
            "name": "ACZD-165.txt",
            "path": "/Downloads/storage_sub/ACZD-165.txt",
            "size": 1024,
            "reason": "extension_not_allowed",
        },
    ]
```

- [ ] **Step 2: Write failing tests for root recovery rejecting other movie codes**

Append to `backend/tests/test_storage_file_finder_scope.py`:

```python
class RootSearchProvider:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str]] = []
        self.original_paths = {
            "/Search/CHERD-105.mp4": "/Downloads/storage_old/CHERD-105/CHERD-105.mp4",
            "/Search/ACZD-165.mp4": "/Downloads/storage_other/ACZD-165/ACZD-165.mp4",
        }

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        self.search_calls.append((term, path))
        return [
            FakeRemoteFile("CHERD-105.mp4", "/Search/CHERD-105.mp4", 900 * 1024 * 1024, False, True),
            FakeRemoteFile("ACZD-165.mp4", "/Search/ACZD-165.mp4", 900 * 1024 * 1024, False, True),
        ]

    def get_original_path(self, path):
        return self.original_paths.get(path, "")

    def list_files(self, path, force_refresh=False):
        return []


def test_root_recovery_rejects_other_movie_codes() -> None:
    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    provider = RootSearchProvider()

    result = find_scoped_video_files(
        provider=provider,
        search_terms=["ACZD-165"],
        search_path="/Downloads",
        search_scope="download_root",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert provider.search_calls == [("ACZD-165", "/Downloads")]
    assert [file["path"] for file in result.accepted_files] == [
        "/Downloads/storage_other/ACZD-165/ACZD-165.mp4"
    ]
    assert result.log_context["rejected_files"] == [
        {
            "name": "CHERD-105.mp4",
            "path": "/Downloads/storage_old/CHERD-105/CHERD-105.mp4",
            "size": 943718400,
            "reason": "movie_code_mismatch",
        }
    ]
```

- [ ] **Step 3: Run the new tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py -v
```

Expected: FAIL because `find_scoped_video_files` does not exist.

- [ ] **Step 4: Commit failing scoped search tests**

```bash
git add backend/tests/test_storage_file_finder_scope.py
git commit -m "test: cover scoped storage file search"
```

## Task 2: Implement Scoped Search and Audit Payloads

**Files:**
- Modify: `backend/app/modules/storage/worker/file_finder.py`
- Test: `backend/tests/test_storage_file_finder_scope.py`

- [ ] **Step 1: Add dataclasses and result conversion helpers**

In `backend/app/modules/storage/worker/file_finder.py`, add these imports:

```python
from dataclasses import dataclass
```

Add these dataclasses below the imports:

```python
@dataclass
class ScopedSearchResult:
    accepted_files: list[dict]
    log_context: dict
```

Replace `_file_to_dict` with:

```python
def _raw_file_to_dict(file_obj) -> dict:
    path = getattr(file_obj, "full_path", "") or getattr(file_obj, "fullPathName", "")
    return {
        "name": getattr(file_obj, "name", "") or PurePosixPath(path).name,
        "path": path,
        "size": int(getattr(file_obj, "size", 0) or 0),
        "is_dir": bool(getattr(file_obj, "is_directory", False) or getattr(file_obj, "isDirectory", False)),
    }


def _file_to_dict(provider, file_obj) -> dict:
    item = _raw_file_to_dict(file_obj)
    if getattr(file_obj, "is_search_result", False) or getattr(file_obj, "isSearchResult", False):
        original = provider.get_original_path(item["path"])
        if original:
            item["path"] = original
            item["name"] = PurePosixPath(original).name
    return item
```

- [ ] **Step 2: Add filtering helpers**

Add below `_is_usable_video`:

```python
def _path_is_under(path: str, folder: str) -> bool:
    normalized_path = str(PurePosixPath(path))
    normalized_folder = str(PurePosixPath(folder))
    return normalized_path == normalized_folder or normalized_path.startswith(f"{normalized_folder}/")


def _movie_code_matches(file_dict: dict, movie_code: str) -> bool:
    normalized_code = movie_code.upper()
    haystack = f"{file_dict.get('name', '')} {file_dict.get('path', '')}".upper()
    return normalized_code in haystack


def _rejection_reason(file_dict: dict, *, config: dict, movie_code: str, search_scope: str, task_download_folder: str) -> str | None:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    if ext not in {str(item).lower() for item in config.get("video_extensions", [])}:
        return "extension_not_allowed"
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    if int(file_dict.get("size") or 0) < min_bytes:
        return "below_minimum_size"
    if not _movie_code_matches(file_dict, movie_code):
        return "movie_code_mismatch"
    if search_scope == "task_download_folder" and not _path_is_under(file_dict["path"], task_download_folder):
        return "outside_task_download_folder"
    return None
```

- [ ] **Step 3: Add scoped search implementation**

Add below `_recursive_list`:

```python
def _append_candidate(
    *,
    candidate: dict,
    accepted: list[dict],
    rejected: list[dict],
    seen: set[str],
    config: dict,
    movie_code: str,
    search_scope: str,
    task_download_folder: str,
) -> None:
    if candidate.get("is_dir"):
        return
    reason = _rejection_reason(
        candidate,
        config=config,
        movie_code=movie_code,
        search_scope=search_scope,
        task_download_folder=task_download_folder,
    )
    if reason:
        rejected.append({
            "name": candidate["name"],
            "path": candidate["path"],
            "size": int(candidate.get("size") or 0),
            "reason": reason,
        })
        return
    if candidate["path"] in seen:
        return
    seen.add(candidate["path"])
    accepted.append({
        "name": candidate["name"],
        "path": candidate["path"],
        "size": int(candidate.get("size") or 0),
        "is_dir": False,
    })


def find_scoped_video_files(
    *,
    provider,
    search_terms: list[str],
    search_path: str,
    search_scope: str,
    movie_code: str,
    task_download_folder: str,
    config: dict,
) -> ScopedSearchResult:
    accepted: list[dict] = []
    rejected: list[dict] = []
    raw_results: list[dict] = []
    resolved_results: list[dict] = []
    seen: set[str] = set()
    search_term = search_terms[0] if search_terms else movie_code

    try:
        search_results = provider.search_files(search_term, search_path)
    except Exception as exc:
        return ScopedSearchResult(
            accepted_files=[],
            log_context={
                "search_term": search_term,
                "search_path": search_path,
                "search_scope": search_scope,
                "search_method": "search_files",
                "raw_results": [],
                "resolved_results": [],
                "accepted_files": [],
                "rejected_files": [{"name": "", "path": search_path, "size": 0, "reason": "search_error", "error": str(exc)}],
            },
        )

    for file_obj in search_results:
        raw_item = _raw_file_to_dict(file_obj)
        raw_results.append({key: raw_item[key] for key in ("name", "path", "size")})
        resolved = _file_to_dict(provider, file_obj)
        resolved_results.append({key: resolved[key] for key in ("name", "path", "size")})
        _append_candidate(
            candidate=resolved,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
        )

    try:
        listed_files = _recursive_list(provider, search_path, config)
    except Exception as exc:
        rejected.append({"name": "", "path": search_path, "size": 0, "reason": "list_error", "error": str(exc)})
        listed_files = []

    for listed in listed_files:
        raw_results.append({key: listed[key] for key in ("name", "path", "size")})
        resolved_results.append({key: listed[key] for key in ("name", "path", "size")})
        _append_candidate(
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
            "search_term": search_term,
            "search_path": search_path,
            "search_scope": search_scope,
            "search_method": "search_files",
            "raw_results": raw_results,
            "resolved_results": resolved_results,
            "accepted_files": accepted,
            "rejected_files": rejected,
        },
    )
```

- [ ] **Step 4: Keep existing compatibility function working**

Replace `find_existing_video_files` with:

```python
def find_existing_video_files(provider, search_terms: list[str], search_paths: list[str], config: dict) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    movie_code = search_terms[0] if search_terms else ""
    task_download_folder = search_paths[0] if search_paths else "/"
    for path in search_paths:
        scoped = find_scoped_video_files(
            provider=provider,
            search_terms=search_terms,
            search_path=path,
            search_scope="download_root",
            movie_code=movie_code,
            task_download_folder=task_download_folder,
            config=config,
        )
        for item in scoped.accepted_files:
            if item["path"] not in seen:
                seen.add(item["path"])
                results.append(item)
        if results:
            return results
    return results
```

- [ ] **Step 5: Run scoped search tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit scoped search implementation**

```bash
git add backend/app/modules/storage/worker/file_finder.py backend/tests/test_storage_file_finder_scope.py
git commit -m "feat: add scoped storage file search logging"
```

## Task 3: Task-Folder Polling Before Root Recovery

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add integration test for task folder search before root search**

Append to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_poll_downloaded_video_files_searches_task_folder_before_download_root(monkeypatch):
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False
        is_search_result: bool = False

    class Provider:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, str]] = []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            if path == "/Downloads":
                return [RemoteFile("ACZD-165.mp4", "/Downloads/ACZD-165.mp4", 500 * 1024 * 1024)]
            return []

        def get_original_path(self, path):
            return ""

        def list_files(self, path, force_refresh=False):
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

    assert [file["path"] for file in files] == ["/Downloads/ACZD-165.mp4"]
    assert context.provider.search_calls == [
        ("ACZD-165", "/Downloads/storage_sub"),
        ("ACZD-165", "/Downloads/storage_sub"),
        ("ACZD-165", "/Downloads"),
    ]
    assert [log["context"]["search_scope"] for log in context.logs if log["message"] == "查找下载文件"] == [
        "task_download_folder",
        "task_download_folder",
        "download_root",
    ]
```

- [ ] **Step 2: Add test that task folder success never searches root**

Append to `backend/tests/test_storage_worker_pipeline.py`:

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
        is_search_result: bool = False

    class Provider:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, str]] = []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 500 * 1024 * 1024)]

        def get_original_path(self, path):
            return ""

        def list_files(self, path, force_refresh=False):
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
    assert context.provider.search_calls == [("ACZD-165", "/Downloads/storage_sub")]
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_searches_task_folder_before_download_root backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_does_not_search_root_when_task_folder_has_file -v
```

Expected: FAIL because `poll_downloaded_video_files` still accepts a `search_paths` list and does not implement root recovery after task-folder polling.

- [ ] **Step 4: Update polling implementation**

In `backend/app/modules/storage/worker/steps.py`, replace `poll_downloaded_video_files` with:

```python
def _log_search_result(context, result) -> None:
    context.log(
        "INFO",
        "查找下载文件",
        result.log_context,
        step="waiting_download",
    )


def poll_downloaded_video_files(context, search_terms: list[str], task_download_folder: str, download_root: str) -> list[dict]:
    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    config = context.config
    movie_code = getattr(context.subtask, "movie_code", search_terms[0] if search_terms else "")
    max_poll_count = int(config.get("download_max_poll_count", 10) or 10)
    poll_min = float(config.get("download_poll_interval_min", 5.0) or 0)
    poll_max = float(config.get("download_poll_interval_max", poll_min) or poll_min)
    if poll_max < poll_min:
        poll_max = poll_min

    for poll_index in range(1, max_poll_count + 1):
        result = find_scoped_video_files(
            provider=context.provider,
            search_terms=search_terms,
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

    root_result = find_scoped_video_files(
        provider=context.provider,
        search_terms=search_terms,
        search_path=download_root,
        search_scope="download_root",
        movie_code=movie_code,
        task_download_folder=task_download_folder,
        config=config,
    )
    root_result.log_context["poll_index"] = max_poll_count
    root_result.log_context["max_poll_count"] = max_poll_count
    _log_search_result(context, root_result)
    if root_result.accepted_files:
        return root_result.accepted_files

    context.log(
        "WARNING",
        f"轮询次数超过上限: {max_poll_count}/{max_poll_count}，任务目录与下载根目录均未发现可用视频文件，跳过当前磁力",
        {"max_poll_count": max_poll_count, "task_download_folder": task_download_folder, "download_root": download_root},
        step="waiting_download",
    )
    return []
```

- [ ] **Step 5: Update caller in `execute_current_magnet_attempt`**

Replace:

```python
    search_paths = [download_folder, download_root, *target_paths]
    found_files = poll_downloaded_video_files(context, search_terms, search_paths)
```

with:

```python
    found_files = poll_downloaded_video_files(
        context,
        search_terms=search_terms,
        task_download_folder=download_folder,
        download_root=download_root,
    )
```

Replace the warning context:

```python
{"magnet_id": magnet.get("id"), "search_paths": search_paths}
```

with:

```python
{"magnet_id": magnet.get("id"), "task_download_folder": download_folder, "download_root": download_root}
```

- [ ] **Step 6: Run task-folder polling tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_searches_task_folder_before_download_root backend/tests/test_storage_worker_pipeline.py::test_poll_downloaded_video_files_does_not_search_root_when_task_folder_has_file -v
```

Expected: PASS.

- [ ] **Step 7: Commit polling implementation**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: search storage task folder before download root"
```

## Task 4: Magnet Loop Sequencing Tests

**Files:**
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add test that second magnet starts only after first returns failure**

Append to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_subtask_pipeline_starts_next_magnet_only_after_current_failure(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_order: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet):
        attempt_order.append(magnet["id"])
        return magnet["id"] == "m2"

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "ACZD-165"
        status: str = "queued"
        step: str = "prepare"
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}
            self.logs: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append(message)
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_order == ["m1", "m2"]
    assert context.subtask.status == "completed"
    assert [attempt["magnet_id"] for attempt in context.subtask.magnet_attempts] == ["m1", "m2"]
    assert [attempt["success"] for attempt in context.subtask.magnet_attempts] == [False, True]
```

- [ ] **Step 2: Add test that success stops later magnets**

Append to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_subtask_pipeline_does_not_start_later_magnet_after_success(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_order: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet):
        attempt_order.append(magnet["id"])
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "ACZD-165"
        status: str = "queued"
        step: str = "prepare"
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}

        def log(self, level, message, context=None, *, step=None, event=None):
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_order == ["m1"]
    assert context.subtask.status == "completed"
    assert [attempt["magnet_id"] for attempt in context.subtask.magnet_attempts] == ["m1"]
```

- [ ] **Step 3: Run magnet loop sequencing tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_subtask_pipeline_starts_next_magnet_only_after_current_failure backend/tests/test_storage_worker_pipeline.py::test_subtask_pipeline_does_not_start_later_magnet_after_success -v
```

Expected: PASS. If either test fails, fix `execute_subtask_pipeline` so it calls `execute_current_magnet_attempt` synchronously and returns immediately after success or skipped status.

- [ ] **Step 4: Commit sequencing tests**

```bash
git add backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify sequential storage magnet attempts"
```

## Task 5: Full Verification

**Files:**
- Verify: `backend/app/modules/storage/worker/file_finder.py`
- Verify: `backend/app/modules/storage/worker/steps.py`
- Verify: `backend/tests/test_storage_file_finder_scope.py`
- Verify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_timeline.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 2: Verify no target folders are used as download search paths**

Run:

```bash
rg -n "target_paths|search_paths = \\[download_folder, download_root" backend/app/modules/storage/worker/steps.py
```

Expected: No line builds download search paths with `target_paths`. `target_paths` may still appear in move, copy, and skipped-result code.

- [ ] **Step 3: Verify search logs use the expected message**

Run:

```bash
rg -n "查找下载文件|search_scope|accepted_files|rejected_files" backend/app/modules/storage/worker
```

Expected: `steps.py` logs `查找下载文件`, and `file_finder.py` builds `search_scope`, `accepted_files`, and `rejected_files`.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff --stat HEAD
git diff -- backend/app/modules/storage/worker/file_finder.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py
```

Expected: The diff only changes scoped file search, search logs, polling order, and backend tests.

- [ ] **Step 5: Commit verification fixes if files changed**

If Task 5 changed files, run:

```bash
git add backend/app/modules/storage/worker/file_finder.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify storage magnet search scope"
```

If Task 5 did not change files, do not create a commit.

## Self-Review

- Spec coverage: The plan implements task-folder-first search, root recovery after poll exhaustion, detailed search logs, and sequential magnet attempts.
- Type consistency: `find_scoped_video_files` returns `ScopedSearchResult`, and `poll_downloaded_video_files` logs `result.log_context`.
- Risk control: Existing `find_existing_video_files` remains available for current callers, while the storage worker switches to the scoped API.
- Scope control: The plan does not change frontend UI, CloudDrive2 gateway method signatures, storage config fields, or magnet weight ordering.
