# Storage Existing Target Skip After Task Exists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When CloudDrive2 reports the first magnet task already exists and no usable file is found in the download/recovery location, check the configured target folders with `ListSubFileRequest`; if the target video already exists in all required targets, mark the subtask skipped and do not try later magnets.

**Architecture:** Keep normal download discovery unchanged. Add a target-folder existence check in `backend/app/modules/storage/worker/steps.py` that uses `provider.list_files(target_folder)` so CloudDrive2 `GetSubFiles/ListSubFileRequest` is used. Call it only in the existing-task recovery path after `recover_existing_downloaded_video_files()` returns empty.

**Tech Stack:** Python 3.12+, FastAPI backend, SQLAlchemy models, pytest, CloudDrive2 provider gateway.

---

## File Structure

- Modify `backend/app/modules/storage/worker/steps.py`
  - Add a helper that lists each target folder and checks for the expected canonical filename.
  - Add a helper that marks a subtask skipped because all target files already exist.
  - Call the helper after `submit_task_exists` recovery finds no download files.

- Modify `backend/tests/test_storage_worker_pipeline.py`
  - Add tests for single-target skip after 10008 and empty download recovery.
  - Add tests for multi-target behavior: all target folders must contain the file to skip.
  - Add a test that missing target file does not skip and still allows later magnet attempts.

---

### Task 1: Add Target Folder Existing-File Detection

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Write the failing helper test for single target**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_find_existing_target_files_uses_list_files_for_single_target() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import find_existing_target_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.find_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/人妖/ACZD-165":
                return [
                    RemoteFile("ACZD-165.mp4", "/Movies/人妖/ACZD-165/ACZD-165.mp4", 4770615244),
                ]
            return []

        def find_file(self, path):
            self.find_calls.append(path)
            return None

    result = find_existing_target_files(
        provider=Provider(),
        target_paths=["/Movies/人妖/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
    )

    assert result.all_targets_exist is True
    assert result.existing_targets == ["/Movies/人妖/ACZD-165/ACZD-165.mp4"]
    assert result.missing_targets == []
    assert result.checked_targets == ["/Movies/人妖/ACZD-165"]
```

- [ ] **Step 2: Run the failing helper test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_find_existing_target_files_uses_list_files_for_single_target -q
```

Expected: FAIL with `ImportError` because `find_existing_target_files` does not exist.

- [ ] **Step 3: Implement the target existence result dataclass**

In `backend/app/modules/storage/worker/steps.py`, add this dataclass after `MoveRenamedVideosResult`:

```python
@dataclass
class ExistingTargetFilesResult:
    all_targets_exist: bool
    checked_targets: list[str]
    existing_targets: list[str]
    missing_targets: list[str]
    expected_names: list[str]
```

- [ ] **Step 4: Implement direct target-folder listing**

In `backend/app/modules/storage/worker/steps.py`, add these helpers after `_target_file_path()`:

```python
def _remote_file_name(file_obj) -> str:
    path = getattr(file_obj, "full_path", "") or getattr(file_obj, "fullPathName", "")
    return str(getattr(file_obj, "name", "") or PurePosixPath(path).name)


def _remote_file_size(file_obj) -> int:
    return int(getattr(file_obj, "size", 0) or 0)


def find_existing_target_files(provider, target_paths: list[str], expected_names: list[str]) -> ExistingTargetFilesResult:
    checked_targets: list[str] = []
    existing_targets: list[str] = []
    missing_targets: list[str] = []
    expected_name_set = {name for name in expected_names if name}

    for target_path in target_paths:
        checked_targets.append(target_path)
        try:
            files = provider.list_files(target_path)
        except Exception:
            files = []

        names_to_paths: dict[str, str] = {}
        for file_obj in files:
            name = _remote_file_name(file_obj)
            size = _remote_file_size(file_obj)
            is_dir = bool(getattr(file_obj, "is_directory", False) or getattr(file_obj, "isDirectory", False))
            if is_dir or size <= 0:
                continue
            names_to_paths[name] = str(PurePosixPath(target_path) / name)

        matched_path = next(
            (names_to_paths[name] for name in expected_name_set if name in names_to_paths),
            None,
        )
        if matched_path:
            existing_targets.append(matched_path)
        else:
            missing_targets.append(target_path)

    return ExistingTargetFilesResult(
        all_targets_exist=bool(target_paths) and len(existing_targets) == len(target_paths),
        checked_targets=checked_targets,
        existing_targets=existing_targets,
        missing_targets=missing_targets,
        expected_names=sorted(expected_name_set),
    )
```

This intentionally uses `provider.list_files(target_path)`, not `provider.find_file()`, so CloudDrive2 `ListSubFileRequest/GetSubFiles` is used.

- [ ] **Step 5: Run the helper test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_find_existing_target_files_uses_list_files_for_single_target -q
```

Expected: PASS.

- [ ] **Step 6: Add multi-target helper tests**

Append these tests to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_find_existing_target_files_requires_all_targets_to_exist() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import find_existing_target_files

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
            if path == "/Movies/A/ACZD-165":
                return [RemoteFile("ACZD-165.mp4", "/Movies/A/ACZD-165/ACZD-165.mp4", 4770615244)]
            return []

    provider = Provider()

    result = find_existing_target_files(
        provider=provider,
        target_paths=["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
    )

    assert result.all_targets_exist is False
    assert result.existing_targets == ["/Movies/A/ACZD-165/ACZD-165.mp4"]
    assert result.missing_targets == ["/Movies/B/ACZD-165"]
    assert provider.list_calls == ["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"]


def test_find_existing_target_files_accepts_suffix_filename() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import find_existing_target_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def list_files(self, path, force_refresh=False):
            return [
                RemoteFile("ACZD-165-C.mp4", f"{path}/ACZD-165-C.mp4", 4770615244),
            ]

    result = find_existing_target_files(
        provider=Provider(),
        target_paths=["/Movies/A/ACZD-165-C"],
        expected_names=["ACZD-165-C.mp4", "ACZD-165.mp4"],
    )

    assert result.all_targets_exist is True
    assert result.existing_targets == ["/Movies/A/ACZD-165-C/ACZD-165-C.mp4"]
```

- [ ] **Step 7: Run helper tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_worker_pipeline.py::test_find_existing_target_files_uses_list_files_for_single_target \
  backend/tests/test_storage_worker_pipeline.py::test_find_existing_target_files_requires_all_targets_to_exist \
  backend/tests/test_storage_worker_pipeline.py::test_find_existing_target_files_accepts_suffix_filename \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

Run:

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: detect existing target storage files"
```

---

### Task 2: Skip Subtask After Existing Magnet and Existing Target Files

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Write failing test for 10008 target skip**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_skips_after_task_exists_when_target_file_exists(monkeypatch) -> None:
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
            self.submit_calls = 0

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            self.submit_calls += 1
            raise RuntimeError("api error: code: 10008, message: 任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ACZD-165":
                return [
                    RemoteFile("ACZD-165.mp4", "/Movies/A/ACZD-165/ACZD-165.mp4", 4770615244),
                ]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

        def delete_file(self, path):
            return None

    class Subtask:
        id = "sub"
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
        skip_reason = None

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
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert context.subtask.result == {
        "status": "skipped",
        "reason": "target_exists",
        "files": [
            {
                "renamed_name": "ACZD-165.mp4",
                "existing_targets": ["/Movies/A/ACZD-165/ACZD-165.mp4"],
                "skip_reason": "target_exists",
            }
        ],
    }
    assert context.subtask.skipped_files == [
        {
            "renamed_name": "ACZD-165.mp4",
            "existing_targets": ["/Movies/A/ACZD-165/ACZD-165.mp4"],
            "skip_reason": "target_exists",
        }
    ]
    assert "/Movies/A/ACZD-165" in context.provider.list_calls
    assert any(log["event"] == "subtask_skipped" for log in context.logs)
```

- [ ] **Step 2: Run the failing 10008 target skip test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_skips_after_task_exists_when_target_file_exists -q
```

Expected: FAIL because `execute_current_magnet_attempt()` returns `False` when existing-task recovery finds no download files and never checks target folders.

- [ ] **Step 3: Add a subtask skip helper**

In `backend/app/modules/storage/worker/steps.py`, add this helper after `find_existing_target_files()`:

```python
def mark_subtask_skipped_for_existing_targets(context, existing_result: ExistingTargetFilesResult, expected_name: str) -> None:
    skipped_files = [
        {
            "renamed_name": expected_name,
            "existing_targets": existing_result.existing_targets,
            "skip_reason": "target_exists",
        }
    ]
    context.subtask.status = "skipped"
    context.subtask.skip_reason = "target_exists"
    context.subtask.skipped_files = skipped_files
    context.subtask.result = {
        "status": "skipped",
        "reason": "target_exists",
        "files": skipped_files,
    }
    context.log(
        "INFO",
        "目标文件已全部存在，子任务标记为跳过",
        {
            "skipped_files": skipped_files,
            "target_paths": existing_result.checked_targets,
            "existing_targets": existing_result.existing_targets,
            "expected_names": existing_result.expected_names,
        },
        step="waiting_download",
        event="subtask_skipped",
    )
    context.publish_subtask()
```

- [ ] **Step 4: Add target check after empty existing-task recovery**

In `execute_current_magnet_attempt()`, replace:

```python
    if not found_files:
        context.log("WARNING", "未在下载目录找到可用视频文件", {"magnet_id": magnet.get("id"), "task_download_folder": download_folder, "download_root": download_root}, step="waiting_download")
        return False
```

with:

```python
    if not found_files:
        context.log(
            "WARNING",
            "未在下载目录找到可用视频文件",
            {"magnet_id": magnet.get("id"), "task_download_folder": download_folder, "download_root": download_root},
            step="waiting_download",
        )
        if submit_task_exists:
            expected_names = [preview_name]
            existing_targets = find_existing_target_files(provider, target_paths, expected_names)
            context.log(
                "INFO",
                "检查目标目录是否已存在视频文件",
                {
                    "target_paths": target_paths,
                    "expected_names": expected_names,
                    "existing_targets": existing_targets.existing_targets,
                    "missing_targets": existing_targets.missing_targets,
                    "search_method": "list_sub_files",
                    "recovery_reason": "submit_task_exists_download_missing",
                },
                step="waiting_download",
            )
            if existing_targets.all_targets_exist:
                mark_subtask_skipped_for_existing_targets(context, existing_targets, preview_name)
                return True
        return False
```

This preserves normal behavior for non-10008 magnet attempts.

- [ ] **Step 5: Run the 10008 target skip test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_skips_after_task_exists_when_target_file_exists -q
```

Expected: PASS.

- [ ] **Step 6: Write multi-target skip test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_skips_after_task_exists_only_when_all_targets_exist(monkeypatch) -> None:
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

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path in {"/Movies/A/ACZD-165", "/Movies/B/ACZD-165"}:
                return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 4770615244)]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def delete_file(self, path):
            return None

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        target_locations = ["A", "B"]
        selected_storage_location = None
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "queued"
        step = "prepare"
        result = {}
        skip_reason = None

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
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert sorted(context.subtask.skipped_files[0]["existing_targets"]) == [
        "/Movies/A/ACZD-165/ACZD-165.mp4",
        "/Movies/B/ACZD-165/ACZD-165.mp4",
    ]
    assert "/Movies/A/ACZD-165" in context.provider.list_calls
    assert "/Movies/B/ACZD-165" in context.provider.list_calls
```

- [ ] **Step 7: Write missing-target non-skip test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_does_not_skip_after_task_exists_when_any_target_missing(monkeypatch) -> None:
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

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ACZD-165":
                return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 4770615244)]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        target_locations = ["A", "B"]
        selected_storage_location = None
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "queued"
        step = "prepare"
        result = {}
        skip_reason = None

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

    assert success is False
    assert context.subtask.status == "queued"
    assert context.subtask.skip_reason is None
    assert "/Movies/A/ACZD-165" in context.provider.list_calls
    assert "/Movies/B/ACZD-165" in context.provider.list_calls
    assert any(
        log["message"] == "检查目标目录是否已存在视频文件"
        and log["context"]["missing_targets"] == ["/Movies/B/ACZD-165"]
        for log in context.logs
    )
```

- [ ] **Step 8: Run target-skip behavior tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_skips_after_task_exists_when_target_file_exists \
  backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_skips_after_task_exists_only_when_all_targets_exist \
  backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_does_not_skip_after_task_exists_when_any_target_missing \
  -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: skip storage when existing target files are complete"
```

---

### Task 3: Verify Pipeline Stops Later Magnets After Target Skip

**Files:**
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add integration-style pipeline test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_subtask_pipeline_stops_after_existing_target_skip_from_task_exists(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet):
        attempt_ids.append(magnet["id"])
        context.subtask.status = "skipped"
        context.subtask.skip_reason = "target_exists"
        context.subtask.result = {
            "status": "skipped",
            "reason": "target_exists",
            "files": [
                {
                    "renamed_name": "ACZD-165.mp4",
                    "existing_targets": ["/Movies/A/ACZD-165/ACZD-165.mp4"],
                    "skip_reason": "target_exists",
                }
            ],
        }
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
        skip_reason: str | None = None
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None
        result: dict | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []
            if self.result is None:
                self.result = {}

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

    assert attempt_ids == ["m1"]
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert context.subtask.step == "done"
    assert context.subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert context.subtask.magnet_attempts[0]["success"] is True
    assert context.subtask.magnet_attempts[0]["status"] == "skipped"
```

- [ ] **Step 2: Run the pipeline stop test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_subtask_pipeline_stops_after_existing_target_skip_from_task_exists -q
```

Expected: PASS. This behavior should already be supported once `execute_current_magnet_attempt()` returns `True` with `subtask.status == "skipped"`.

- [ ] **Step 3: Run focused storage pipeline tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit Task 3 if the new test was added separately**

Run:

```bash
git add backend/tests/test_storage_worker_pipeline.py
git commit -m "test: stop magnets after existing target skip"
```

If Task 2 commit already included this test, do not create a duplicate commit.

---

### Task 4: Final Verification

**Files:**
- Verify only; no source edits expected.

- [ ] **Step 1: Run storage worker and file discovery tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_worker_pipeline.py \
  backend/tests/test_storage_file_finder_scope.py \
  backend/tests/test_storage_worker_service.py \
  -q
```

Expected: PASS. Existing warning from `fastapi.testclient` or Starlette deprecation may appear and does not block this change.

- [ ] **Step 2: Inspect target-exists log strings**

Run:

```bash
rg -n "检查目标目录是否已存在视频文件|目标文件已全部存在|target_exists|find_existing_target_files" backend/app/modules/storage/worker backend/tests/test_storage_worker_pipeline.py
```

Expected:

- `execute_current_magnet_attempt()` logs `检查目标目录是否已存在视频文件` only after `submit_task_exists` and empty recovered downloads.
- `mark_subtask_skipped_for_existing_targets()` logs `目标文件已全部存在，子任务标记为跳过`.
- Tests cover single-target, all multi-target, and missing multi-target behavior.

- [ ] **Step 3: Manual log acceptance check**

Use the attached log scenario as the acceptance model:

```text
第一条磁力:
  提交磁力 -> 任务已存在 (10008)
  waiting_download -> 下载/恢复目录未找到可用视频
  waiting_download -> 检查 targets=['/嘿嘿/日本/人妖/ACZD-165']
  如果 /嘿嘿/日本/人妖/ACZD-165/ACZD-165.mp4 存在:
    子任务 status=skipped
    skip_reason=target_exists
    不再出现第二条或第三条磁力的 "开始尝试磁力"
```

- [ ] **Step 4: Commit verification-only fixes if needed**

If Step 1 or Step 2 required assertion or log wording fixes, run:

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify existing target skip recovery"
```

If no fixes were needed, do not create a commit for Task 4.

---

## Self-Review

Spec coverage:

- First magnet returns `任务已存在 (code 10008)`: Task 2 tests and implementation gate on `submit_task_exists`.
- Download/recovery directories do not contain usable video: Task 2 tests use empty `list_files()` and empty `search_files()`.
- Check target folders with `ListSubFileRequest`: Task 1 helper uses `provider.list_files(target_path)` and tests assert list calls.
- Multiple target folders must all be checked: Task 1 and Task 2 multi-target tests assert both target paths are listed.
- If all required targets have the expected video, mark subtask skipped: Task 2 implements `mark_subtask_skipped_for_existing_targets()`.
- Do not try later magnets after skip: Task 3 verifies `execute_subtask_pipeline()` stops after first successful skipped attempt.
- Continue to next magnet only when any required target is missing: Task 2 missing-target test expects `success is False`.

No incomplete markers remain. Function names are consistent: `find_existing_target_files`, `ExistingTargetFilesResult`, and `mark_subtask_skipped_for_existing_targets`.
