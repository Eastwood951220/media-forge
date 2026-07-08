# Cohesion Coupling Follow-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve cohesion and reduce coupling in the remaining storage worker, crawler task router, frontend realtime pages, TagsView, and request transform code without changing behavior.

**Architecture:** Execute four sequential phases: backend storage worker first, crawler task router second, frontend realtime pages third, frontend shell/request infrastructure last. Each phase moves behavior into focused same-domain modules behind stable interfaces, keeps facades only where existing imports require them, and verifies behavior before and after extraction.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, Vitest, React Testing Library, Axios.

## Global Constraints

- No database schema or Alembic migration changes.
- No new API endpoints or response shape changes.
- No route, sidebar, visual layout, or Ant Design component redesign.
- No new state management or request libraries.
- No storage provider behavior changes.
- No crawler scraping behavior changes.
- Existing API paths and frontend routes must remain unchanged.
- Existing event names and realtime subscription semantics must remain unchanged.
- Do not stage unrelated historical plan/spec files.

---

## File Structure

### Create

- `backend/app/modules/storage/worker/rename_ops.py`
  - Owns rename-name-exists detection and selected video rename behavior.
- `backend/app/modules/storage/worker/move_ops.py`
  - Owns move/copy target helpers, `MoveRenamedVideosResult`, and moved file creation.
- `backend/app/modules/storage/worker/verify_ops.py`
  - Owns moved/copied file verification.
- `backend/app/modules/storage/worker/cleanup_ops.py`
  - Owns download folder cleanup.
- `backend/app/modules/storage/worker/target_planning.py`
  - Owns download folder and target path planning for one magnet attempt.
- `backend/app/modules/storage/worker/attempts.py`
  - Owns magnet candidate conversion, ordering, and attempt record append.
- `backend/app/modules/storage/worker/provider_session.py`
  - Owns CloudDrive2 provider open/close and provider creation failure state.
- `backend/app/modules/storage/worker/movie_sync.py`
  - Owns movie storage status synchronization after subtask completion/failure/skip.
- `backend/app/modules/storage/worker/task_processor.py`
  - Owns processing one storage main task and iterating queued subtasks.
- `backend/app/modules/crawler/tasks/serializers.py`
  - Owns crawler task read serialization.
- `backend/app/modules/crawler/tasks/validation.py`
  - Owns crawler task URL/name/delete-mode validation helpers.
- `backend/app/modules/crawler/tasks/errors.py`
  - Owns crawler task integrity error translation.
- `backend/app/modules/crawler/tasks/name_extractor.py`
  - Owns `/extract-name` scraping and search URL parsing.
- `backend/app/modules/crawler/tasks/provider.py`
  - Owns optional cloud cleanup provider session for crawler task deletion.
- `backend/app/modules/crawler/tasks/service.py`
  - Owns crawler task application service methods.
- `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
- `frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx`
- `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
- `frontend/src/pages/crawler/runs/utils/status.ts`
- `frontend/src/pages/crawler/tasks/hooks/useTaskListData.ts`
- `frontend/src/pages/crawler/tasks/hooks/useTaskListRealtime.ts`
- `frontend/src/pages/crawler/tasks/utils/runtimeStats.ts`
- `frontend/src/pages/storage/tasks/hooks/useStorageTaskDetail.ts`
- `frontend/src/pages/storage/tasks/hooks/useStorageTaskDetailRealtime.ts`
- `frontend/src/pages/storage/tasks/hooks/useStorageTaskList.ts`
- `frontend/src/pages/storage/tasks/hooks/useStorageTaskListRealtime.ts`
- `frontend/src/pages/storage/tasks/components/StorageMainSummaryCard.tsx`
- `frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx`
- `frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx`
- `frontend/src/pages/storage/tasks/utils/status.ts`
- `frontend/src/layout/TagsView/components/TagsBar.tsx`
- `frontend/src/layout/TagsView/components/TagsContextMenu.tsx`
- `frontend/src/layout/TagsView/hooks/useTagsContextMenu.ts`
- `frontend/src/layout/TagsView/hooks/useTagsViewActions.ts`
- `frontend/src/layout/TagsView/hooks/useTagsViewRegistration.ts`
- `frontend/src/layout/TagsView/tagsViewUtils.ts`
- `frontend/src/layout/TagsView/__tests__/tagsViewUtils.test.ts`
- `frontend/src/request/session.ts`
- `frontend/src/request/businessError.ts`
- `frontend/src/request/networkError.ts`
- `frontend/src/request/responseTransform.ts`
- `frontend/src/request/__tests__/transform.test.ts`

### Modify

- `backend/app/modules/storage/worker/file_ops.py`
  - Convert to a compatibility facade or delete after imports are rewired.
- `backend/app/modules/storage/worker/steps.py`
  - Import focused storage worker helpers and delegate planning/attempt logic.
- `backend/app/modules/storage/worker/runner.py`
  - Keep worker lifecycle and delegate one-task processing.
- `backend/tests/test_storage_worker_pipeline.py`
  - Add focused regression tests for extracted file operation modules.
- `backend/tests/test_storage_worker_service.py`
  - Add focused regression tests for task processor/provider/movie sync extraction.
- `backend/app/modules/crawler/tasks/router.py`
  - Keep FastAPI HTTP boundary only.
- `backend/tests/test_crawler_tasks_api.py`
  - Add if missing, or create this file for crawler task router behavior regressions.
- `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`
- `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`
- `frontend/src/layout/TagsView/index.tsx`
- `frontend/src/request/transform.ts`

---

### Task 1: Split Storage File Operations

**Files:**
- Create: `backend/app/modules/storage/worker/rename_ops.py`
- Create: `backend/app/modules/storage/worker/move_ops.py`
- Create: `backend/app/modules/storage/worker/verify_ops.py`
- Create: `backend/app/modules/storage/worker/cleanup_ops.py`
- Modify: `backend/app/modules/storage/worker/file_ops.py`
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Produces:
  - `rename_ops.is_rename_name_exists_error(error: Exception | str) -> bool`
  - `rename_ops.rename_selected_videos(context, selected_videos: list[dict], tags: list[str]) -> list[dict]`
  - `move_ops.MoveRenamedVideosResult`
  - `move_ops.move_renamed_videos(context, renamed_files: list[dict], target_paths: list[str]) -> MoveRenamedVideosResult`
  - `verify_ops.verify_moved_files(context, moved_files: list[dict]) -> bool`
  - `cleanup_ops.cleanup_download_folder(context, download_folder: str, config: dict) -> None`
  - `file_ops.py` facade exports the same public names used before this task.

- [ ] **Step 1: Add file operation module regression tests**

Append to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_storage_file_operation_modules_export_current_public_functions() -> None:
    from backend.app.modules.storage.worker import cleanup_ops, file_ops, move_ops, rename_ops, verify_ops

    assert rename_ops.is_rename_name_exists_error("名称已存在")
    assert callable(rename_ops.rename_selected_videos)
    assert callable(move_ops.move_renamed_videos)
    assert callable(verify_ops.verify_moved_files)
    assert callable(cleanup_ops.cleanup_download_folder)
    assert file_ops.rename_selected_videos is rename_ops.rename_selected_videos
    assert file_ops.move_renamed_videos is move_ops.move_renamed_videos
    assert file_ops.verify_moved_files is verify_ops.verify_moved_files
    assert file_ops.cleanup_download_folder is cleanup_ops.cleanup_download_folder
```

- [ ] **Step 2: Run the new regression and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py::test_storage_file_operation_modules_export_current_public_functions -v
```

Expected: FAIL with `ImportError` for one of the new modules.

- [ ] **Step 3: Move rename functions**

Create `backend/app/modules/storage/worker/rename_ops.py` by moving these definitions from `file_ops.py` without behavior changes:

```python
is_rename_name_exists_error
_find_existing_rename_target
rename_selected_videos
```

Keep these imports in `rename_ops.py`:

```python
from __future__ import annotations

from pathlib import PurePosixPath
```

- [ ] **Step 4: Move move functions and result type**

Create `backend/app/modules/storage/worker/move_ops.py` by moving these definitions from `file_ops.py` without behavior changes:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from backend.app.modules.storage.worker.target_files import ensure_directory_chain

_target_file_exists
_move_source_path
_move_file_name
_target_file_path
MoveRenamedVideosResult
move_renamed_videos
```

- [ ] **Step 5: Move verify and cleanup functions**

Create `backend/app/modules/storage/worker/verify_ops.py` with `verify_moved_files` moved unchanged from `file_ops.py` and imports:

```python
from __future__ import annotations

from pathlib import PurePosixPath
```

Create `backend/app/modules/storage/worker/cleanup_ops.py` with `cleanup_download_folder` moved unchanged from `file_ops.py` and imports:

```python
from __future__ import annotations
```

- [ ] **Step 6: Convert `file_ops.py` to facade for moved functions**

Keep `select_main_videos`, `target_files_exist`, and `scan_found_files` in `file_ops.py`. Delete the moved implementations and import/re-export them:

```python
from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.move_ops import MoveRenamedVideosResult, move_renamed_videos
from backend.app.modules.storage.worker.rename_ops import is_rename_name_exists_error, rename_selected_videos
from backend.app.modules.storage.worker.verify_ops import verify_moved_files
```

- [ ] **Step 7: Rewire `steps.py` imports**

In `backend/app/modules/storage/worker/steps.py`, replace the `file_ops` imports for moved functions:

```python
from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.move_ops import move_renamed_videos
from backend.app.modules.storage.worker.rename_ops import rename_selected_videos
from backend.app.modules.storage.worker.verify_ops import verify_moved_files
from backend.app.modules.storage.worker.file_ops import scan_found_files
```

- [ ] **Step 8: Run storage worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py tests/test_storage_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 9: Verify no duplicated moved definitions remain in `file_ops.py`**

Run:

```bash
rg -n "^def (is_rename_name_exists_error|_find_existing_rename_target|rename_selected_videos|_target_file_exists|_move_source_path|_move_file_name|_target_file_path|move_renamed_videos|verify_moved_files|cleanup_download_folder)|^class MoveRenamedVideosResult" backend/app/modules/storage/worker/file_ops.py
```

Expected: no output.

- [ ] **Step 10: Commit**

```bash
git add backend/app/modules/storage/worker/rename_ops.py backend/app/modules/storage/worker/move_ops.py backend/app/modules/storage/worker/verify_ops.py backend/app/modules/storage/worker/cleanup_ops.py backend/app/modules/storage/worker/file_ops.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "refactor: split storage file operations"
```

---

### Task 2: Extract Storage Target Planning And Magnet Attempts

**Files:**
- Create: `backend/app/modules/storage/worker/target_planning.py`
- Create: `backend/app/modules/storage/worker/attempts.py`
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Produces:
  - `target_planning.StorageAttemptPlan`
  - `target_planning.plan_storage_attempt(subtask, config: dict, magnet: dict) -> StorageAttemptPlan`
  - `attempts.magnet_dicts_from_movie(movie) -> list[dict]`
  - `attempts.ordered_magnet_attempts(movie, max_attempts: int) -> list[dict]`
  - `attempts.append_magnet_attempt(subtask, magnet: dict, success: bool) -> None`

- [ ] **Step 1: Add planning and attempt tests**

Append to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_plan_storage_attempt_uses_selected_storage_location() -> None:
    import uuid
    from types import SimpleNamespace
    from backend.app.modules.storage.worker.target_planning import plan_storage_attempt

    subtask = SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000123"),
        movie_code="ABC-123",
        target_locations=["A", "B"],
        selected_storage_location="B",
        download_path="",
        target_paths=[],
    )

    plan = plan_storage_attempt(
        subtask,
        {"download_root_folder": "/Downloads", "target_folder": "/Movies"},
        {"id": "m1", "tags": ["中字"]},
    )

    assert plan.download_folder == "/Downloads/storage_00000000-0000-0000-0000-000000000123"
    assert plan.target_paths == ["/Movies/B/ABC-123"]
    assert subtask.download_path == plan.download_folder
    assert subtask.target_paths == plan.target_paths


def test_append_magnet_attempt_records_status_and_success() -> None:
    from types import SimpleNamespace
    from backend.app.modules.storage.worker.attempts import append_magnet_attempt

    subtask = SimpleNamespace(status="running", magnet_attempts=None)

    append_magnet_attempt(subtask, {"id": "m1"}, success=False)

    assert subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert subtask.magnet_attempts[0]["success"] is False
    assert subtask.magnet_attempts[0]["status"] == "running"
```

- [ ] **Step 2: Run the new tests and verify they fail**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_uses_selected_storage_location tests/test_storage_worker_pipeline.py::test_append_magnet_attempt_records_status_and_success -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `target_planning.py`**

Create `backend/app/modules/storage/worker/target_planning.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from backend.app.modules.storage.tasks.policies import build_video_filename, code_folder_from_filename


@dataclass(frozen=True)
class StorageAttemptPlan:
    download_root: str
    download_folder: str
    preview_name: str
    code_folder: str
    target_root: str
    target_paths: list[str]


def plan_storage_attempt(subtask, config: dict, magnet: dict) -> StorageAttemptPlan:
    tags = list(magnet.get("tags") or [])
    download_root = config.get("download_root_folder", "/Downloads")
    download_folder = f"{download_root}/storage_{subtask.id}"
    preview_name = build_video_filename(subtask.movie_code, f"{subtask.movie_code}.mp4", tags, 0, 1)
    code_folder = code_folder_from_filename(preview_name)
    target_root = config.get("target_folder", "/Movies")
    target_locations = list(subtask.target_locations or [])
    selected_location = getattr(subtask, "selected_storage_location", None) or ""
    if selected_location:
        target_paths = [f"{target_root}/{selected_location}/{code_folder}"]
    else:
        target_paths = [f"{target_root}/{location}/{code_folder}" for location in target_locations] or [f"{target_root}/{code_folder}"]
    subtask.download_path = download_folder
    subtask.target_paths = target_paths
    return StorageAttemptPlan(
        download_root=download_root,
        download_folder=download_folder,
        preview_name=preview_name,
        code_folder=code_folder,
        target_root=target_root,
        target_paths=target_paths,
    )
```

- [ ] **Step 4: Create `attempts.py`**

Create `backend/app/modules/storage/worker/attempts.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from backend.app.modules.storage.tasks.policies import order_magnet_candidates


def magnet_dicts_from_movie(movie) -> list[dict]:
    return [
        {
            "id": str(m.id),
            "magnet_url": m.magnet_url,
            "tags": list(m.tags or []),
            "weight": m.weight,
            "selected": m.selected,
        }
        for m in (movie.magnets or [])
        if m.magnet_url
    ]


def ordered_magnet_attempts(movie, max_attempts: int) -> list[dict]:
    return order_magnet_candidates(magnet_dicts_from_movie(movie), max_attempts)


def append_magnet_attempt(subtask, magnet: dict, success: bool) -> None:
    attempt_record = {
        "magnet_id": magnet.get("id"),
        "success": success,
        "status": subtask.status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    attempts = list(subtask.magnet_attempts or [])
    attempts.append(attempt_record)
    subtask.magnet_attempts = attempts
```

- [ ] **Step 5: Rewire `steps.py` planning and attempt logic**

In `execute_current_magnet_attempt`, replace the inline download/target planning block with:

```python
    plan = plan_storage_attempt(subtask, config, magnet)
    download_root = plan.download_root
    download_folder = plan.download_folder
    preview_name = plan.preview_name
    target_paths = plan.target_paths
```

Keep the existing prepare log message, using these values.

In `execute_subtask_pipeline`, replace inline magnet dict creation and ordering with:

```python
    ordered = ordered_magnet_attempts(movie, int(config.get("magnet_max_attempts_per_subtask", 3)))
```

Replace inline attempt record appending with:

```python
        append_magnet_attempt(subtask, magnet, success)
```

Add imports:

```python
from backend.app.modules.storage.worker.attempts import append_magnet_attempt, ordered_magnet_attempts
from backend.app.modules.storage.worker.target_planning import plan_storage_attempt
```

- [ ] **Step 6: Run storage worker pipeline tests**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/storage/worker/target_planning.py backend/app/modules/storage/worker/attempts.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "refactor: extract storage attempt planning"
```

---

### Task 3: Extract Storage Provider Session And Movie Sync

**Files:**
- Create: `backend/app/modules/storage/worker/provider_session.py`
- Create: `backend/app/modules/storage/worker/movie_sync.py`
- Modify: `backend/app/modules/storage/worker/runner.py`
- Modify: `backend/tests/test_storage_worker_service.py`

**Interfaces:**
- Produces:
  - `provider_session.open_storage_provider(provider_factory, config: dict)`
  - `provider_session.close_storage_provider(client) -> None`
  - `provider_session.mark_provider_creation_failed(subtask, main_task_id: str, error: Exception) -> None`
  - `movie_sync.sync_movie_storage_after_subtask(db: Session, context) -> None`

- [ ] **Step 1: Add provider session import regression**

Append to `backend/tests/test_storage_worker_service.py`:

```python
def test_storage_provider_session_closes_client() -> None:
    from backend.app.modules.storage.worker.provider_session import close_storage_provider

    class Client:
        closed = False

        def close(self):
            self.closed = True

    client = Client()
    close_storage_provider(client)
    assert client.closed is True
```

- [ ] **Step 2: Add movie sync import regression**

Append to `backend/tests/test_storage_worker_service.py`:

```python
def test_movie_sync_module_exports_worker_sync_function() -> None:
    from backend.app.modules.storage.worker.movie_sync import sync_movie_storage_after_subtask

    assert callable(sync_movie_storage_after_subtask)
```

- [ ] **Step 3: Run new regressions and verify they fail**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_service.py::test_storage_provider_session_closes_client tests/test_storage_worker_service.py::test_movie_sync_module_exports_worker_sync_function -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create `provider_session.py`**

Create `backend/app/modules/storage/worker/provider_session.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway


def open_storage_provider(provider_factory, config: dict):
    client = provider_factory.create(config)
    return client, CloudDrive2Gateway(client)


def close_storage_provider(client) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def mark_provider_creation_failed(subtask, main_task_id: str, error: Exception) -> None:
    subtask.status = "failed"
    subtask.error_message = f"创建 CloudDrive2 客户端失败: {error}"
    subtask.finished_at = datetime.now(timezone.utc)
    write_storage_subtask_log(
        str(subtask.id),
        "ERROR",
        f"创建 CloudDrive2 客户端失败: {error}",
        {"main_task_id": main_task_id},
    )
```

- [ ] **Step 5: Create `movie_sync.py`**

Move `_sync_movie_storage_after_subtask` from `runner.py` to `backend/app/modules/storage/worker/movie_sync.py` and rename it to:

```python
def sync_movie_storage_after_subtask(db: Session, context) -> None:
```

Keep its current body and imports, including:

```python
from sqlalchemy.orm import Session
```

- [ ] **Step 6: Rewire `runner.py`**

In `backend/app/modules/storage/worker/runner.py`, import:

```python
from backend.app.modules.storage.worker.movie_sync import sync_movie_storage_after_subtask
from backend.app.modules.storage.worker.provider_session import (
    close_storage_provider,
    mark_provider_creation_failed,
    open_storage_provider,
)
```

Replace provider creation block with:

```python
            try:
                client, provider = open_storage_provider(provider_factory, config)
            except Exception as exc:
                mark_provider_creation_failed(subtask, str(main_task.id), exc)
                has_failure = True
                _publish_main_with_recomputed_counts(db, repository, main_task)
                continue
```

Replace `_sync_movie_storage_after_subtask(db, context)` calls with:

```python
                sync_movie_storage_after_subtask(db, context)
```

Replace inline client close block with:

```python
            close_storage_provider(client)
```

Delete `_sync_movie_storage_after_subtask` from `runner.py`.

- [ ] **Step 7: Run storage worker service tests**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Verify runner no longer owns provider gateway or movie sync imports**

```bash
rg -n "CloudDrive2Gateway|sync_movie_storage_status|set_movie_storage_status|publish_movie_storage_updated|target_folder_specs_from_subtask" backend/app/modules/storage/worker/runner.py
```

Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/worker/provider_session.py backend/app/modules/storage/worker/movie_sync.py backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_service.py
git commit -m "refactor: extract storage provider and movie sync"
```

---

### Task 4: Extract Storage Main Task Processor

**Files:**
- Create: `backend/app/modules/storage/worker/task_processor.py`
- Modify: `backend/app/modules/storage/worker/runner.py`
- Modify: `backend/tests/test_storage_worker_service.py`

**Interfaces:**
- Produces:
  - `task_processor.publish_main_with_recomputed_counts(db: Session, repository, main_task: StorageMainTask) -> None`
  - `task_processor.process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool`
  - `runner.process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool` remains as a compatibility wrapper around `task_processor.process_main_task`.

- [ ] **Step 1: Add processor facade regression**

Append to `backend/tests/test_storage_worker_service.py`:

```python
def test_runner_process_main_task_delegates_to_task_processor(monkeypatch) -> None:
    from backend.app.modules.storage.worker import runner

    calls: list[str] = []

    def fake_process(runtime, provider_factory, config_service, task_id: str) -> bool:
        calls.append(task_id)
        return True

    monkeypatch.setattr("backend.app.modules.storage.worker.task_processor.process_main_task", fake_process, raising=False)

    result = runner.process_main_task(object(), object(), object(), "main-1")

    assert result is True
    assert calls == ["main-1"]
```

- [ ] **Step 2: Run the new regression and verify it fails**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_service.py::test_runner_process_main_task_delegates_to_task_processor -v
```

Expected: FAIL because `task_processor` does not exist.

- [ ] **Step 3: Create `task_processor.py`**

Move these definitions from `runner.py` to `backend/app/modules/storage/worker/task_processor.py`:

```python
_publish_main_with_recomputed_counts -> publish_main_with_recomputed_counts
process_main_task
```

Update internal calls from `_publish_main_with_recomputed_counts(db, repository, main_task)` to:

```python
publish_main_with_recomputed_counts(db, repository, main_task)
```

Keep imports required by the moved function:

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.context import StorageWorkerContext
from backend.app.modules.storage.worker.movie_sync import sync_movie_storage_after_subtask
from backend.app.modules.storage.worker.provider_session import (
    close_storage_provider,
    mark_provider_creation_failed,
    open_storage_provider,
)
```

- [ ] **Step 4: Convert runner processor function to wrapper**

In `backend/app/modules/storage/worker/runner.py`, delete the large `process_main_task` body and replace it with:

```python
def process_main_task(runtime, provider_factory, config_service, task_id: str) -> bool:
    from backend.app.modules.storage.worker.task_processor import process_main_task as process

    return process(runtime, provider_factory, config_service, task_id)
```

Keep `_worker_loop` calling `process_main_task` so current monkeypatch tests keep working.

- [ ] **Step 5: Run storage worker service tests**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 6: Verify runner is lifecycle-only**

```bash
rg -n "StorageWorkerContext|execute_subtask_pipeline|CloudDrive2Gateway|sync_movie_storage|recompute_counts|write_storage_subtask_log" backend/app/modules/storage/worker/runner.py
```

Expected: no output except an allowed import marked `# noqa: F401` if still needed by historical import compatibility. Remove that compatibility import if no tests or runtime references require it.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/storage/worker/task_processor.py backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_service.py
git commit -m "refactor: extract storage task processor"
```

---

### Task 5: Extract Crawler Task Router Helpers

**Files:**
- Create: `backend/app/modules/crawler/tasks/serializers.py`
- Create: `backend/app/modules/crawler/tasks/validation.py`
- Create: `backend/app/modules/crawler/tasks/errors.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Create: `backend/tests/test_crawler_tasks_api.py` if it does not exist.

**Interfaces:**
- Produces:
  - `serialize_task(task, latest_run=None) -> CrawlTaskRead`
  - `check_urls_unique(urls) -> None`
  - `ensure_delete_mode_supported(mode: str) -> None`
  - `constraint_name_from_integrity_error(exc: IntegrityError) -> str`
  - `raise_task_integrity_error(exc: IntegrityError, *, name: str | None = None) -> None`

- [ ] **Step 1: Add helper import regression**

Create or append `backend/tests/test_crawler_tasks_api.py`:

```python
import pytest
from fastapi import HTTPException


def test_crawler_task_helper_modules_export_public_helpers() -> None:
    from backend.app.modules.crawler.tasks import errors, serializers, validation

    assert callable(serializers.serialize_task)
    assert callable(validation.check_urls_unique)
    assert callable(validation.ensure_delete_mode_supported)
    assert callable(errors.constraint_name_from_integrity_error)
    assert callable(errors.raise_task_integrity_error)


def test_check_urls_unique_rejects_duplicate_url() -> None:
    from types import SimpleNamespace
    from backend.app.modules.crawler.tasks.validation import check_urls_unique

    with pytest.raises(HTTPException) as exc:
        check_urls_unique([SimpleNamespace(url="https://example.test/a"), SimpleNamespace(url="https://example.test/a")])

    assert exc.value.status_code == 400
    assert "URL 重复" in exc.value.detail
```

- [ ] **Step 2: Run new tests and verify they fail**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_tasks_api.py::test_crawler_task_helper_modules_export_public_helpers tests/test_crawler_tasks_api.py::test_check_urls_unique_rejects_duplicate_url -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Create `serializers.py`**

Move `_serialize` from `router.py` to `backend/app/modules/crawler/tasks/serializers.py` and rename:

```python
from __future__ import annotations

from backend.app.schemas.crawl_task import CrawlTaskRead


def serialize_task(task, latest_run=None) -> CrawlTaskRead:
    data = CrawlTaskRead.model_validate(task)
    data._id = data.id
    if latest_run is not None:
        data.last_run_at = latest_run.created_at
        data.last_run_status = latest_run.status
    return data
```

- [ ] **Step 4: Create `validation.py`**

Move `_check_urls_unique` from `router.py` to `backend/app/modules/crawler/tasks/validation.py` and rename:

```python
from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.modules.crawler.tasks.delete_service import VALID_DELETE_MODES


def check_urls_unique(urls) -> None:
    seen: set[str] = set()
    for entry in urls:
        if entry.url in seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"URL 重复: {entry.url}")
        seen.add(entry.url)


def ensure_delete_mode_supported(mode: str) -> None:
    if mode not in VALID_DELETE_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid delete mode: {mode}. Valid modes: {', '.join(VALID_DELETE_MODES)}",
        )
```

- [ ] **Step 5: Create `errors.py`**

Move `_constraint_name_from_integrity_error` and `_raise_task_integrity_error` from `router.py` to `backend/app/modules/crawler/tasks/errors.py`, renaming them to:

```python
constraint_name_from_integrity_error
raise_task_integrity_error
```

Keep existing status codes, messages, and logging behavior. Add imports:

```python
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)
```

- [ ] **Step 6: Rewire router imports and calls**

In `backend/app/modules/crawler/tasks/router.py`:

```python
from backend.app.modules.crawler.tasks.errors import raise_task_integrity_error
from backend.app.modules.crawler.tasks.serializers import serialize_task
from backend.app.modules.crawler.tasks.validation import check_urls_unique, ensure_delete_mode_supported
```

Replace:

```python
_serialize(task, latest_run) -> serialize_task(task, latest_run)
_check_urls_unique(data.urls) -> check_urls_unique(data.urls)
_raise_task_integrity_error(exc, name=name) -> raise_task_integrity_error(exc, name=name)
```

Replace inline delete mode validation with:

```python
    ensure_delete_mode_supported(mode)
```

Delete the old private helper definitions from `router.py`.

- [ ] **Step 7: Run crawler task helper tests**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/tasks/serializers.py backend/app/modules/crawler/tasks/validation.py backend/app/modules/crawler/tasks/errors.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_tasks_api.py
git commit -m "refactor: extract crawler task router helpers"
```

---

### Task 6: Extract Crawler Task Service, Name Extractor, And Provider Session

**Files:**
- Create: `backend/app/modules/crawler/tasks/name_extractor.py`
- Create: `backend/app/modules/crawler/tasks/provider.py`
- Create: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/tests/test_crawler_tasks_api.py`

**Interfaces:**
- Produces:
  - `extract_task_name(body: ExtractNameRequest) -> str`
  - `open_delete_provider(mode: str)`
  - `CrawlerTaskService.list_tasks(owner_id, skip, limit, keyword) -> tuple[list, int, dict]`
  - `CrawlerTaskService.get_task(task_id, owner_id)`
  - `CrawlerTaskService.create_task(data, owner_id)`
  - `CrawlerTaskService.update_task(task_id, data, owner_id)`
  - `CrawlerTaskService.run_task(task_id, data, owner_id)`
  - `CrawlerTaskService.delete_task(task_id, owner_id, mode: str) -> dict`

- [ ] **Step 1: Add extract-name search URL regression**

Append to `backend/tests/test_crawler_tasks_api.py`:

```python
def test_extract_task_name_from_search_url_without_scraper() -> None:
    from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
    from backend.app.schemas.crawl_task import ExtractNameRequest

    name = extract_task_name(ExtractNameRequest(url="https://javdb.com/search?q=ABC-123&f=all", url_type="search"))

    assert name == "ABC-123"
```

- [ ] **Step 2: Add provider session no-op regression**

Append to `backend/tests/test_crawler_tasks_api.py`:

```python
def test_open_delete_provider_returns_empty_session_for_task_only() -> None:
    from backend.app.modules.crawler.tasks.provider import open_delete_provider

    with open_delete_provider("task_only") as provider:
        assert provider is None
```

- [ ] **Step 3: Run new regressions and verify they fail**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_tasks_api.py::test_extract_task_name_from_search_url_without_scraper tests/test_crawler_tasks_api.py::test_open_delete_provider_returns_empty_session_for_task_only -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create `name_extractor.py`**

Move the body of router `extract_name` to `backend/app/modules/crawler/tasks/name_extractor.py`:

```python
from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException

from backend.app.schemas.crawl_task import ExtractNameRequest
from scraper.config.settings import REQUEST_TIMEOUT
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.core.security import is_security_check_page
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.spiders.javdb.javdb_parser import parse_page_section_name

logger = logging.getLogger(__name__)


def extract_task_name(body: ExtractNameRequest) -> str:
    if body.url_type == "search":
        parsed = urlparse(body.url)
        q_values = parse_qs(parsed.query).get("q", [])
        return q_values[0].strip() if q_values else ""

    try:
        cookie_manager = CookieManager(JAVDB_SITE["cookie_file"])
        fetcher = ScraplingFetcher(
            headers=JAVDB_SITE["headers"],
            cookies=cookie_manager.load(),
            timeout=REQUEST_TIMEOUT,
        )
        page = fetcher.get(body.url)
        if is_security_check_page(page):
            raise HTTPException(status_code=429, detail="触发安全验证，请稍后重试")
        return parse_page_section_name(page, body.url_type)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Extract task URL name failed: %s", body.url)
        raise HTTPException(status_code=500, detail=f"提取名称失败: {exc}") from exc
```

- [ ] **Step 5: Create `provider.py`**

Create `backend/app/modules/crawler/tasks/provider.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator


@contextmanager
def open_delete_provider(mode: str) -> Iterator[object | None]:
    if mode != "task_movies_and_cloud":
        yield None
        return

    from backend.app.modules.storage.config.service import StorageConfigService

    config_service = StorageConfigService()
    config = config_service.get_raw_config()
    client = config_service.provider_factory.create(config)
    provider = config_service.gateway_class(client)
    try:
        yield provider
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
```

- [ ] **Step 6: Create `service.py`**

Create `backend/app/modules/crawler/tasks/service.py`. Move repository/runtime orchestration from router functions into methods on:

```python
class CrawlerTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CrawlTaskRepository(db)
```

Methods must preserve current behavior and call the helpers from Task 5:

```python
list_tasks(owner_id, skip=None, limit=None, keyword=None)
get_stats(owner_id)
task_dict(owner_id)
get_task(task_id, owner_id)
run_task(task_id, data, owner_id)
create_task(data, owner_id)
update_task(task_id, data, owner_id)
delete_task(task_id, owner_id, mode)
```

For `delete_task`, use:

```python
with open_delete_provider(mode) as provider:
    result = delete_task(self.db, task_id, mode=mode, provider=provider)
return result.to_dict()
```

- [ ] **Step 7: Rewire router to service and name extractor**

In `router.py`, remove direct scraper imports and direct storage config provider creation. Instantiate:

```python
service = CrawlerTaskService(db)
```

Use service methods for list/get/stats/dict/statuses/run/create/update/delete. Keep `list_task_runtime_statuses` as a direct runtime-status call unless the service already wraps it cleanly.

For `/extract-name`, use:

```python
return success(data={"name": extract_task_name(body)})
```

- [ ] **Step 8: Run crawler API tests**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_tasks_api.py tests/test_crawler_runs_api.py tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 9: Verify router no longer imports scraper or storage provider internals**

```bash
rg -n "from scraper|import scraper|StorageConfigService|provider_factory|gateway_class|CloudDrive2" backend/app/modules/crawler/tasks/router.py
```

Expected: no output.

- [ ] **Step 10: Commit**

```bash
git add backend/app/modules/crawler/tasks/name_extractor.py backend/app/modules/crawler/tasks/provider.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_tasks_api.py
git commit -m "refactor: extract crawler task service"
```

---

### Task 7: Extract Crawler Run Detail Page State And Realtime Hooks

**Files:**
- Create: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- Create: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
- Create: `frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx`
- Create: `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
- Create: `frontend/src/pages/crawler/runs/utils/status.ts`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Create: `frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx`

**Interfaces:**
- Produces:
  - `useRunDetail(id: string | undefined)` returns run/logs/tasks/loading/action state and actions.
  - `useRunDetailRealtime(args)` subscribes to current run detail events.
  - `statusLabels` from `utils/status.ts`.

- [ ] **Step 1: Add realtime page regression test**

Create `frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx` with the same realtime handler Map pattern used by storage tests. The test must mock `@/api/crawlerRun` and verify:

```tsx
it('merges detail realtime events according to current filters', async () => {
  render(<RunDetailPage />)
  expect(await screen.findByText('运行详情 - task-a')).toBeInTheDocument()
  emit('crawler.run.detail.updated', {
    run_id: 'run-1',
    tasks: [{ id: 'detail-1', code: 'ABC-001', source_name: 'Movie 1', status: 'saved', error: null, created_at: '2026-07-06T00:00:00Z' }],
  })
  await waitFor(() => expect(screen.getByText('已保存')).toBeInTheDocument())
})
```

Use these router mocks:

```ts
vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ id: 'run-1' }),
}))
```

- [ ] **Step 2: Run the new test against current page**

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx --run
```

Expected: PASS before extraction.

- [ ] **Step 3: Create `utils/status.ts`**

Move `statusLabels` from `RunDetailPage.tsx` to:

```ts
export const runDetailStatusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
  pending_crawl: { text: '待爬取', color: 'default' },
  crawled: { text: '已爬取', color: 'processing' },
  crawl_failed: { text: '爬取失败', color: 'error' },
  saved: { text: '已保存', color: 'success' },
  save_failed: { text: '保存失败', color: 'error' },
  skipped: { text: '已跳过', color: 'default' },
}
```

- [ ] **Step 4: Create `useRunDetail.ts`**

Move run/log/task state, fetch helpers, `resyncSnapshot`, `handleStop`, and `handleRestart` from `RunDetailPage.tsx` into `useRunDetail`. Preserve current API calls and message behavior.

Required return shape:

```ts
return {
  actionLoading,
  fetchLogs,
  fetchRun,
  fetchTasks,
  handleRestart,
  handleStop,
  keyword,
  loading,
  logs,
  pageSize,
  resyncSnapshot,
  run,
  setKeyword,
  setLogs,
  setPageSize,
  setRun,
  setStatusFilter,
  setTasks,
  statusFilter,
  tasks,
}
```

- [ ] **Step 5: Create `useRunDetailRealtime.ts`**

Move the realtime `useEffect` from `RunDetailPage.tsx` into a hook. Required signature:

```ts
export function useRunDetailRealtime(args: {
  id: string | undefined
  fetchLogs: () => Promise<void>
  keyword: string
  resyncSnapshot: () => void
  setLogs: React.Dispatch<React.SetStateAction<RunLogEntry[]>>
  setRun: React.Dispatch<React.SetStateAction<CrawlRun | null>>
  setTasks: React.Dispatch<React.SetStateAction<CrawlRunDetailTask[]>>
  statusFilter: string | undefined
}): void
```

- [ ] **Step 6: Extract presentational components**

Create:

```tsx
RunSummaryCard.tsx
RunTaskTable.tsx
```

Move the current card and table JSX from `RunDetailPage.tsx`. Keep text, buttons, `Descriptions`, `Select`, `Input.Search`, and pagination behavior unchanged.

- [ ] **Step 7: Rewire `RunDetailPage.tsx`**

`RunDetailPage.tsx` should:

```tsx
const { id } = useParams({ strict: false })
const detail = useRunDetail(id)
useRunDetailRealtime({
  id,
  fetchLogs: detail.fetchLogs,
  keyword: detail.keyword,
  resyncSnapshot: detail.resyncSnapshot,
  setLogs: detail.setLogs,
  setRun: detail.setRun,
  setTasks: detail.setTasks,
  statusFilter: detail.statusFilter,
})
return (
  <div style={{ padding: 24 }}>
    <RunSummaryCard
      actionLoading={detail.actionLoading}
      onRestart={detail.handleRestart}
      onStop={detail.handleStop}
      run={detail.run}
    />
    <RunTaskTable
      keyword={detail.keyword}
      loading={detail.loading}
      onKeywordSearch={detail.setKeyword}
      onPageSizeChange={detail.setPageSize}
      onStatusChange={detail.setStatusFilter}
      pageSize={detail.pageSize}
      tasks={detail.tasks}
    />
    {detail.run && (
      <Card title="运行日志" style={{ marginTop: 16 }}>
        <RunLogsTimeline
          logs={detail.logs}
          isActive={detail.run.status === 'queued' || detail.run.status === 'running'}
        />
      </Card>
    )}
  </div>
)
```

- [ ] **Step 8: Run frontend test**

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx --run
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx frontend/src/pages/crawler/runs/components/RunTaskTable.tsx frontend/src/pages/crawler/runs/utils/status.ts frontend/src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx
git commit -m "refactor: split crawler run detail page"
```

---

### Task 8: Extract Crawler Task List Data And Realtime Hooks

**Files:**
- Create: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.ts`
- Create: `frontend/src/pages/crawler/tasks/hooks/useTaskListRealtime.ts`
- Create: `frontend/src/pages/crawler/tasks/utils/runtimeStats.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`

**Interfaces:**
- Produces:
  - `initialStats`
  - `recomputeStats(runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>) -> CrawlTaskRuntimeStats`
  - `useTaskListData()`
  - `useTaskListRealtime({ refreshList, setRuntimeByTaskId })`

- [ ] **Step 1: Move runtime stats utility**

Create `frontend/src/pages/crawler/tasks/utils/runtimeStats.ts`:

```ts
import type { CrawlTaskRuntimeSnapshot, CrawlTaskRuntimeStats } from '@/api/crawlTask/types'

export const initialStats: CrawlTaskRuntimeStats = {
  idle: 0,
  queued: 0,
  running: 0,
  stopped: 0,
  failed: 0,
  completed: 0,
}

export function recomputeStats(runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>): CrawlTaskRuntimeStats {
  const rows = Object.values(runtimeByTaskId)
  return {
    idle: rows.filter((row) => row.runtime_status === 'idle').length,
    queued: rows.filter((row) => row.runtime_status === 'queued').length,
    running: rows.filter((row) => row.runtime_status === 'running').length,
    stopped: rows.filter((row) => row.runtime_status === 'stopped').length,
    failed: rows.filter((row) => row.runtime_status === 'failed').length,
    completed: rows.filter((row) => row.runtime_status === 'completed').length,
  }
}
```

- [ ] **Step 2: Create `useTaskListData.ts`**

Move task list state, `fetchTasks`, `fetchRuntimeStatuses`, `refreshList`, delete/toggle/run/stop/restart handlers from `TaskListPage.tsx` into the hook. Preserve `Modal.confirm` delete behavior and success messages.

Return:

```ts
return {
  fetchRuntimeStatuses,
  handleDelete,
  handleRestart,
  handleRun,
  handleStop,
  handleToggleSkip,
  loading,
  refreshList,
  runtimeByTaskId,
  setRuntimeByTaskId,
  stats,
  tasks,
  total,
}
```

- [ ] **Step 3: Create `useTaskListRealtime.ts`**

Move the current realtime `useEffect` into:

```ts
export function useTaskListRealtime({
  refreshList,
  setRuntimeByTaskId,
}: {
  refreshList: () => void
  setRuntimeByTaskId: React.Dispatch<React.SetStateAction<Record<string, CrawlTaskRuntimeSnapshot>>>
}) {
  useEffect(() => {
    connectRealtime()
    const unsubscribeTaskStatus = subscribeRealtime<CrawlerTaskStatusUpdatedPayload>(
      'crawler.task.status.updated',
      (event) => {
        const payload = event.payload
        setRuntimeByTaskId((current) => ({ ...current, [payload.task_id]: payload }))
      },
    )
    const unsubscribeResync = subscribeRealtime('system.resync_required', () => {
      refreshList()
    })
    return () => {
      unsubscribeTaskStatus()
      unsubscribeResync()
    }
  }, [refreshList, setRuntimeByTaskId])
}
```

- [ ] **Step 4: Rewire `TaskListPage.tsx`**

Keep UI composition in the page. Replace local state/effects/handlers with:

```ts
const list = useTaskListData()
useTaskListRealtime({ refreshList: list.refreshList, setRuntimeByTaskId: list.setRuntimeByTaskId })
```

Pass hook values to existing `TaskListCards`.

- [ ] **Step 5: Run frontend build for type safety**

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/hooks/useTaskListData.ts frontend/src/pages/crawler/tasks/hooks/useTaskListRealtime.ts frontend/src/pages/crawler/tasks/utils/runtimeStats.ts
git commit -m "refactor: split crawler task list page"
```

---

### Task 9: Extract Storage Task Page Hooks And Tables

**Files:**
- Create: `frontend/src/pages/storage/tasks/hooks/useStorageTaskDetail.ts`
- Create: `frontend/src/pages/storage/tasks/hooks/useStorageTaskDetailRealtime.ts`
- Create: `frontend/src/pages/storage/tasks/hooks/useStorageTaskList.ts`
- Create: `frontend/src/pages/storage/tasks/hooks/useStorageTaskListRealtime.ts`
- Create: `frontend/src/pages/storage/tasks/components/StorageMainSummaryCard.tsx`
- Create: `frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx`
- Create: `frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx`
- Create: `frontend/src/pages/storage/tasks/utils/status.ts`
- Modify: `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`
- Modify: `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`
- Modify: `frontend/src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx`
- Modify: `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

**Interfaces:**
- Produces:
  - Storage status labels and mode labels in `utils/status.ts`.
  - Detail/list hooks that preserve current API and realtime behavior.
  - Presentational summary/table components.

- [ ] **Step 1: Move storage status utilities**

Create `frontend/src/pages/storage/tasks/utils/status.ts` by moving:

```ts
statusLabels
subTaskStatusLabels
modeLabels
mergeSubtaskUpdate
PAGE_SIZE_OPTIONS
```

from storage task pages. Export all names.

- [ ] **Step 2: Extract `useStorageTaskDetail.ts`**

Move detail state, `fetchTask`, `fetchSubtasks`, `handleStop`, and `handleRestart` from `StorageTaskDetailPage.tsx` into a hook. Required return shape:

```ts
return {
  actionLoading,
  fetchSubtasks,
  fetchTask,
  handleRestart,
  handleStop,
  loading,
  setSubtasks,
  setTask,
  subtasks,
  subtasksLoading,
  task,
}
```

- [ ] **Step 3: Extract `useStorageTaskDetailRealtime.ts`**

Move the detail realtime effect into:

```ts
export function useStorageTaskDetailRealtime(args: {
  id: string | undefined
  fetchSubtasks: () => void
  fetchTask: () => void
  setSubtasks: React.Dispatch<React.SetStateAction<StorageSubTask[]>>
  setTask: React.Dispatch<React.SetStateAction<StorageMainTask | null>>
}) {
  // subscribe to storage.main.updated, storage.sub.updated, system.resync_required
}
```

Preserve current resource ID filtering.

- [ ] **Step 4: Extract detail components**

Move the main task summary card JSX into `StorageMainSummaryCard.tsx` and the subtasks table JSX/columns into `StorageSubTaskTable.tsx`. Keep all text, buttons, tags, and navigation behavior unchanged.

- [ ] **Step 5: Extract list hooks**

Move `StorageTaskListPage.tsx` list state, `fetchTasks`, stop/restart/delete handlers into `useStorageTaskList.ts`.

Move list realtime effect into `useStorageTaskListRealtime.ts`, preserving subscriptions:

```ts
storage.main.updated
storage.main.deleted
```

- [ ] **Step 6: Extract list table**

Move list columns and table JSX into `StorageMainTaskTable.tsx`. Keep `Popconfirm`, action button text, status labels, mode labels, pagination, and detail navigation unchanged.

- [ ] **Step 7: Rewire pages**

`StorageTaskDetailPage.tsx` should compose:

```tsx
const detail = useStorageTaskDetail(id)
useStorageTaskDetailRealtime({
  id,
  fetchSubtasks: detail.fetchSubtasks,
  fetchTask: detail.fetchTask,
  setSubtasks: detail.setSubtasks,
  setTask: detail.setTask,
})
return (
  <>
    <StorageMainSummaryCard
      actionLoading={detail.actionLoading}
      loading={detail.loading}
      onRestart={detail.handleRestart}
      onStop={detail.handleStop}
      task={detail.task}
    />
    <StorageSubTaskTable
      loading={detail.subtasksLoading}
      subtasks={detail.subtasks}
    />
  </>
)
```

`StorageTaskListPage.tsx` should compose:

```tsx
const list = useStorageTaskList()
useStorageTaskListRealtime({ setTasks: list.setTasks })
return (
  <StorageMainTaskTable
    current={list.current}
    loading={list.loading}
    onDelete={list.handleDelete}
    onPageChange={list.setCurrent}
    onPageSizeChange={list.setPageSize}
    onRefresh={list.refreshCurrentPage}
    onRestart={list.handleRestart}
    onStop={list.handleStop}
    pageSize={list.pageSize}
    tasks={list.tasks}
    total={list.total}
  />
)
```

- [ ] **Step 8: Run existing storage page tests**

```bash
cd frontend
npm test -- src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx --run
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx frontend/src/pages/storage/tasks/StorageTaskListPage.tsx frontend/src/pages/storage/tasks/hooks/useStorageTaskDetail.ts frontend/src/pages/storage/tasks/hooks/useStorageTaskDetailRealtime.ts frontend/src/pages/storage/tasks/hooks/useStorageTaskList.ts frontend/src/pages/storage/tasks/hooks/useStorageTaskListRealtime.ts frontend/src/pages/storage/tasks/components/StorageMainSummaryCard.tsx frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx frontend/src/pages/storage/tasks/utils/status.ts frontend/src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
git commit -m "refactor: split storage task pages"
```

---

### Task 10: Split TagsView Utilities, Hooks, And Components

**Files:**
- Create: `frontend/src/layout/TagsView/tagsViewUtils.ts`
- Create: `frontend/src/layout/TagsView/hooks/useTagsViewRegistration.ts`
- Create: `frontend/src/layout/TagsView/hooks/useTagsContextMenu.ts`
- Create: `frontend/src/layout/TagsView/hooks/useTagsViewActions.ts`
- Create: `frontend/src/layout/TagsView/components/TagsBar.tsx`
- Create: `frontend/src/layout/TagsView/components/TagsContextMenu.tsx`
- Create: `frontend/src/layout/TagsView/__tests__/tagsViewUtils.test.ts`
- Modify: `frontend/src/layout/TagsView/index.tsx`

**Interfaces:**
- Produces:
  - `TAGS_VIEW_WHITELIST`
  - `getRemovedCacheKeys(beforeViews: TagView[], nextViews: TagView[]) -> string[]`
  - `clampContextMenuPosition(clientX, clientY, menuWidth, menuHeight, viewportWidth, viewportHeight) -> { left: number; top: number }`
  - `useTagsViewRegistration(props)`
  - `useTagsContextMenu()`
  - `useTagsViewActions(props)`

- [ ] **Step 1: Add pure utility tests**

Create `frontend/src/layout/TagsView/__tests__/tagsViewUtils.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { clampContextMenuPosition, getRemovedCacheKeys } from '../tagsViewUtils'

describe('tagsViewUtils', () => {
  it('returns cache keys removed from closable tags only', () => {
    const before = [
      { path: '/', fullPath: '/', cacheKey: 'root', title: 'Root', closable: false },
      { path: '/a', fullPath: '/a', cacheKey: 'a', title: 'A', closable: true },
      { path: '/b', fullPath: '/b', cacheKey: 'b', title: 'B', closable: true },
    ]
    const next = [before[0], before[2]]

    expect(getRemovedCacheKeys(before, next)).toEqual(['a'])
  })

  it('clamps context menu to viewport', () => {
    expect(clampContextMenuPosition(790, 590, 140, 260, 800, 600)).toEqual({ left: 652, top: 332 })
  })
})
```

- [ ] **Step 2: Run utility tests and verify they fail**

```bash
cd frontend
npm test -- src/layout/TagsView/__tests__/tagsViewUtils.test.ts --run
```

Expected: FAIL because `tagsViewUtils.ts` does not exist.

- [ ] **Step 3: Create `tagsViewUtils.ts`**

Move `TAGS_VIEW_WHITELIST` and `getRemovedCacheKeys` from `index.tsx`, and add:

```ts
export function clampContextMenuPosition(
  clientX: number,
  clientY: number,
  menuWidth: number,
  menuHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): { left: number; top: number } {
  const left = clientX + menuWidth > viewportWidth
    ? viewportWidth - menuWidth - 8
    : clientX
  const top = clientY + menuHeight > viewportHeight
    ? viewportHeight - menuHeight - 8
    : clientY
  return {
    left: Math.max(0, left),
    top: Math.max(0, top),
  }
}
```

- [ ] **Step 4: Extract registration hook**

Create `useTagsViewRegistration.ts` with the current route registration `useEffect`. Required signature:

```ts
export function useTagsViewRegistration({
  cacheKey,
  currentMeta,
  fullPath,
  pathname,
  searchStr,
}: {
  cacheKey: string
  currentMeta: { title: string; affix?: boolean }
  fullPath: string
  pathname: string
  searchStr: string
}): void
```

- [ ] **Step 5: Extract context menu hook**

Create `useTagsContextMenu.ts` with `ContextMenuState`, `closeContextMenu`, document click listener, and `handleContextMenu`. Use `clampContextMenuPosition`.

- [ ] **Step 6: Extract actions hook**

Create `useTagsViewActions.ts` with close/refresh handlers and cache destruction. Keep signatures aligned with current component handlers:

```ts
handleClose(tag, event?)
handleMouseDown(tag, event)
handleRefresh()
handleCloseCurrent()
handleCloseOthers()
handleCloseLeft()
handleCloseRight()
handleCloseAll()
```

- [ ] **Step 7: Extract presentational components**

Create `TagsBar.tsx` for the tag strip and `TagsContextMenu.tsx` for the menu. Move current JSX exactly, preserving classes, icons, text, disabled states, and click handlers.

- [ ] **Step 8: Rewire `index.tsx`**

`TagsView` should keep route state lookup, `cacheControl`, and composition:

```tsx
useTagsViewRegistration({
  cacheKey,
  currentMeta,
  fullPath,
  pathname,
  searchStr,
})
const context = useTagsContextMenu()
const actions = useTagsViewActions({
  cacheControl,
  cacheKey,
  closeContextMenu: context.closeContextMenu,
  contextMenu: context.contextMenu,
  fullPath,
  navigate,
  visitedViews,
})
return (
  <>
    <TagsBar
      darkMode={darkMode}
      isActive={isActive}
      onClose={actions.handleClose}
      onContextMenu={context.handleContextMenu}
      onMouseDown={actions.handleMouseDown}
      onNavigate={(fullPath) => void navigate({ to: fullPath })}
      visitedViews={visitedViews}
    />
    <TagsContextMenu
      actions={actions}
      contextMenu={context.contextMenu}
      selectedTag={context.contextMenu.selectedTag}
      visitedViews={visitedViews}
    />
  </>
)
```

- [ ] **Step 9: Run tests and build**

```bash
cd frontend
npm test -- src/layout/TagsView/__tests__/tagsViewUtils.test.ts --run
npm run build
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/layout/TagsView/index.tsx frontend/src/layout/TagsView/tagsViewUtils.ts frontend/src/layout/TagsView/hooks/useTagsViewRegistration.ts frontend/src/layout/TagsView/hooks/useTagsContextMenu.ts frontend/src/layout/TagsView/hooks/useTagsViewActions.ts frontend/src/layout/TagsView/components/TagsBar.tsx frontend/src/layout/TagsView/components/TagsContextMenu.tsx frontend/src/layout/TagsView/__tests__/tagsViewUtils.test.ts
git commit -m "refactor: split tags view"
```

---

### Task 11: Split Request Transform Modules

**Files:**
- Create: `frontend/src/request/session.ts`
- Create: `frontend/src/request/businessError.ts`
- Create: `frontend/src/request/networkError.ts`
- Create: `frontend/src/request/responseTransform.ts`
- Create: `frontend/src/request/__tests__/transform.test.ts`
- Modify: `frontend/src/request/transform.ts`

**Interfaces:**
- Produces:
  - `session.isRelogin`
  - `session.loginRedirectUrl() -> string`
  - `session.expireSession(msg: string) -> Promise<never>`
  - `businessError.getBusinessMessage(data) -> string`
  - `networkError.normalizeNetworkError(error: AxiosError) -> string`
  - `networkError.getResponseErrorPayload(error: AxiosError) -> { msg: string; code?: string | number; data?: unknown }`
  - `responseTransform.transformResponse(response) -> unknown`
  - `responseTransform.handleResponseError(error) -> Promise<never>`
  - `transform.ts` re-exports the public functions used by existing imports.

- [ ] **Step 1: Add request transform tests**

Create `frontend/src/request/__tests__/transform.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { AxiosError, AxiosResponse } from 'axios'
import { normalizeNetworkError, transformResponse } from '../transform'

function response(data: unknown, config: Record<string, unknown> = {}): AxiosResponse {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: { responseType: 'json' },
  } as AxiosResponse
}

describe('request transform', () => {
  it('unwraps successful object responses', () => {
    expect(transformResponse(response({ code: 200, msg: 'ok', data: { id: 1 } }))).toEqual({ id: 1 })
  })

  it('keeps paginated responses intact', () => {
    expect(transformResponse(response({ code: 200, msg: 'ok', rows: [{ id: 1 }], total: 1 }))).toEqual({
      code: 200,
      msg: 'ok',
      rows: [{ id: 1 }],
      total: 1,
    })
  })

  it('normalizes network errors', () => {
    expect(normalizeNetworkError({ message: 'Network Error' } as AxiosError)).toBe('后端接口连接异常')
  })
})
```

- [ ] **Step 2: Run request tests before extraction**

```bash
cd frontend
npm test -- src/request/__tests__/transform.test.ts --run
```

Expected: PASS before extraction.

- [ ] **Step 3: Create `session.ts`**

Move from `transform.ts`:

```ts
isRelogin
loginRedirectUrl
expireSession
```

Export all three. Preserve modal title/content/buttons, `useAuthStore.getState().logout()`, and redirect behavior.

- [ ] **Step 4: Create `businessError.ts`**

Move `getBusinessMessage` to `businessError.ts`:

```ts
import { HttpStatus } from '@/enums/RespEnum'
import errorCode from '@/request/errorCode'
import type { ApiResponse, PaginatedApiResponse } from './types'

export function getBusinessMessage(data: ApiResponse | PaginatedApiResponse): string {
  const code = data.code ?? HttpStatus.SUCCESS
  return errorCode[code as string | number] || data.msg || errorCode.default
}
```

- [ ] **Step 5: Create `networkError.ts`**

Move `normalizeNetworkError` and `getResponseErrorPayload` to `networkError.ts`. Export both. Keep FastAPI `detail` handling and wrapped backend `msg` handling unchanged.

- [ ] **Step 6: Create `responseTransform.ts`**

Move `transformResponse` and `handleResponseError` to `responseTransform.ts`. Import `expireSession`, `getBusinessMessage`, `getResponseErrorPayload`, `BusinessError`, `isCancelledError`, Ant Design `message`, `notification`, and `HttpStatus`.

- [ ] **Step 7: Convert `transform.ts` to public facade**

Replace `frontend/src/request/transform.ts` with:

```ts
export { getBusinessMessage } from './businessError'
export { getResponseErrorPayload, normalizeNetworkError } from './networkError'
export { expireSession, isRelogin, loginRedirectUrl } from './session'
export { handleResponseError, transformResponse } from './responseTransform'
```

- [ ] **Step 8: Run request tests and build**

```bash
cd frontend
npm test -- src/request/__tests__/transform.test.ts --run
npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/request/transform.ts frontend/src/request/session.ts frontend/src/request/businessError.ts frontend/src/request/networkError.ts frontend/src/request/responseTransform.ts frontend/src/request/__tests__/transform.test.ts
git commit -m "refactor: split request transform"
```

---

### Task 12: Final Verification

**Files:**
- Verify all touched backend and frontend files.

**Interfaces:**
- Consumes all interfaces from Tasks 1-11.
- Produces final confidence that behavior and boundaries match the spec.

- [ ] **Step 1: Run backend focused suites**

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py tests/test_storage_worker_service.py tests/test_storage_tasks_api.py tests/test_crawler_tasks_api.py tests/test_crawler_runs_api.py tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-realtime.test.tsx src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx src/layout/TagsView/__tests__/tagsViewUtils.test.ts src/request/__tests__/transform.test.ts --run
```

Expected: PASS.

- [ ] **Step 3: Run frontend lint**

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Run boundary checks**

```bash
rg -n "CloudDrive2Gateway|sync_movie_storage_status|set_movie_storage_status|publish_movie_storage_updated|target_folder_specs_from_subtask" backend/app/modules/storage/worker/runner.py
rg -n "from scraper|import scraper|StorageConfigService|provider_factory|gateway_class|CloudDrive2" backend/app/modules/crawler/tasks/router.py
rg -n "^def (is_rename_name_exists_error|_find_existing_rename_target|rename_selected_videos|_target_file_exists|_move_source_path|_move_file_name|_target_file_path|move_renamed_videos|verify_moved_files|cleanup_download_folder)|^class MoveRenamedVideosResult" backend/app/modules/storage/worker/file_ops.py
rg -n "connectRealtime\\(|subscribeRealtime\\(" frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx frontend/src/pages/storage/tasks/StorageTaskListPage.tsx
```

Expected:
- first command: no output;
- second command: no output;
- third command: no output;
- fourth command: no output from page files after realtime hooks are extracted.

- [ ] **Step 6: Inspect git status**

```bash
git status --short
```

Expected: no unstaged tracked changes from this plan.
