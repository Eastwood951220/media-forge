# Storage Rename Name Exists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat CloudDrive2 rename failures caused by `20004` / `目录名称已存在` as a terminal already-exists condition so storage subtasks do not try later magnets.

**Architecture:** Keep the current storage worker pipeline and magnet ordering. Add explicit classification for rename name-conflict errors, resolve the existing canonical file or final target file before moving, and return a terminal skip result when the conflict means the requested output already exists. Generic rename failures remain non-terminal and can still fail the current magnet.

**Tech Stack:** Python 3.12, FastAPI backend modules, SQLAlchemy storage task models, CloudDrive2 gateway abstraction, Pytest.

---

## Root Cause From Attached Log

The attached log shows this sequence:

- `rename_files` tries to rename `hhd800.com@MIDA-628.mp4` to `MIDA-628.mp4`.
- CloudDrive2 returns an internal RPC error from 115 Open API: `code: 20004, message: 很抱歉，该目录名称已存在。`
- `rename_selected_videos` stores that as a generic `rename_error`.
- `move_renamed_videos` skips the file with `skip_reason: rename_failed`.
- `execute_current_magnet_attempt` sees no moved files, returns `False`, and `execute_subtask_pipeline` tries the next magnet.

This is wrong for `20004 / 目录名称已存在`. That error means the canonical name already exists at the rename destination, so the worker should not keep trying more magnets for the same movie. The worker should either reuse the existing canonical source file for the move step, or mark the subtask skipped if the final target file already exists.

## File Structure

- Modify `backend/app/modules/storage/worker/steps.py`: Add rename-error classification, resolve name-existing files, propagate a terminal skipped result, and stop the magnet loop for this condition.
- Modify `backend/tests/test_storage_worker_pipeline.py`: Add regression tests for rename name-exists errors and for stopping after the first magnet.

## Task 1: Add Failing Regression Tests

**Files:**
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add tests for rename name-exists classification**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_is_rename_name_exists_error_detects_clouddrive_20004() -> None:
    from backend.app.modules.storage.worker.steps import is_rename_name_exists_error

    error = RuntimeError(
        'api error Cloud 115open(342367138) api error: code: 20004, '
        'message: 很抱歉，该目录名称已存在。'
    )

    assert is_rename_name_exists_error(error) is True
    assert is_rename_name_exists_error(RuntimeError("permission denied")) is False
```

- [ ] **Step 2: Add a test that reuses the existing canonical source file**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_rename_name_exists_reuses_existing_canonical_source_file() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.steps import rename_selected_videos

    class RenameNameExistsProvider:
        def __init__(self) -> None:
            self.find_calls: list[str] = []

        def rename_file(self, source_path, new_name):
            raise RuntimeError("api error: code: 20004, message: 很抱歉，该目录名称已存在。")

        def find_file(self, path):
            self.find_calls.append(path)
            if path == "/Downloads/MIDA-628.mp4":
                return SimpleNamespace(size=6910439461)
            return None

    class FakeSubtask:
        movie_code = "MIDA-628"

    class FakeContext:
        def __init__(self) -> None:
            self.subtask = FakeSubtask()
            self.provider = RenameNameExistsProvider()
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    renamed = rename_selected_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
            }
        ],
        tags=[],
    )

    assert renamed == [
        {
            "name": "hhd800.com@MIDA-628.mp4",
            "path": "/Downloads/hhd800.com@MIDA-628.mp4",
            "size": 6910439461,
            "renamed_path": "/Downloads/MIDA-628.mp4",
            "renamed_name": "MIDA-628.mp4",
            "rename_name_exists": True,
            "existing_path": "/Downloads/MIDA-628.mp4",
        }
    ]
    assert context.provider.find_calls == ["/Downloads/MIDA-628.mp4"]
    assert any("重命名目标已存在，复用已有文件" in message for message in context.messages)
```

- [ ] **Step 3: Add a test that treats unresolved rename name-exists as a terminal skip**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_rename_name_exists_without_resolved_file_becomes_terminal_skip() -> None:
    from backend.app.modules.storage.worker.steps import move_renamed_videos

    class Provider:
        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            return None

    class Subtask:
        pass

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.subtask = Subtask()
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
                "rename_error": "api error: code: 20004, message: 很抱歉，该目录名称已存在。",
                "rename_name_exists": True,
                "renamed_name": "MIDA-628.mp4",
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
            "rename_error": "api error: code: 20004, message: 很抱歉，该目录名称已存在。",
            "rename_name_exists": True,
            "renamed_name": "MIDA-628.mp4",
            "skip_reason": "rename_name_exists",
        }
    ]
    assert result.all_rename_name_exists is True
    assert any("跳过重命名目标已存在的文件" in message for message in context.messages)
```

- [ ] **Step 4: Add a test that a terminal rename name-exists skip stops later magnets**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_subtask_pipeline_stops_after_rename_name_exists_skip(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet):
        attempt_ids.append(magnet["id"])
        context.subtask.status = "skipped"
        context.subtask.skip_reason = "rename_name_exists"
        context.subtask.result = {"status": "skipped", "reason": "rename_name_exists"}
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
    assert context.subtask.skip_reason == "rename_name_exists"
    assert context.subtask.step == "done"
    assert context.subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert context.subtask.magnet_attempts[0]["success"] is True
    assert context.subtask.magnet_attempts[0]["status"] == "skipped"
```

- [ ] **Step 5: Run the new tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_is_rename_name_exists_error_detects_clouddrive_20004 backend/tests/test_storage_worker_pipeline.py::test_rename_name_exists_reuses_existing_canonical_source_file backend/tests/test_storage_worker_pipeline.py::test_rename_name_exists_without_resolved_file_becomes_terminal_skip backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_rename_name_exists_skip -v
```

Expected: FAIL because `is_rename_name_exists_error` is missing, `rename_selected_videos` treats the `20004` error as generic `rename_error`, and `MoveRenamedVideosResult` does not expose `all_rename_name_exists`.

- [ ] **Step 6: Commit the failing tests**

```bash
git add backend/tests/test_storage_worker_pipeline.py
git commit -m "test: cover storage rename name exists handling"
```

## Task 2: Classify Rename Name-Exists Errors

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Add the rename error classifier**

Add this helper above `rename_selected_videos` in `backend/app/modules/storage/worker/steps.py`:

```python
def is_rename_name_exists_error(error: Exception | str) -> bool:
    message = str(error)
    return (
        "20004" in message
        or "目录名称已存在" in message
        or "名称已存在" in message
        or "already exists" in message.lower()
    )
```

- [ ] **Step 2: Add a helper to find the canonical source path**

Add this helper below `is_rename_name_exists_error`:

```python
def _find_existing_rename_target(provider, path: str):
    try:
        return provider.find_file(path)
    except Exception:
        return None
```

- [ ] **Step 3: Change rename handling for name-exists errors**

In `rename_selected_videos`, replace the current `except Exception as exc` block:

```python
        except Exception as exc:
            context.log("ERROR", f"重命名失败: {video['name']}: {exc}", step="rename_files")
            renamed.append({**video, "rename_error": str(exc)})
```

with:

```python
        except Exception as exc:
            if is_rename_name_exists_error(exc):
                existing = _find_existing_rename_target(context.provider, new_path)
                if existing is not None:
                    renamed.append({
                        **video,
                        "renamed_path": new_path,
                        "renamed_name": new_name,
                        "rename_name_exists": True,
                        "existing_path": new_path,
                    })
                    context.log(
                        "WARNING",
                        f"重命名目标已存在，复用已有文件: {video['name']} → {new_name}",
                        {"source": old_path, "existing_path": new_path},
                        step="rename_files",
                    )
                    continue
                context.log(
                    "WARNING",
                    f"重命名目标已存在但未能定位已有文件: {video['name']} → {new_name}",
                    {"source": old_path, "expected_path": new_path, "error": str(exc)},
                    step="rename_files",
                )
                renamed.append({
                    **video,
                    "rename_error": str(exc),
                    "rename_name_exists": True,
                    "renamed_name": new_name,
                })
                continue

            context.log("ERROR", f"重命名失败: {video['name']}: {exc}", step="rename_files")
            renamed.append({**video, "rename_error": str(exc)})
```

- [ ] **Step 4: Run rename classification tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_is_rename_name_exists_error_detects_clouddrive_20004 backend/tests/test_storage_worker_pipeline.py::test_rename_name_exists_reuses_existing_canonical_source_file -v
```

Expected: PASS.

- [ ] **Step 5: Commit rename classification**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: classify storage rename name conflicts"
```

## Task 3: Make Unresolved Rename Name-Exists Terminal

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Extend the move result dataclass**

In `MoveRenamedVideosResult`, replace:

```python
@dataclass
class MoveRenamedVideosResult:
    moved_files: list[dict]
    skipped_files: list[dict]
    all_targets_exist: bool = False
```

with:

```python
@dataclass
class MoveRenamedVideosResult:
    moved_files: list[dict]
    skipped_files: list[dict]
    all_targets_exist: bool = False
    all_rename_name_exists: bool = False
```

- [ ] **Step 2: Treat unresolved rename name-exists separately from generic rename failures**

In `move_renamed_videos`, replace:

```python
        if file_info.get("rename_error"):
            skipped.append({**file_info, "skip_reason": "rename_failed"})
            context.log("WARNING", f"跳过重命名失败的文件: {file_info['name']}", step="move_files")
            continue
```

with:

```python
        if file_info.get("rename_error"):
            if file_info.get("rename_name_exists"):
                skipped.append({**file_info, "skip_reason": "rename_name_exists"})
                context.log(
                    "WARNING",
                    f"跳过重命名目标已存在的文件: {file_info['name']}",
                    {"rename_error": file_info.get("rename_error"), "renamed_name": file_info.get("renamed_name")},
                    step="move_files",
                )
                continue
            skipped.append({**file_info, "skip_reason": "rename_failed"})
            context.log("WARNING", f"跳过重命名失败的文件: {file_info['name']}", step="move_files")
            continue
```

- [ ] **Step 3: Set the new aggregate flag**

At the end of `move_renamed_videos`, replace:

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

with:

```python
    all_targets_exist = bool(renamed_files) and len(skipped) == len(renamed_files) and all(
        item.get("skip_reason") == "target_exists"
        for item in skipped
    )
    all_rename_name_exists = bool(renamed_files) and len(skipped) == len(renamed_files) and all(
        item.get("skip_reason") == "rename_name_exists"
        for item in skipped
    )
    return MoveRenamedVideosResult(
        moved_files=moved,
        skipped_files=skipped,
        all_targets_exist=all_targets_exist,
        all_rename_name_exists=all_rename_name_exists,
    )
```

- [ ] **Step 4: Run the move result test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_rename_name_exists_without_resolved_file_becomes_terminal_skip -v
```

Expected: PASS.

- [ ] **Step 5: Commit terminal move result metadata**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: mark unresolved rename conflicts as terminal skips"
```

## Task 4: Stop Later Magnets for Rename Name-Exists

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Add terminal skip handling after move results**

In `execute_current_magnet_attempt`, add this block after the existing `if move_result.all_targets_exist:` block and before `if not moved_files:`:

```python
    if move_result.all_rename_name_exists:
        subtask.status = "skipped"
        subtask.skip_reason = "rename_name_exists"
        subtask.result = {
            "status": "skipped",
            "reason": "rename_name_exists",
            "files": skipped_files,
        }
        context.log(
            "INFO",
            "重命名目标已存在，子任务标记为跳过",
            {"skipped_files": skipped_files, "target_paths": target_paths},
            step="move_files",
            event="subtask_skipped",
        )
        context.publish_subtask()
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True
```

The move-result section should contain both terminal skip cases:

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

    if move_result.all_rename_name_exists:
        subtask.status = "skipped"
        subtask.skip_reason = "rename_name_exists"
        subtask.result = {
            "status": "skipped",
            "reason": "rename_name_exists",
            "files": skipped_files,
        }
        context.log(
            "INFO",
            "重命名目标已存在，子任务标记为跳过",
            {"skipped_files": skipped_files, "target_paths": target_paths},
            step="move_files",
            event="subtask_skipped",
        )
        context.publish_subtask()
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True
```

- [ ] **Step 2: Verify the magnet loop preserves skipped status**

Confirm `execute_subtask_pipeline` contains this success branch:

```python
        if success:
            if subtask.status != "skipped":
                subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            context.publish_subtask()
            return
```

If the branch overwrites skipped status with completed, replace it with the code above.

- [ ] **Step 3: Verify the attempt record includes status**

Confirm `execute_subtask_pipeline` creates attempt records with `status`:

```python
        attempt_record = {
            "magnet_id": magnet.get("id"),
            "success": success,
            "status": subtask.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
```

If `status` is missing, replace the attempt record with the code above.

- [ ] **Step 4: Run terminal skip tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_rename_name_exists_without_resolved_file_becomes_terminal_skip backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_rename_name_exists_skip -v
```

Expected: PASS.

- [ ] **Step 5: Commit rename conflict terminal behavior**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: stop storage magnets after rename name conflict"
```

## Task 5: Full Verification

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

- [ ] **Step 2: Verify generic rename failures still fail the current magnet**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_logs_submit_failure -v
```

Expected: PASS. This confirms the plan did not make all failures terminal skips.

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git diff --stat HEAD
git diff -- backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
```

Expected: The diff only changes rename name-conflict handling, terminal skip behavior, and backend tests.

- [ ] **Step 4: Commit verification fixes if files changed**

If Task 5 changed files, run:

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify storage rename name conflict handling"
```

If Task 5 did not change files, do not create a commit.

## Self-Review

- Spec coverage: The plan explains why the attached log shows rename failure and maps the `20004 / 目录名称已存在` error to terminal already-exists handling.
- Behavior boundary: Generic rename failures remain current-magnet failures; only name-exists rename errors stop later magnets.
- Data flow: Resolved canonical source files continue into move/copy. Unresolved name-exists conflicts become skipped subtasks with `skip_reason: rename_name_exists`.
- Test coverage: Tests cover error classification, source-file reuse, unresolved terminal skip, and no later magnet attempt.
