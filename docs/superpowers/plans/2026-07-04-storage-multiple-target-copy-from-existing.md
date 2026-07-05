# Storage Multiple Target Copy From Existing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a storage subtask is in `multiple` mode and one target folder already contains the expected video, copy that found file into the other missing target folders and finish the current magnet without trying later magnets.

**Architecture:** Add a target-folder recovery path to the storage worker after CloudDrive reports an existing magnet task and download-folder recovery finds no usable video. The worker will inspect every target folder with `ListSubFileRequest` through `provider.list_files`, select the first existing expected video as the copy source, copy it to missing targets, verify the copied targets, and return success so the magnet loop stops. The existing all-target-exists branch remains a skip, while partial target recovery in `multiple` mode becomes a completed subtask because it actively fills missing storage locations.

**Tech Stack:** Python 3.12, FastAPI backend modules, SQLAlchemy task models, CloudDrive2 provider gateway, pytest.

---

## File Structure

- Modify `backend/app/modules/storage/worker/steps.py`
  - Add a dataclass describing target-folder scan results.
  - Add `provider.list_files` based target-folder lookup that mirrors CloudDrive2 `ListSubFileRequest` behavior and avoids virtual search paths.
  - Add a helper that copies the first found target video into missing target folders for `multiple` mode.
  - Insert the recovery branch in `execute_current_magnet_attempt()` only after `submit_task_exists` and download recovery returns no files.
- Modify `backend/tests/test_storage_worker_pipeline.py`
  - Add focused tests for partial-target recovery, single-mode non-recovery, all-target skip preservation, verification, and magnet-loop stop behavior.
- No frontend changes are required because the status transitions and EventSource payloads are already driven by subtask persistence and `context.publish_subtask()`.

## Behavior Rules

- If all target folders already contain the expected video, keep the current behavior: mark the subtask `skipped`, set `skip_reason = "target_exists"`, clean the download folder, and stop later magnet attempts.
- If `storage_mode == "multiple"` and at least one target folder contains the expected video while other target folders are missing it, use the found target file as the source and copy it to every missing target folder.
- If the copy-to-missing-targets branch succeeds, set `subtask.result.status = "success"`, keep `subtask.status` ready for the pipeline to become `completed`, clean the download folder, return `True`, and stop later magnet attempts.
- If `storage_mode != "multiple"` and only some targets contain the expected video, do not copy from target to target; return `False` so the next magnet can be tried.
- If no target folder contains the expected video, return `False` so the next magnet can be tried.
- Target-folder lookup must use `provider.list_files(target_folder)` and compare direct child file names. Do not use CloudDrive search virtual paths for this target check.

## Task 1: Add Target Folder Result Types And Lookup Helper

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Write the failing helper test for partial target discovery**

Append this test near the existing storage worker helper tests in `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_find_existing_target_files_reports_source_and_missing_targets() -> None:
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
                return [
                    RemoteFile(
                        name="ACZD-165.mp4",
                        full_path="/Movies/A/ACZD-165/ACZD-165.mp4",
                        size=500 * 1024 * 1024,
                    )
                ]
            if path == "/Movies/B/ACZD-165":
                return []
            return []

    result = find_existing_target_files(
        provider=Provider(),
        target_paths=["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
    )

    assert result.any_target_exists is True
    assert result.all_targets_exist is False
    assert result.checked_targets == ["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"]
    assert result.existing_targets == ["/Movies/A/ACZD-165"]
    assert result.missing_targets == ["/Movies/B/ACZD-165"]
    assert result.source_path == "/Movies/A/ACZD-165/ACZD-165.mp4"
    assert result.source_name == "ACZD-165.mp4"
    assert result.existing_files == [
        {
            "target_folder": "/Movies/A/ACZD-165",
            "path": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "name": "ACZD-165.mp4",
            "size": 500 * 1024 * 1024,
        }
    ]
```

- [ ] **Step 2: Run the helper test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_find_existing_target_files_reports_source_and_missing_targets -q
```

Expected: FAIL with an import error like `cannot import name 'find_existing_target_files'`.

- [ ] **Step 3: Add the result dataclass and lookup helper**

In `backend/app/modules/storage/worker/steps.py`, add this code after `_target_file_path()`:

```python
@dataclass
class ExistingTargetFilesResult:
    all_targets_exist: bool
    any_target_exists: bool
    checked_targets: list[str]
    existing_targets: list[str]
    missing_targets: list[str]
    expected_names: list[str]
    existing_files: list[dict]
    source_path: str | None = None
    source_name: str | None = None
    source_size: int = 0


def _listed_entry_to_target_file(entry) -> dict:
    path = getattr(entry, "full_path", "") or getattr(entry, "fullPathName", "")
    name = getattr(entry, "name", "") or PurePosixPath(path).name
    return {
        "name": name,
        "path": path,
        "size": int(getattr(entry, "size", 0) or 0),
        "is_dir": bool(getattr(entry, "is_directory", False) or getattr(entry, "isDirectory", False)),
    }


def find_existing_target_files(provider, target_paths: list[str], expected_names: list[str]) -> ExistingTargetFilesResult:
    normalized_expected = {str(name).lower() for name in expected_names if name}
    checked_targets: list[str] = []
    existing_targets: list[str] = []
    missing_targets: list[str] = []
    existing_files: list[dict] = []
    source_path: str | None = None
    source_name: str | None = None
    source_size = 0

    for target_folder in target_paths:
        checked_targets.append(target_folder)
        matched_file: dict | None = None
        try:
            entries = provider.list_files(target_folder)
        except Exception:
            entries = []

        for entry in entries:
            item = _listed_entry_to_target_file(entry)
            if item["is_dir"]:
                continue
            if item["size"] <= 0:
                continue
            if item["name"].lower() not in normalized_expected:
                continue
            matched_file = {
                "target_folder": target_folder,
                "path": item["path"] or _target_file_path(target_folder, item["name"]),
                "name": item["name"],
                "size": item["size"],
            }
            break

        if matched_file:
            existing_targets.append(target_folder)
            existing_files.append(matched_file)
            if source_path is None:
                source_path = matched_file["path"]
                source_name = matched_file["name"]
                source_size = int(matched_file["size"] or 0)
            continue

        missing_targets.append(target_folder)

    return ExistingTargetFilesResult(
        all_targets_exist=bool(target_paths) and len(existing_targets) == len(target_paths),
        any_target_exists=bool(existing_targets),
        checked_targets=checked_targets,
        existing_targets=existing_targets,
        missing_targets=missing_targets,
        expected_names=list(expected_names),
        existing_files=existing_files,
        source_path=source_path,
        source_name=source_name,
        source_size=source_size,
    )
```

- [ ] **Step 4: Run the helper test and verify it passes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_find_existing_target_files_reports_source_and_missing_targets -q
```

Expected: PASS.

- [ ] **Step 5: Commit the helper**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: cover existing storage target discovery"
```

Expected: commit succeeds.

## Task 2: Add Copy From Existing Target Helper

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Write the failing copy helper test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_copy_existing_target_to_missing_targets_copies_from_first_found_target() -> None:
    from backend.app.modules.storage.worker.steps import (
        ExistingTargetFilesResult,
        copy_existing_target_to_missing_targets,
    )

    class Provider:
        def __init__(self) -> None:
            self.ensure_calls: list[str] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            self.ensure_calls.append(path)

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()
    result = ExistingTargetFilesResult(
        all_targets_exist=False,
        any_target_exists=True,
        checked_targets=["/Movies/A/ACZD-165", "/Movies/B/ACZD-165", "/Movies/C/ACZD-165"],
        existing_targets=["/Movies/A/ACZD-165"],
        missing_targets=["/Movies/B/ACZD-165", "/Movies/C/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
        existing_files=[
            {
                "target_folder": "/Movies/A/ACZD-165",
                "path": "/Movies/A/ACZD-165/ACZD-165.mp4",
                "name": "ACZD-165.mp4",
                "size": 500 * 1024 * 1024,
            }
        ],
        source_path="/Movies/A/ACZD-165/ACZD-165.mp4",
        source_name="ACZD-165.mp4",
        source_size=500 * 1024 * 1024,
    )

    copied = copy_existing_target_to_missing_targets(context, result)

    assert context.provider.ensure_calls == ["/Movies/B/ACZD-165", "/Movies/C/ACZD-165"]
    assert context.provider.copy_calls == [
        ("/Movies/A/ACZD-165/ACZD-165.mp4", "/Movies/B/ACZD-165"),
        ("/Movies/A/ACZD-165/ACZD-165.mp4", "/Movies/C/ACZD-165"),
    ]
    assert copied == [
        {
            "name": "ACZD-165.mp4",
            "path": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "size": 500 * 1024 * 1024,
            "renamed_name": "ACZD-165.mp4",
            "moved_path": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "copied_paths": ["/Movies/B/ACZD-165/ACZD-165.mp4", "/Movies/C/ACZD-165/ACZD-165.mp4"],
            "copy_source": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "copy_source_target": "/Movies/A/ACZD-165",
        }
    ]
    assert any("已从命中的目标文件复制到缺失目标" in log["message"] for log in context.logs)
```

- [ ] **Step 2: Run the copy helper test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_copy_existing_target_to_missing_targets_copies_from_first_found_target -q
```

Expected: FAIL with an import error like `cannot import name 'copy_existing_target_to_missing_targets'`.

- [ ] **Step 3: Add the copy helper**

In `backend/app/modules/storage/worker/steps.py`, add this code after `find_existing_target_files()`:

```python
def copy_existing_target_to_missing_targets(context, result: ExistingTargetFilesResult) -> list[dict]:
    if not result.source_path or not result.source_name:
        return []
    if not result.missing_targets:
        return []

    copied_paths: list[str] = []
    for target_folder in result.missing_targets:
        ensure_directory_chain(context.provider, target_folder)
        context.provider.copy_file(result.source_path, target_folder)
        copied_paths.append(_target_file_path(target_folder, result.source_name))

    moved_file = {
        "name": result.source_name,
        "path": result.source_path,
        "size": result.source_size,
        "renamed_name": result.source_name,
        "moved_path": result.source_path,
        "copied_paths": copied_paths,
        "copy_source": result.source_path,
        "copy_source_target": result.existing_targets[0] if result.existing_targets else "",
    }
    context.log(
        "INFO",
        "已从命中的目标文件复制到缺失目标",
        {
            "source": result.source_path,
            "source_target": moved_file["copy_source_target"],
            "missing_targets": result.missing_targets,
            "copied_paths": copied_paths,
        },
        step="move_files",
    )
    return [moved_file]
```

- [ ] **Step 4: Run the copy helper test and verify it passes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_copy_existing_target_to_missing_targets_copies_from_first_found_target -q
```

Expected: PASS.

- [ ] **Step 5: Commit the copy helper**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "feat: copy storage target from existing target file"
```

Expected: commit succeeds.

## Task 3: Wire Recovery Branch Into Existing Magnet Attempt

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Write the failing integration test for multiple-mode partial target recovery**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_copies_from_existing_target_when_multiple_mode_partial_targets(monkeypatch):
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
            self.copy_calls: list[tuple[str, str]] = []
            self.ensure_calls: list[str] = []
            self.deleted: list[str] = []
            self.files = {
                "/Movies/A/ACZD-165/ACZD-165.mp4": RemoteFile(
                    "ACZD-165.mp4",
                    "/Movies/A/ACZD-165/ACZD-165.mp4",
                    500 * 1024 * 1024,
                )
            }

        def ensure_directory(self, path):
            self.ensure_calls.append(path)

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("磁力链接已存在 (code 10008)")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Downloads/storage_sub":
                return []
            if path == "/Downloads":
                return []
            if path == "/Movies/A/ACZD-165":
                return [self.files["/Movies/A/ACZD-165/ACZD-165.mp4"]]
            if path == "/Movies/B/ACZD-165":
                return []
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            dest_path = f"{dest_folder}/ACZD-165.mp4"
            self.files[dest_path] = RemoteFile("ACZD-165.mp4", dest_path, 500 * 1024 * 1024)

        def find_file(self, path):
            return self.files.get(path)

        def delete_file(self, path):
            self.deleted.append(path)

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        storage_mode = "multiple"
        target_locations = ["A", "B"]
        selected_storage_location = ""
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "running"
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
            self.publish_count = 0

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            self.publish_count += 1

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
    assert context.subtask.result["status"] == "success"
    assert context.subtask.result["reason"] == "copied_from_existing_target"
    assert context.subtask.moved_files[0]["copy_source"] == "/Movies/A/ACZD-165/ACZD-165.mp4"
    assert context.provider.copy_calls == [
        ("/Movies/A/ACZD-165/ACZD-165.mp4", "/Movies/B/ACZD-165")
    ]
    assert context.provider.find_file("/Movies/B/ACZD-165/ACZD-165.mp4") is not None
    assert context.provider.deleted == ["/Downloads/storage_sub"]
    assert any(log["message"] == "检查目标目录是否已存在视频文件" for log in context.logs)
    assert any(log["message"] == "磁力任务处理成功" for log in context.logs)
```

- [ ] **Step 2: Run the integration test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_copies_from_existing_target_when_multiple_mode_partial_targets -q
```

Expected: FAIL because `execute_current_magnet_attempt()` returns `False` after download recovery finds no file.

- [ ] **Step 3: Add the recovery branch inside `execute_current_magnet_attempt()`**

In `backend/app/modules/storage/worker/steps.py`, replace this block:

```python
    if not found_files:
        context.log("WARNING", "未在下载目录找到可用视频文件", {"magnet_id": magnet.get("id"), "task_download_folder": download_folder, "download_root": download_root}, step="waiting_download")
        return False
```

with this block:

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
            existing_result = find_existing_target_files(provider, target_paths, expected_names)
            context.log(
                "INFO",
                "检查目标目录是否已存在视频文件",
                {
                    "search_method": "list_sub_files",
                    "storage_mode": getattr(subtask, "storage_mode", ""),
                    "expected_names": expected_names,
                    "checked_targets": existing_result.checked_targets,
                    "existing_targets": existing_result.existing_targets,
                    "missing_targets": existing_result.missing_targets,
                    "source_path": existing_result.source_path,
                    "existing_files": existing_result.existing_files,
                },
                step="waiting_download",
            )
            if existing_result.all_targets_exist:
                subtask.status = "skipped"
                subtask.skip_reason = "target_exists"
                subtask.moved_files = []
                subtask.skipped_files = [
                    {
                        "name": existing_result.source_name or preview_name,
                        "skip_reason": "target_exists",
                        "existing_targets": [
                            item["path"]
                            for item in existing_result.existing_files
                        ],
                    }
                ]
                subtask.result = {
                    "status": "skipped",
                    "reason": "target_exists",
                    "files": subtask.skipped_files,
                }
                context.log(
                    "INFO",
                    "目标文件已全部存在，子任务标记为跳过",
                    {"skipped_files": subtask.skipped_files, "target_paths": target_paths},
                    step="move_files",
                    event="subtask_skipped",
                )
                context.publish_subtask()
                context.set_step("cleanup_files")
                cleanup_download_folder(context, download_folder, config)
                return True

            if getattr(subtask, "storage_mode", "") == "multiple" and existing_result.any_target_exists:
                copied_files = copy_existing_target_to_missing_targets(context, existing_result)
                subtask.renamed_files = []
                subtask.moved_files = copied_files
                subtask.skipped_files = []
                context.publish_subtask()
                context.set_step("verify_result")
                if not verify_moved_files(context, copied_files):
                    return False
                context.set_step("cleanup_files")
                cleanup_download_folder(context, download_folder, config)
                subtask.result = {
                    "status": "success",
                    "reason": "copied_from_existing_target",
                    "files": copied_files,
                    "existing_targets": existing_result.existing_targets,
                    "missing_targets": existing_result.missing_targets,
                }
                context.log(
                    "INFO",
                    "磁力任务处理成功",
                    {"magnet_id": magnet.get("id"), "files": copied_files, "reason": "copied_from_existing_target"},
                    step="cleanup_files",
                    event="magnet_success",
                )
                context.publish_subtask()
                return True
        return False
```

- [ ] **Step 4: Run the integration test and verify it passes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_copies_from_existing_target_when_multiple_mode_partial_targets -q
```

Expected: PASS.

- [ ] **Step 5: Commit the recovery branch**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "feat: recover multiple storage targets from existing target"
```

Expected: commit succeeds.

## Task 4: Preserve Single Mode And All-Target Semantics

**Files:**
- Modify: `backend/tests/test_storage_worker_pipeline.py`
- Modify if needed: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Write the single-mode guard test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_current_magnet_attempt_does_not_copy_between_targets_in_single_mode(monkeypatch):
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
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("磁力链接已存在 (code 10008)")

        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/ACZD-165":
                return [RemoteFile("ACZD-165.mp4", "/Movies/A/ACZD-165/ACZD-165.mp4", 500 * 1024 * 1024)]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))

        def find_file(self, path):
            return None

        def delete_file(self, path):
            return None

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        storage_mode = "single"
        target_locations = ["A", "B"]
        selected_storage_location = ""
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "running"
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
    assert context.provider.copy_calls == []
    assert context.subtask.result == {}
```

- [ ] **Step 2: Run the single-mode guard test**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_does_not_copy_between_targets_in_single_mode -q
```

Expected: PASS. If it fails because the code copies in `single` mode, change the branch condition to exactly `getattr(subtask, "storage_mode", "") == "multiple" and existing_result.any_target_exists`.

- [ ] **Step 3: Run the existing all-target skip test**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_current_magnet_attempt_marks_subtask_skipped_when_all_targets_exist -q
```

Expected: PASS.

- [ ] **Step 4: Run the existing pipeline stop-after-skip test**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_target_exists_skip -q
```

Expected: PASS.

- [ ] **Step 5: Commit semantic preservation tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: preserve storage target skip semantics"
```

Expected: commit succeeds.

## Task 5: Ensure Later Magnets Stop After Partial Target Copy

**Files:**
- Modify: `backend/tests/test_storage_worker_pipeline.py`
- Modify if needed: `backend/app/modules/storage/worker/steps.py`

- [ ] **Step 1: Write the pipeline stop test for target-copy completion**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_execute_subtask_pipeline_stops_after_existing_target_copy_success(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet):
        attempt_ids.append(magnet["id"])
        context.subtask.result = {"status": "success", "reason": "copied_from_existing_target"}
        context.subtask.moved_files = [
            {
                "name": "ACZD-165.mp4",
                "moved_path": "/Movies/A/ACZD-165/ACZD-165.mp4",
                "copied_paths": ["/Movies/B/ACZD-165/ACZD-165.mp4"],
            }
        ]
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
        moved_files: list | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []
            if self.result is None:
                self.result = {}
            if self.moved_files is None:
                self.moved_files = []

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
    assert context.subtask.status == "completed"
    assert context.subtask.step == "done"
    assert context.subtask.result == {"status": "success", "reason": "copied_from_existing_target"}
    assert context.subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert context.subtask.magnet_attempts[0]["success"] is True
    assert context.subtask.magnet_attempts[0]["status"] == "running"
```

- [ ] **Step 2: Run the pipeline stop test**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_stops_after_existing_target_copy_success -q
```

Expected: PASS because `execute_subtask_pipeline()` already stops after any successful magnet and sets `completed` when the subtask is not `skipped`. The attempt record status is `running` because the worker records the attempt before it assigns the final `completed` status.

- [ ] **Step 3: Run focused storage worker tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py -q
```

Expected: PASS for the full storage worker pipeline test file.

- [ ] **Step 4: Commit pipeline stop coverage**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: stop storage magnet loop after target copy"
```

Expected: commit succeeds.

## Task 6: Final Verification

**Files:**
- Verify: `backend/app/modules/storage/worker/steps.py`
- Verify: `backend/tests/test_storage_worker_pipeline.py`
- Verify: `backend/tests/test_storage_file_finder_scope.py`
- Verify: `backend/tests/test_storage_worker_service.py`

- [ ] **Step 1: Run storage worker and finder tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_worker_pipeline.py \
  backend/tests/test_storage_file_finder_scope.py \
  backend/tests/test_storage_worker_service.py \
  -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Inspect logs in a manual dev run**

Start the backend and submit a storage task that reproduces this state:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Expected storage subtask logs contain these messages in order after CloudDrive returns code `10008` and no download-folder files are found:

```text
磁力链接已存在 (code 10008)，搜索现有下载中
未在下载目录找到可用视频文件
检查目标目录是否已存在视频文件
已从命中的目标文件复制到缺失目标
验证通过: 所有文件完整 (含复制目标)
已清理下载目录
清理完成
磁力任务处理成功
```

- [ ] **Step 3: Confirm no later magnet is submitted**

Use the same manual dev run and inspect the subtask logs.

Expected: after `磁力任务处理成功`, the subtask reaches `done`, and there is no second `准备提交磁力到 CloudDrive2` log for the same subtask.

- [ ] **Step 4: Commit final verification notes if code changed during verification**

Run only if verification required code or test changes:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: verify storage target copy recovery"
```

Expected: commit succeeds when there are staged verification fixes. If no files changed, `git status --short` shows no new changes from this plan.

## Self-Review

- Spec coverage: The plan covers multi-target tasks, `multiple` storage mode, using the first found target as the copy source, copying only to missing target folders, skipping when all targets already contain the video, and stopping later magnet attempts after the recovery succeeds.
- Scope control: The plan stays inside the storage worker and tests. It does not change frontend EventSource code, storage task schemas, or unrelated crawler behavior.
- Type consistency: `ExistingTargetFilesResult`, `find_existing_target_files()`, and `copy_existing_target_to_missing_targets()` are defined before use. The result fields used by integration code match the helper tests.
- Failure behavior: If no target contains the expected file, or if the mode is not `multiple`, the current magnet returns `False` and the existing magnet ordering logic tries the next candidate.
- Verification coverage: Unit tests cover helper behavior, integration into `execute_current_magnet_attempt()`, skip preservation, and magnet-loop stop semantics.

## Execution Options

1. Subagent-Driven (recommended) - Use `superpowers:subagent-driven-development` to dispatch one fresh worker per task, then review between tasks.
2. Inline Execution - Use `superpowers:executing-plans` to execute this plan in the current session with checkpoints.
