# Storage Rename Existing Source Target Skip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When rename reports that the canonical filename already exists, use that canonical file for move or copy work, and mark the subtask skipped without trying later magnets when every target already contains the file.

**Architecture:** Keep the current storage worker pipeline and existing `rename_name_exists` classification. Tighten the contract between `rename_selected_videos` and `move_renamed_videos`: a resolved canonical source path is a valid source for move/copy, while destination existence is checked for every target path before any operation. If all expected destination files already exist, the move result is terminal skipped and the magnet loop stops.

**Tech Stack:** Python 3.12, FastAPI backend modules, SQLAlchemy storage task models, CloudDrive2 gateway abstraction, Pytest.

---

## Current Context

The current worker already has partial support for this area:

- `backend/app/modules/storage/worker/steps.py` contains `is_rename_name_exists_error`.
- `rename_selected_videos` can set `rename_name_exists=True`, `existing_path`, `renamed_path`, and `renamed_name`.
- `move_renamed_videos` checks whether destination files exist before copying or moving.
- `execute_current_magnet_attempt` already treats `move_result.all_targets_exist` and `move_result.all_rename_name_exists` as skipped terminal outcomes.

This plan finishes the desired semantics:

- If rename says `MIDA-628.mp4` already exists beside the downloaded file, use `/source/dir/MIDA-628.mp4` as the source for move/copy.
- Before each move or copy, check the corresponding target folder for `MIDA-628.mp4`.
- If every expected target already has `MIDA-628.mp4`, mark the subtask `skipped` with `skip_reason="target_exists"` and do not try later magnets.
- If only some expected targets exist, copy or move only the missing targets by using the canonical existing source file.

## File Structure

- Modify `backend/app/modules/storage/worker/steps.py`: Make canonical existing source reuse explicit, add a helper for destination path construction, and ensure all-target-exists terminal skip covers rename-name-exists source files.
- Modify `backend/tests/test_storage_worker_pipeline.py`: Add regression tests for single-target skip, multi-target skip, and partial multi-target copy using the canonical existing source file.

## Task 1: Add Regression Tests for Canonical Source Reuse

**Files:**
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add a test for single-target existing destination skip**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_rename_existing_source_skips_when_single_target_already_has_file() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.steps import move_renamed_videos

    target_file = "/Movies/巨乳/MIDA-628/MIDA-628.mp4"

    class Provider:
        def __init__(self) -> None:
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            if path == target_file:
                return SimpleNamespace(size=6910439461)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    result = move_renamed_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
                "renamed_path": "/Downloads/MIDA-628.mp4",
                "renamed_name": "MIDA-628.mp4",
                "rename_name_exists": True,
                "existing_path": "/Downloads/MIDA-628.mp4",
            }
        ],
        ["/Movies/巨乳/MIDA-628"],
    )

    assert result.moved_files == []
    assert result.skipped_files == [
        {
            "name": "hhd800.com@MIDA-628.mp4",
            "path": "/Downloads/hhd800.com@MIDA-628.mp4",
            "size": 6910439461,
            "renamed_path": "/Downloads/MIDA-628.mp4",
            "renamed_name": "MIDA-628.mp4",
            "rename_name_exists": True,
            "existing_path": "/Downloads/MIDA-628.mp4",
            "skip_reason": "target_exists",
            "existing_targets": [target_file],
        }
    ]
    assert result.all_targets_exist is True
    assert context.provider.move_calls == []
    assert context.provider.copy_calls == []
    assert any("跳过已存在: MIDA-628.mp4" in message for message in context.messages)
```

- [ ] **Step 2: Add a test for multi-target existing destination skip**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_rename_existing_source_skips_when_all_multi_targets_already_have_file() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.steps import move_renamed_videos

    target_files = {
        "/Movies/巨乳/MIDA-628/MIDA-628.mp4",
        "/Movies/中字/MIDA-628/MIDA-628.mp4",
    }

    class Provider:
        def __init__(self) -> None:
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            if path in target_files:
                return SimpleNamespace(size=6910439461)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    result = move_renamed_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
                "renamed_path": "/Downloads/MIDA-628.mp4",
                "renamed_name": "MIDA-628.mp4",
                "rename_name_exists": True,
                "existing_path": "/Downloads/MIDA-628.mp4",
            }
        ],
        ["/Movies/巨乳/MIDA-628", "/Movies/中字/MIDA-628"],
    )

    assert result.moved_files == []
    assert result.skipped_files[0]["skip_reason"] == "target_exists"
    assert result.skipped_files[0]["existing_targets"] == [
        "/Movies/巨乳/MIDA-628/MIDA-628.mp4",
        "/Movies/中字/MIDA-628/MIDA-628.mp4",
    ]
    assert result.all_targets_exist is True
    assert context.provider.move_calls == []
    assert context.provider.copy_calls == []
```

- [ ] **Step 3: Add a test for partially missing multi-target destinations**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_rename_existing_source_copies_missing_multi_target_and_keeps_existing_move_target() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.steps import move_renamed_videos

    existing_move_target = "/Movies/中字/MIDA-628/MIDA-628.mp4"

    class Provider:
        def __init__(self) -> None:
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            if path == existing_move_target:
                return SimpleNamespace(size=6910439461)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    result = move_renamed_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
                "renamed_path": "/Downloads/MIDA-628.mp4",
                "renamed_name": "MIDA-628.mp4",
                "rename_name_exists": True,
                "existing_path": "/Downloads/MIDA-628.mp4",
            }
        ],
        ["/Movies/巨乳/MIDA-628", "/Movies/中字/MIDA-628"],
    )

    assert result.all_targets_exist is False
    assert result.moved_files == [
        {
            "name": "hhd800.com@MIDA-628.mp4",
            "path": "/Downloads/hhd800.com@MIDA-628.mp4",
            "size": 6910439461,
            "renamed_path": "/Downloads/MIDA-628.mp4",
            "renamed_name": "MIDA-628.mp4",
            "rename_name_exists": True,
            "existing_path": "/Downloads/MIDA-628.mp4",
            "moved_path": "/Movies/中字/MIDA-628/MIDA-628.mp4",
            "copied_paths": ["/Movies/巨乳/MIDA-628/MIDA-628.mp4"],
        }
    ]
    assert result.skipped_files == []
    assert context.provider.copy_calls == [
        ("/Downloads/MIDA-628.mp4", "/Movies/巨乳/MIDA-628")
    ]
    assert context.provider.move_calls == []
```

- [ ] **Step 4: Add a pipeline-level test for no later magnet after destination skip**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_subtask_pipeline_stops_after_rename_existing_source_target_skip(monkeypatch):
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
                    "renamed_path": "/Downloads/MIDA-628.mp4",
                    "existing_targets": ["/Movies/巨乳/MIDA-628/MIDA-628.mp4"],
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
        movie_code: str = "MIDA-628"
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

- [ ] **Step 5: Run the new tests and verify failure or confirm existing coverage**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_rename_existing_source_skips_when_single_target_already_has_file backend/tests/test_storage_worker_pipeline.py::test_rename_existing_source_skips_when_all_multi_targets_already_have_file backend/tests/test_storage_worker_pipeline.py::test_rename_existing_source_copies_missing_multi_target_and_keeps_existing_move_target backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_rename_existing_source_target_skip -v
```

Expected: FAIL if the current implementation does not consistently use `renamed_path` as the source or does not aggregate all-target-exists correctly. PASS is acceptable if the implementation already satisfies the behavior; keep the tests as regression coverage.

- [ ] **Step 6: Commit the regression tests**

```bash
git add backend/tests/test_storage_worker_pipeline.py
git commit -m "test: cover rename existing source target skips"
```

## Task 2: Make Canonical Source and Destination Paths Explicit

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Add path helper functions**

Add these helpers below `_target_file_exists` in `backend/app/modules/storage/worker/steps.py`:

```python
def _move_source_path(file_info: dict) -> str:
    return str(file_info.get("existing_path") or file_info.get("renamed_path") or file_info["path"])


def _move_file_name(file_info: dict) -> str:
    return str(file_info.get("renamed_name") or PurePosixPath(_move_source_path(file_info)).name)


def _target_file_path(target_folder: str, file_name: str) -> str:
    return str(PurePosixPath(target_folder) / file_name)
```

- [ ] **Step 2: Use the helpers in `move_renamed_videos`**

In `move_renamed_videos`, replace:

```python
        src = file_info.get("renamed_path") or file_info["path"]
        file_name = PurePosixPath(src).name
        existing_targets = [str(PurePosixPath(target) / file_name) for target in target_paths if _target_file_exists(context.provider, str(PurePosixPath(target) / file_name))]
```

with:

```python
        src = _move_source_path(file_info)
        file_name = _move_file_name(file_info)
        existing_targets = [
            _target_file_path(target, file_name)
            for target in target_paths
            if _target_file_exists(context.provider, _target_file_path(target, file_name))
        ]
```

- [ ] **Step 3: Use destination helper for copy target checks**

In `move_renamed_videos`, replace:

```python
            copy_dst = str(PurePosixPath(copy_target) / file_name)
```

with:

```python
            copy_dst = _target_file_path(copy_target, file_name)
```

- [ ] **Step 4: Use destination helper for move target checks**

In `move_renamed_videos`, replace:

```python
        move_dst = str(PurePosixPath(move_target) / file_name)
```

with:

```python
        move_dst = _target_file_path(move_target, file_name)
```

- [ ] **Step 5: Add log context for canonical source reuse**

After computing `src` and `file_name`, insert:

```python
        if file_info.get("rename_name_exists"):
            context.log(
                "INFO",
                f"使用已存在的规范命名文件执行移动或复制: {file_name}",
                {"source": src, "targets": target_paths},
                step="move_files",
            )
```

- [ ] **Step 6: Run canonical source tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_rename_existing_source_skips_when_single_target_already_has_file backend/tests/test_storage_worker_pipeline.py::test_rename_existing_source_skips_when_all_multi_targets_already_have_file backend/tests/test_storage_worker_pipeline.py::test_rename_existing_source_copies_missing_multi_target_and_keeps_existing_move_target -v
```

Expected: PASS.

- [ ] **Step 7: Commit canonical source path handling**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: use existing renamed source for storage moves"
```

## Task 3: Preserve Terminal Skip Semantics

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Confirm all-target-exists aggregation covers canonical source files**

Confirm this block remains at the end of `move_renamed_videos`:

```python
    all_targets_exist = bool(renamed_files) and len(skipped) == len(renamed_files) and all(
        item.get("skip_reason") == "target_exists"
        for item in skipped
    )
```

This is the rule that makes single mode and multiple mode skip only when every expected target already has the file.

- [ ] **Step 2: Confirm terminal target-exists handling in the magnet attempt**

Confirm `execute_current_magnet_attempt` contains this block before `if not moved_files:`:

```python
    if move_result.all_targets_exist:
        subtask.status = "skipped"
        subtask.skip_reason = "target_exists"
        subtask.result = {
            "status": "skipped",
            "reason": "target_exists",
            "files": skipped_files,
        }
        context.log(
            "INFO",
            "目标文件已全部存在，子任务标记为跳过",
            {"skipped_files": skipped_files, "target_paths": target_paths},
            step="move_files",
            event="subtask_skipped",
        )
        context.publish_subtask()
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True
```

If this block is missing or appears after `if not moved_files:`, move it before `if not moved_files:`.

- [ ] **Step 3: Confirm skipped status is preserved in the magnet loop**

Confirm `execute_subtask_pipeline` contains:

```python
        if success:
            if subtask.status != "skipped":
                subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            context.publish_subtask()
            return
```

If the code overwrites skipped status with completed, replace the success branch with the code above.

- [ ] **Step 4: Confirm attempt records include skipped status**

Confirm `execute_subtask_pipeline` creates attempt records with:

```python
        attempt_record = {
            "magnet_id": magnet.get("id"),
            "success": success,
            "status": subtask.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
```

If `status` is missing, add it exactly as shown.

- [ ] **Step 5: Run no-later-magnet test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_rename_existing_source_target_skip -v
```

Expected: PASS.

- [ ] **Step 6: Commit terminal skip preservation**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: stop storage magnets after existing destination skip"
```

## Task 4: Full Verification

**Files:**
- Verify: `backend/app/modules/storage/worker/steps.py`
- Verify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Run storage worker regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_timeline.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 2: Verify existing rename-name-exists tests still pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_rename_name_exists_reuses_existing_canonical_source_file backend/tests/test_storage_worker_pipeline.py::test_rename_name_exists_without_resolved_file_becomes_terminal_skip backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_rename_name_exists_skip -v
```

Expected: PASS.

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git diff --stat HEAD
git diff -- backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
```

Expected: The diff only changes canonical source path selection, destination existence checks, terminal skip handling, and backend tests.

- [ ] **Step 4: Commit verification fixes if files changed**

If Task 4 changed files, run:

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify storage rename existing target flow"
```

If Task 4 did not change files, do not create a commit.

## Self-Review

- Requirement coverage: The plan uses the canonical existing file when rename reports the target filename exists.
- Destination checks: The plan checks every move and copy target before performing the operation.
- Skip behavior: The plan marks the subtask skipped only when every expected target already has the file, and the magnet loop stops after that skipped result.
- Partial multi-target behavior: The plan still copies or moves missing targets when only some destinations already exist.
