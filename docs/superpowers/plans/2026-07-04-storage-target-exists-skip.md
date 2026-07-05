# Storage Target Exists Skip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a storage subtask finds that every target video file already exists during the first magnet attempt, mark the subtask as skipped and stop trying later magnets.

**Architecture:** Keep the current storage worker pipeline and Redis-backed main task flow. Change the move step to return structured move results instead of treating “all targets exist” as a failed magnet attempt. The subtask pipeline will treat that result as a terminal skipped outcome and preserve `skipped` status instead of overwriting it as `completed`.

**Tech Stack:** Python 3.12, FastAPI backend modules, SQLAlchemy storage task models, CloudDrive2 gateway abstraction, Pytest.

---

## File Structure

- Modify `backend/app/modules/storage/worker/steps.py`: Add a structured move result, detect all-target-exists skips, set subtask skipped state, and preserve skipped status in the magnet loop.
- Modify `backend/tests/test_storage_worker_pipeline.py`: Add regression coverage for a target-existing file and for stopping the magnet loop after a skipped outcome.

## Current Root Cause

The attached log shows this flow:

- The first magnet reaches `move_files`.
- `move_renamed_videos` logs `跳过已存在: MIDA-628.mp4` with `skip_reason: target_exists`.
- `execute_current_magnet_attempt` then sees `moved_files` is empty and returns `False`.
- `execute_subtask_pipeline` logs `磁力尝试失败，准备尝试下一条` and starts the next magnet.

That is incorrect for this case. If the selected storage target already has every expected output file, no more work is needed for the subtask. The subtask should be `skipped`, and the magnet loop should stop.

## Task 1: Add Failing Regression Tests

**Files:**
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add imports for the new tests**

At the top of `backend/tests/test_storage_worker_pipeline.py`, keep the existing imports and add:

```python
from types import SimpleNamespace
```

If `SimpleNamespace` is already imported in the file after previous work, keep one import only.

- [ ] **Step 2: Add a regression test for all target files already existing**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_marks_subtask_skipped_when_all_targets_exist(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    target_folder = "/Movies/巨乳/MIDA-628"
    target_file = f"{target_folder}/MIDA-628.mp4"
    file_size = 6910439461

    class Result:
        success = True
        error_message = None
        result_paths = []

    class SearchFile:
        name = "MIDA-628.mp4"
        full_path = "/Search/MIDA-628.mp4"
        size = file_size
        is_directory = False
        is_search_result = True

    class ExistingTargetProvider:
        def __init__(self) -> None:
            self.deleted: list[str] = []
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            return Result()

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            if path == target_folder:
                return [SearchFile()]
            return []

        def get_original_path(self, path):
            return target_file

        def list_files(self, path, force_refresh=False):
            return []

        def find_file(self, path):
            if path == target_file:
                return SimpleNamespace(size=file_size)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

        def delete_file(self, path):
            self.deleted.append(path)
            return SimpleNamespace(success=True)

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "MIDA-628"
        step: str = "prepare"
        status: str = "running"
        skip_reason: str | None = None
        download_path: str = ""
        target_locations: list | None = None
        selected_storage_location: str = "巨乳"
        target_paths: list | None = None
        renamed_files: list | None = None
        moved_files: list | None = None
        skipped_files: list | None = None
        result: dict | None = None

        def __post_init__(self):
            if self.target_locations is None:
                self.target_locations = ["巨乳"]
            if self.target_paths is None:
                self.target_paths = []
            if self.renamed_files is None:
                self.renamed_files = []
            if self.moved_files is None:
                self.moved_files = []
            if self.skipped_files is None:
                self.skipped_files = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self, subtask, config, provider):
            self.subtask = subtask
            self.config = config
            self.provider = provider

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            from backend.app.modules.storage.tasks.logs import write_storage_subtask_log

            write_storage_subtask_log(
                str(self.subtask.id),
                level,
                message,
                context or {},
                step=step,
                event=event,
            )
            return {}

        def publish_subtask(self):
            return None

    provider = ExistingTargetProvider()
    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={
            "download_root_folder": "/Downloads",
            "target_folder": "/Movies",
            "download_max_poll_count": 1,
            "download_poll_interval_min": 0,
            "download_poll_interval_max": 0,
            "video_extensions": [".mp4"],
            "minimum_video_size_mb": 100,
            "use_task_subfolder": True,
        },
        provider=provider,
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:mida628", "tags": [], "weight": 16394},
    )

    assert success is True
    assert subtask.status == "skipped"
    assert subtask.skip_reason == "target_exists"
    assert subtask.result["status"] == "skipped"
    assert subtask.result["reason"] == "target_exists"
    assert subtask.moved_files == []
    assert subtask.skipped_files[0]["skip_reason"] == "target_exists"
    assert subtask.skipped_files[0]["existing_targets"] == [target_file]
    assert provider.move_calls == []
    assert provider.copy_calls == []
    assert provider.deleted == [f"/Downloads/storage_{subtask.id}"]

    logs = read_storage_subtask_logs(str(subtask.id))
    assert any("目标文件已全部存在，子任务标记为跳过" in entry["message"] for entry in logs)
    assert any("清理完成" in entry["message"] for entry in logs)
```

- [ ] **Step 3: Add a regression test that skipped status stops later magnets**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_subtask_pipeline_stops_after_target_exists_skip(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet):
        attempt_ids.append(magnet["id"])
        context.subtask.status = "skipped"
        context.subtask.skip_reason = "target_exists"
        context.subtask.result = {"status": "skipped", "reason": "target_exists"}
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
    assert context.subtask.magnet_attempts == [
        {
            "magnet_id": "m1",
            "success": True,
            "status": "skipped",
            "timestamp": context.subtask.magnet_attempts[0]["timestamp"],
        }
    ]
```

- [ ] **Step 4: Run the new tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_marks_subtask_skipped_when_all_targets_exist backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_target_exists_skip -v
```

Expected: FAIL. The first test fails because target-exists skips currently return `False` from `execute_current_magnet_attempt`. The second test fails because the success branch currently overwrites skipped status with completed and does not record status in the attempt record.

- [ ] **Step 5: Commit the failing tests**

```bash
git add backend/tests/test_storage_worker_pipeline.py
git commit -m "test: cover storage target exists skip behavior"
```

## Task 2: Return Structured Move Results

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Add a result dataclass for move output**

Add this import near the top of `backend/app/modules/storage/worker/steps.py`:

```python
from dataclasses import dataclass
```

Add this dataclass above `move_renamed_videos`:

```python
@dataclass
class MoveRenamedVideosResult:
    moved_files: list[dict]
    skipped_files: list[dict]
    all_targets_exist: bool = False
```

- [ ] **Step 2: Change `move_renamed_videos` to return the structured result**

Replace the function signature:

```python
def move_renamed_videos(context, renamed_files: list[dict], target_paths: list[str]) -> MoveRenamedVideosResult:
```

Replace the final return statement in `move_renamed_videos` with:

```python
    all_targets_exist = bool(renamed_files) and len(skipped) == len(renamed_files) and all(
        item.get("skip_reason") == "target_exists"
        for item in skipped
    )
    return MoveRenamedVideosResult(
        moved_files=moved,
        skipped_files=skipped,
        all_targets_exist=all_targets_exist,
    )
```

- [ ] **Step 3: Keep partial target-exists behavior unchanged**

Confirm this block remains in `move_renamed_videos`:

```python
        if len(existing_targets) == len(target_paths):
            skipped.append({**file_info, "skip_reason": "target_exists", "existing_targets": existing_targets})
            context.log("INFO", f"跳过已存在: {file_name}", {"existing_targets": existing_targets}, step="move_files")
            continue
```

Confirm this block remains for a final destination that already exists while copy targets still require work:

```python
        if _target_file_exists(context.provider, move_dst):
            moved.append({**file_info, "moved_path": move_dst, "copied_paths": copied_paths})
            context.log("INFO", f"跳过已存在: {file_name}", {"target": move_dst}, step="move_files")
            continue
```

This distinction matters. Only “every target path already has every expected file” becomes a skipped subtask. A partial existing target still counts as work completed after missing copies are created.

- [ ] **Step 4: Update the caller to unpack the result object**

In `execute_current_magnet_attempt`, replace:

```python
    moved_files, skipped_files = move_renamed_videos(context, renamed_files, target_paths)
    subtask.renamed_files = renamed_files
    subtask.moved_files = moved_files
    subtask.skipped_files = skipped_files
```

with:

```python
    move_result = move_renamed_videos(context, renamed_files, target_paths)
    moved_files = move_result.moved_files
    skipped_files = move_result.skipped_files
    subtask.renamed_files = renamed_files
    subtask.moved_files = moved_files
    subtask.skipped_files = skipped_files
```

- [ ] **Step 5: Run existing pipeline tests and verify the signature change is complete**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py -v
```

Expected: tests still fail only for target-exists terminal semantics. There should be no `ValueError: too many values to unpack` or `TypeError` from the new return type.

- [ ] **Step 6: Commit the structured move result**

```bash
git add backend/app/modules/storage/worker/steps.py
git commit -m "refactor: return structured storage move results"
```

## Task 3: Mark All-Targets-Exist as Skipped and Terminal

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Add skipped terminal handling after the move step**

In `execute_current_magnet_attempt`, insert this block immediately after `context.publish_subtask()` that follows the move result assignment:

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

The surrounding code must then read:

```python
    context.publish_subtask()
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

    if not moved_files:
        context.log("WARNING", "没有文件完成移动或复制", {"skipped_files": skipped_files}, step="move_files")
        return False
```

- [ ] **Step 2: Preserve skipped status in the magnet loop**

In `execute_subtask_pipeline`, replace the success branch:

```python
        if success:
            subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            context.publish_subtask()
            return
```

with:

```python
        if success:
            if subtask.status != "skipped":
                subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            context.publish_subtask()
            return
```

- [ ] **Step 3: Record the final status in magnet attempts**

In `execute_subtask_pipeline`, replace the attempt record:

```python
        attempt_record = {
            "magnet_id": magnet.get("id"),
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
```

with:

```python
        attempt_record = {
            "magnet_id": magnet.get("id"),
            "success": success,
            "status": subtask.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
```

- [ ] **Step 4: Run the target-exists tests and verify pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_marks_subtask_skipped_when_all_targets_exist backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_target_exists_skip -v
```

Expected: PASS.

- [ ] **Step 5: Run all storage worker pipeline tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_timeline.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the terminal skip behavior**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: skip storage subtask when target files exist"
```

## Task 4: Verification and Diff Review

**Files:**
- Verify: `backend/app/modules/storage/worker/steps.py`
- Verify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Run targeted backend verification**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_timeline.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 2: Inspect the final backend diff**

Run:

```bash
git diff --stat HEAD
git diff -- backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
```

Expected: The diff only changes storage worker skip semantics and backend tests. It must not change storage config, movie list UI, frontend realtime code, or CloudDrive2 gateway code.

- [ ] **Step 3: Confirm no later magnet is attempted for skipped target-exists tasks**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_target_exists_skip -v
```

Expected: PASS with `attempt_ids == ["m1"]`.

- [ ] **Step 4: Commit verification fixes if files changed**

If Task 4 changed files, run:

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify storage target exists skip"
```

If Task 4 did not change files, do not create a commit.

## Self-Review

- Spec coverage: The plan covers the attached log case where the first magnet finds an existing target file during `move_files`.
- Terminal behavior: The plan makes the subtask `skipped`, sets `skip_reason` to `target_exists`, cleans the task download folder, returns `True` from the current magnet attempt, and stops the magnet loop.
- Multiple target behavior: The plan skips only when every expected target already exists. Partial existing targets still allow missing copies or moves to proceed.
- Test coverage: The plan includes a direct magnet-attempt regression test and a pipeline-level test proving the second magnet is not attempted.
