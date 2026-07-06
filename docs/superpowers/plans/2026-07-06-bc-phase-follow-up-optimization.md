# BC Phase Follow-Up Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove remaining active-code legacy artifacts, split storage worker responsibilities, tighten storage task service boundaries, and push common movie list filters into SQL without changing user-visible behavior.

**Architecture:** Execute four independent phases in order: legacy cleanup, storage worker module split, storage task service boundary cleanup, and movie query SQL pushdown. Keep existing router APIs, database schema, CloudDrive2 behavior, storage step names, and frontend screens unchanged. Each task introduces focused tests before implementation and ends with a dedicated commit.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Vitest, ESLint.

## Global Constraints

- Do not redesign the frontend.
- Do not change API response shapes.
- Do not change database schema or Alembic migrations.
- Do not change CloudDrive2 provider behavior, retry policy, or step names.
- Do not rewrite scraper parsing logic.
- Do not remove historical docs or plans that record previous decisions.
- Do not make PostgreSQL-only query behavior mandatory for SQLite tests.
- Preserve current official routes: `/crawler/tasks`, `/api/crawler/tasks`, `/content/movies`, `/api/content/movies`, `/api/events/stream`.
- Leave pre-existing untracked plan files alone unless the user explicitly asks to stage them.

---

## File Structure

### Create

- `backend/app/modules/storage/worker/download.py`
  - Owns magnet submit error classification, submit/recover/poll download discovery, and `DownloadDiscoveryResult`.
- `backend/app/modules/storage/worker/target_files.py`
  - Owns target folder file detection, existing-target result shape, and multi-target copy recovery.
- `backend/app/modules/storage/worker/file_ops.py`
  - Owns scan, rename, move/copy, verify, and cleanup file operations.
- `backend/app/modules/storage/worker/results.py`
  - Owns repeated subtask skipped/success result state writes.
- `backend/app/modules/storage/tasks/skip_rules.py`
  - Owns storage subtask skip classification.
- `backend/app/modules/storage/tasks/target_locations.py`
  - Owns target location resolution from source crawl tasks.
- `backend/app/modules/storage/tasks/serializers.py`
  - Owns storage main/subtask response dicts.
- `backend/app/modules/storage/tasks/creation.py`
  - Owns main task/subtask creation and movie storage summary initialization.
- `backend/tests/test_storage_worker_target_files.py`
  - Covers target exists and copy-from-existing-target recovery.
- `backend/tests/test_storage_task_service_units.py`
  - Covers skip rules, target location resolution, and serializers.
- `backend/tests/test_content_movie_queries_sql.py`
  - Covers SQL pushdown and fallback behavior for movie list queries.

### Modify

- `frontend/src/routes/index.tsx`
  - Remove `legacyCrawlTasksRoute`.
- `backend/tests/test_crawler_worker_service.py`
  - Rename fake classes and comments from `MovieService*` to `CrawlerEngine*`.
- `backend/app/modules/storage/worker/steps.py`
  - Keep public orchestration functions; delegate implementation to focused worker modules.
- `backend/tests/test_storage_worker_pipeline.py`
  - Update imports for moved functions and keep integration coverage.
- `backend/app/modules/storage/tasks/service.py`
  - Delegate creation, skip rules, target location resolution, and serialization to new modules.
- `backend/tests/test_storage_tasks_api.py`
  - Keep API contract tests passing; add assertions only if extracted helpers expose regressions.
- `backend/app/modules/content/movies/queries.py`
  - Introduce SQL query builder and fallback execution.
- `backend/tests/test_content_movies_api.py`
  - Keep original filter contract tests passing.

### Delete

- `backend/app/modules/movies/__init__.py`
- `backend/app/modules/movies/__pycache__/`

---

### Task 1: Remove Remaining Active Legacy Artifacts

**Files:**
- Modify: `frontend/src/routes/index.tsx`
- Modify: `backend/tests/test_crawler_worker_service.py`
- Delete: `backend/app/modules/movies/__init__.py`
- Delete: `backend/app/modules/movies/__pycache__/`

**Interfaces:**
- Consumes: current official frontend route `/crawler/tasks`.
- Produces: no active-code `/crawl-tasks`, `legacyCrawlTasksRoute`, or `backend.app.modules.movies` references.

- [ ] **Step 1: Add a route-level regression by reference search**

Run:

```bash
rg -n "legacyCrawlTasksRoute|/crawl-tasks|backend\.app\.modules\.movies|app\.modules\.movies" frontend/src backend/app backend/tests shared scraper -g '*.py' -g '*.ts' -g '*.tsx'
```

Expected before cleanup:

```text
frontend/src/routes/index.tsx:149:const legacyCrawlTasksRoute = createRoute({
frontend/src/routes/index.tsx:152:  path: '/crawl-tasks',
```

- [ ] **Step 2: Remove the legacy frontend route**

In `frontend/src/routes/index.tsx`, delete this block:

```ts
const legacyCrawlTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawl-tasks',
  beforeLoad: () => {
    throw redirect({ to: '/crawler/tasks' })
  },
})
```

Also remove `legacyCrawlTasksRoute,` from `layoutRoute.addChildren([...])`.

- [ ] **Step 3: Remove the empty legacy backend package**

Run:

```bash
rm -f backend/app/modules/movies/__init__.py
rm -rf backend/app/modules/movies/__pycache__
rmdir backend/app/modules/movies
```

Expected: `rmdir` succeeds because no source files remain in the package.

- [ ] **Step 4: Rename crawler runtime test fake classes**

In `backend/tests/test_crawler_worker_service.py`, rename fake classes without changing method bodies:

```python
MovieServiceStub -> CrawlerEngineStub
PersistingMovieServiceStub -> PersistingCrawlerEngineStub
FilterSyncMovieServiceStub -> FilterSyncCrawlerEngineStub
FailingPersistenceMovieServiceStub -> FailingPersistenceCrawlerEngineStub
ListPhaseDedupeMovieServiceStub -> ListPhaseDedupeCrawlerEngineStub
DetailPhaseDedupeMovieServiceStub -> DetailPhaseDedupeCrawlerEngineStub
StopAwareMovieServiceStub -> StopAwareCrawlerEngineStub
ExistingDetailReuseMovieServiceStub -> ExistingDetailReuseCrawlerEngineStub
ListPhaseRestartMovieServiceStub -> ListPhaseRestartCrawlerEngineStub
```

Replace monkeypatch references, for example:

```python
monkeypatch.setattr(
    "backend.app.modules.crawler.runtime.service.get_crawler_engine",
    lambda: PersistingCrawlerEngineStub(),
)
```

Change the comment:

```python
# Mock the _execute_run function to avoid importing MovieService
```

to:

```python
# Mock _execute_run so this test only verifies queue processing.
```

- [ ] **Step 5: Run legacy backend regressions**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_removed_legacy_apis.py tests/test_realtime_events.py::test_deprecated_crawler_stream_route_is_removed tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 7: Verify active-code legacy references are gone**

Run:

```bash
rg -n "legacyCrawlTasksRoute|/crawl-tasks|backend\.app\.modules\.movies|app\.modules\.movies" frontend/src backend/app backend/tests shared scraper -g '*.py' -g '*.ts' -g '*.tsx'
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/index.tsx backend/tests/test_crawler_worker_service.py
git add -u backend/app/modules/movies
git commit -m "refactor: remove remaining legacy active artifacts"
```

---

### Task 2: Extract Storage Worker Target And File Operations

**Files:**
- Create: `backend/app/modules/storage/worker/target_files.py`
- Create: `backend/app/modules/storage/worker/file_ops.py`
- Create: `backend/tests/test_storage_worker_target_files.py`
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Produces:
  - `ExistingTargetFilesResult`
  - `MoveRenamedVideosResult`
  - `scan_found_files(found_files: list[dict]) -> list[dict]`
  - `rename_selected_videos(context, selected_videos: list[dict], tags: list[str]) -> list[dict]`
  - `move_renamed_videos(context, renamed_files: list[dict], target_paths: list[str]) -> MoveRenamedVideosResult`
  - `verify_moved_files(context, moved_files: list[dict]) -> bool`
  - `cleanup_download_folder(context, download_folder: str, config: dict) -> None`
  - `find_existing_target_files(provider, target_paths: list[str], expected_names: list[str]) -> ExistingTargetFilesResult`
  - `copy_existing_target_to_missing_targets(context, result: ExistingTargetFilesResult) -> list[dict]`

- [ ] **Step 1: Write target file tests**

Create `backend/tests/test_storage_worker_target_files.py`:

```python
from dataclasses import dataclass

from backend.app.modules.storage.worker.target_files import (
    copy_existing_target_to_missing_targets,
    find_existing_target_files,
)


@dataclass
class RemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False


class TargetProvider:
    def __init__(self) -> None:
        self.files = {
            "/Movies/A": [RemoteFile("ABC-123.mp4", "/Movies/A/ABC-123.mp4", 500)],
            "/Movies/B": [],
        }
        self.copied: list[tuple[str, str]] = []
        self.created: list[str] = []

    def list_files(self, path):
        return self.files.get(path, [])

    def ensure_directory(self, path):
        self.created.append(path)

    def copy_file(self, source, target_folder):
        self.copied.append((source, target_folder))


class Context:
    def __init__(self, provider) -> None:
        self.provider = provider
        self.logs = []

    def log(self, level, message, context=None, *, step=None, event=None):
        self.logs.append((level, message, context or {}, step, event))


def test_find_existing_target_files_reports_existing_and_missing_targets() -> None:
    provider = TargetProvider()

    result = find_existing_target_files(provider, ["/Movies/A", "/Movies/B"], ["ABC-123.mp4"])

    assert result.any_target_exists is True
    assert result.all_targets_exist is False
    assert result.existing_targets == ["/Movies/A"]
    assert result.missing_targets == ["/Movies/B"]
    assert result.source_path == "/Movies/A/ABC-123.mp4"
    assert result.source_name == "ABC-123.mp4"


def test_copy_existing_target_to_missing_targets_copies_from_first_existing_target() -> None:
    provider = TargetProvider()
    result = find_existing_target_files(provider, ["/Movies/A", "/Movies/B"], ["ABC-123.mp4"])

    copied = copy_existing_target_to_missing_targets(Context(provider), result)

    assert provider.created == ["/Movies/B"]
    assert provider.copied == [("/Movies/A/ABC-123.mp4", "/Movies/B")]
    assert copied[0]["copied_paths"] == ["/Movies/B/ABC-123.mp4"]
    assert copied[0]["copy_source"] == "/Movies/A/ABC-123.mp4"
```

- [ ] **Step 2: Run target file tests and verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_target_files.py -v
```

Expected: FAIL because `backend.app.modules.storage.worker.target_files` does not exist.

- [ ] **Step 3: Create `target_files.py` by moving exact target helpers**

Create `backend/app/modules/storage/worker/target_files.py` and move these definitions unchanged from `steps.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


def ensure_directory_chain(provider, folder_path: str) -> None:
    provider.ensure_directory(folder_path)


def _target_file_path(target_folder: str, file_name: str) -> str:
    return str(PurePosixPath(target_folder) / file_name)


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
```

Then move these functions from `steps.py` into the same file with the same bodies:

```python
_listed_entry_to_target_file
find_existing_target_files
copy_existing_target_to_missing_targets
```

Keep `_target_file_path` private in this module. Later modules import only `ensure_directory_chain`, `ExistingTargetFilesResult`, `find_existing_target_files`, and `copy_existing_target_to_missing_targets`.

- [ ] **Step 4: Create `file_ops.py` by moving exact file operation helpers**

Create `backend/app/modules/storage/worker/file_ops.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.target_files import ensure_directory_chain
```

Move these definitions from `steps.py` into `file_ops.py` with the same bodies:

```python
select_main_videos
target_files_exist
scan_found_files
is_rename_name_exists_error
_find_existing_rename_target
rename_selected_videos
_target_file_exists
_move_source_path
_move_file_name
_target_file_path
MoveRenamedVideosResult
move_renamed_videos
verify_moved_files
cleanup_download_folder
```

After moving, `MoveRenamedVideosResult` must stay:

```python
@dataclass
class MoveRenamedVideosResult:
    moved_files: list[dict]
    skipped_files: list[dict]
    all_targets_exist: bool = False
    all_rename_name_exists: bool = False
```

- [ ] **Step 5: Update `steps.py` imports and delete moved definitions**

In `backend/app/modules/storage/worker/steps.py`, import moved names:

```python
from backend.app.modules.storage.worker.file_ops import (
    cleanup_download_folder,
    move_renamed_videos,
    rename_selected_videos,
    scan_found_files,
    verify_moved_files,
)
from backend.app.modules.storage.worker.target_files import (
    copy_existing_target_to_missing_targets,
    ensure_directory_chain,
    find_existing_target_files,
)
```

Delete the moved definitions from `steps.py`. Keep `execute_current_magnet_attempt` and `execute_subtask_pipeline` in `steps.py`.

- [ ] **Step 6: Update moved test import**

In `backend/tests/test_storage_worker_pipeline.py`, replace:

```python
from backend.app.modules.storage.worker.steps import select_main_videos
```

with:

```python
from backend.app.modules.storage.worker.file_ops import select_main_videos
```

- [ ] **Step 7: Run focused storage worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_target_files.py tests/test_storage_worker_pipeline.py tests/test_storage_worker_timeline.py -v
```

Expected: PASS.

- [ ] **Step 8: Verify no duplicate moved helpers remain in `steps.py`**

Run:

```bash
rg -n "def select_main_videos|def find_existing_target_files|def move_renamed_videos|def verify_moved_files|class ExistingTargetFilesResult|class MoveRenamedVideosResult" backend/app/modules/storage/worker/steps.py
```

Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/worker/target_files.py backend/app/modules/storage/worker/file_ops.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_target_files.py backend/tests/test_storage_worker_pipeline.py
git commit -m "refactor: extract storage worker file operations"
```

---

### Task 3: Extract Storage Worker Download And Result Helpers

**Files:**
- Create: `backend/app/modules/storage/worker/download.py`
- Create: `backend/app/modules/storage/worker/results.py`
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Consumes from Task 2:
  - `find_existing_target_files(provider, target_paths, expected_names)`
  - `copy_existing_target_to_missing_targets(context, result)`
  - `cleanup_download_folder(context, download_folder, config)`
- Produces:
  - `is_submit_task_exists_error(error: Exception | str) -> bool`
  - `recover_existing_downloaded_video_files(context, search_terms, task_download_folder, download_root) -> list[dict]`
  - `poll_downloaded_video_files(context, search_terms, task_download_folder, download_root) -> list[dict]`
  - `mark_subtask_skipped_for_existing_targets(context, existing_result, expected_name) -> None`
  - `mark_subtask_success_from_existing_targets(context, copied_files, existing_result, magnet) -> None`
  - `mark_subtask_skipped_for_move_result(context, reason, skipped_files, target_paths) -> None`

- [ ] **Step 1: Add submit-task-exists classifier test**

Append to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_is_submit_task_exists_error_matches_clouddrive_duplicate_messages() -> None:
    from backend.app.modules.storage.worker.download import is_submit_task_exists_error

    assert is_submit_task_exists_error(RuntimeError("10008 task exists")) is True
    assert is_submit_task_exists_error("任务已存在") is True
    assert is_submit_task_exists_error(RuntimeError("network down")) is False
```

- [ ] **Step 2: Run classifier test and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py::test_is_submit_task_exists_error_matches_clouddrive_duplicate_messages -v
```

Expected: FAIL because `backend.app.modules.storage.worker.download` does not exist.

- [ ] **Step 3: Create `download.py`**

Create `backend/app/modules/storage/worker/download.py`:

```python
from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass
class DownloadDiscoveryResult:
    found_files: list[dict]
    submit_task_exists: bool = False


def _log_search_result(context, result) -> None:
    context.log("INFO", "查找下载文件", result.log_context, step="waiting_download")


def is_submit_task_exists_error(error: Exception | str) -> bool:
    message = str(error)
    return "10008" in message or "任务已存在" in message
```

Move these functions from `steps.py` into `download.py` with the same bodies:

```python
recover_existing_downloaded_video_files
poll_downloaded_video_files
```

Keep their imports local inside the functions:

```python
from backend.app.modules.storage.worker.file_finder import find_recovery_video_files
from backend.app.modules.storage.worker.file_finder import find_listed_video_files
```

- [ ] **Step 4: Create `results.py`**

Create `backend/app/modules/storage/worker/results.py`:

```python
from __future__ import annotations


def mark_subtask_skipped_for_existing_targets(context, existing_result, expected_name: str) -> None:
    skipped_files = [
        {
            "name": existing_result.source_name or expected_name,
            "skip_reason": "target_exists",
            "existing_targets": [item["path"] for item in existing_result.existing_files],
        }
    ]
    context.subtask.status = "skipped"
    context.subtask.skip_reason = "target_exists"
    context.subtask.moved_files = []
    context.subtask.skipped_files = skipped_files
    context.subtask.result = {"status": "skipped", "reason": "target_exists", "files": skipped_files}
    context.log(
        "INFO",
        "目标文件已全部存在，子任务标记为跳过",
        {"skipped_files": skipped_files, "target_paths": existing_result.checked_targets},
        step="move_files",
        event="subtask_skipped",
    )
    context.publish_subtask()


def mark_subtask_success_from_existing_targets(context, copied_files: list[dict], existing_result, magnet: dict) -> None:
    context.subtask.renamed_files = []
    context.subtask.moved_files = copied_files
    context.subtask.skipped_files = []
    context.subtask.result = {
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


def mark_subtask_skipped_for_move_result(context, reason: str, skipped_files: list[dict], target_paths: list[str]) -> None:
    context.subtask.status = "skipped"
    context.subtask.skip_reason = reason
    context.subtask.result = {"status": "skipped", "reason": reason, "files": skipped_files}
    message = "目标文件已全部存在，子任务标记为跳过" if reason == "target_exists" else "重命名目标已存在，子任务标记为跳过"
    context.log(
        "INFO",
        message,
        {"skipped_files": skipped_files, "target_paths": target_paths},
        step="move_files",
        event="subtask_skipped",
    )
    context.publish_subtask()
```

- [ ] **Step 5: Rewire `steps.py` to use download and result helpers**

In `backend/app/modules/storage/worker/steps.py`, add:

```python
from backend.app.modules.storage.worker.download import (
    is_submit_task_exists_error,
    poll_downloaded_video_files,
    recover_existing_downloaded_video_files,
)
from backend.app.modules.storage.worker.results import (
    mark_subtask_skipped_for_existing_targets,
    mark_subtask_skipped_for_move_result,
    mark_subtask_success_from_existing_targets,
)
```

Replace:

```python
if "10008" not in message and "任务已存在" not in message:
```

with:

```python
if not is_submit_task_exists_error(exc):
```

Replace the inline target-exists skipped state block with:

```python
mark_subtask_skipped_for_existing_targets(context, existing_result, preview_name)
context.set_step("cleanup_files")
cleanup_download_folder(context, download_folder, config)
return True
```

Replace the inline copied-from-existing-target success state block after verification with:

```python
context.set_step("cleanup_files")
cleanup_download_folder(context, download_folder, config)
mark_subtask_success_from_existing_targets(context, copied_files, existing_result, magnet)
return True
```

Replace the two move-result skipped branches with:

```python
mark_subtask_skipped_for_move_result(context, "target_exists", skipped_files, target_paths)
context.set_step("cleanup_files")
cleanup_download_folder(context, download_folder, config)
return True
```

and:

```python
mark_subtask_skipped_for_move_result(context, "rename_name_exists", skipped_files, target_paths)
context.set_step("cleanup_files")
cleanup_download_folder(context, download_folder, config)
return True
```

- [ ] **Step 6: Delete moved helpers from `steps.py`**

Delete these definitions from `backend/app/modules/storage/worker/steps.py`:

```python
_log_search_result
recover_existing_downloaded_video_files
poll_downloaded_video_files
mark_subtask_skipped_for_existing_targets
```

Also remove unused imports from `steps.py`:

```python
import random
import time
from dataclasses import dataclass
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
```

Keep `dataclass` only if no moved result classes were removed by Task 2. If `rg -n "dataclass" backend/app/modules/storage/worker/steps.py` returns no decorators, remove the import.

- [ ] **Step 7: Run storage worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py tests/test_storage_worker_target_files.py tests/test_storage_file_finder_scope.py tests/test_storage_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Verify no duplicate download helpers remain in `steps.py`**

Run:

```bash
rg -n "def recover_existing_downloaded_video_files|def poll_downloaded_video_files|def _log_search_result|def mark_subtask_skipped_for_existing_targets|10008" backend/app/modules/storage/worker/steps.py
```

Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/worker/download.py backend/app/modules/storage/worker/results.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "refactor: extract storage worker download helpers"
```

---

### Task 4: Extract Storage Task Skip Rules, Target Locations, And Serializers

**Files:**
- Create: `backend/app/modules/storage/tasks/skip_rules.py`
- Create: `backend/app/modules/storage/tasks/target_locations.py`
- Create: `backend/app/modules/storage/tasks/serializers.py`
- Create: `backend/tests/test_storage_task_service_units.py`
- Modify: `backend/app/modules/storage/tasks/service.py`

**Interfaces:**
- Produces:
  - `classify_storage_skip(movie) -> str | None`
  - `resolve_target_locations(db: Session, movie: Movie, source: str, selected_storage_location: str | None) -> list[str]`
  - `storage_main_task_to_dict(task: StorageMainTask) -> dict`
  - `storage_subtask_to_dict(task: StorageSubTask) -> dict`

- [ ] **Step 1: Write focused unit tests**

Create `backend/tests/test_storage_task_service_units.py`:

```python
import uuid

from backend.app.models.crawl_task import CrawlTask
from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.tasks.serializers import (
    storage_main_task_to_dict,
    storage_subtask_to_dict,
)
from backend.app.modules.storage.tasks.skip_rules import classify_storage_skip
from backend.app.modules.storage.tasks.target_locations import resolve_target_locations
from shared.database.models.content import Movie, MovieMagnet


def test_classify_storage_skip_returns_expected_reasons() -> None:
    assert classify_storage_skip(None) == "movie_not_found"

    marked = Movie(code="A", source_name="A", marked=True)
    assert classify_storage_skip(marked) == "movie_marked"

    no_magnets = Movie(code="B", source_name="B", marked=False)
    no_magnets.magnets = []
    assert classify_storage_skip(no_magnets) == "no_magnets"

    no_url = Movie(code="C", source_name="C", marked=False)
    no_url.magnets = [MovieMagnet(magnet_url="", dedupe_key="empty")]
    assert classify_storage_skip(no_url) == "no_magnet_url"

    usable = Movie(code="D", source_name="D", marked=False)
    usable.magnets = [MovieMagnet(magnet_url="magnet:?xt=urn:btih:abc", dedupe_key="abc")]
    assert classify_storage_skip(usable) is None


def test_resolve_target_locations_uses_source_task_locations(db_session, test_user) -> None:
    task_a = CrawlTask(name="A", owner_id=test_user.id, storage_location="A")
    task_b = CrawlTask(name="B", owner_id=test_user.id, storage_location="B")
    db_session.add_all([task_a, task_b])
    db_session.flush()
    movie = Movie(code="LOC-1", source_name="LOC", source_task_ids=[task_a.id, task_b.id])

    assert resolve_target_locations(db_session, movie, "single", "B") == ["B"]
    assert resolve_target_locations(db_session, movie, "batch", None) == ["A"]
    assert resolve_target_locations(db_session, movie, "single", None) == ["A", "B"]


def test_storage_task_serializers_preserve_response_shape(test_user) -> None:
    main_id = uuid.uuid4()
    movie_id = uuid.uuid4()
    main = StorageMainTask(
        id=main_id,
        alias="alias",
        display_name="alias",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        created_by=test_user.id,
    )
    sub = StorageSubTask(
        id=uuid.uuid4(),
        main_task_id=main_id,
        movie_id=movie_id,
        movie_code="ABC-123",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
        selected_storage_location="A",
        target_locations=["A"],
        target_paths=["/Movies/A/ABC-123"],
        download_path="",
    )

    main_payload = storage_main_task_to_dict(main)
    sub_payload = storage_subtask_to_dict(sub)

    assert main_payload["id"] == str(main_id)
    assert main_payload["alias"] == "alias"
    assert main_payload["status"] == "queued"
    assert sub_payload["movie_code"] == "ABC-123"
    assert sub_payload["target_locations"] == ["A"]
    assert sub_payload["current_magnet_id"] is None
```

- [ ] **Step 2: Run unit tests and verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_task_service_units.py -v
```

Expected: FAIL because the new modules do not exist.

- [ ] **Step 3: Create `skip_rules.py`**

Create `backend/app/modules/storage/tasks/skip_rules.py`:

```python
from __future__ import annotations

from shared.database.models.content import Movie


def classify_storage_skip(movie: Movie | None) -> str | None:
    if movie is None:
        return "movie_not_found"
    if movie.marked:
        return "movie_marked"
    if not movie.magnets:
        return "no_magnets"
    usable = [magnet for magnet in movie.magnets if magnet.magnet_url]
    if not usable:
        return "no_magnet_url"
    return None
```

- [ ] **Step 4: Create `target_locations.py`**

Create `backend/app/modules/storage/tasks/target_locations.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie


def resolve_target_locations(
    db: Session,
    movie: Movie,
    source: str,
    selected_storage_location: str | None,
) -> list[str]:
    locations: list[str] = []
    for task_id in movie.source_task_ids or []:
        try:
            parsed_id = uuid.UUID(str(task_id)) if not isinstance(task_id, uuid.UUID) else task_id
        except (ValueError, TypeError):
            continue
        crawl_task = db.get(CrawlTask, parsed_id)
        if crawl_task and crawl_task.storage_location and crawl_task.storage_location not in locations:
            locations.append(crawl_task.storage_location)

    if not locations:
        return []
    if source == "single" and selected_storage_location and selected_storage_location in locations:
        return [selected_storage_location]
    if source == "batch":
        return [locations[0]]
    return locations
```

- [ ] **Step 5: Create `serializers.py`**

Create `backend/app/modules/storage/tasks/serializers.py` by moving the bodies of `StorageTaskService.to_main_response` and `StorageTaskService.to_subtask_response` into:

```python
from __future__ import annotations

from backend.app.models.storage_task import StorageMainTask, StorageSubTask


def storage_main_task_to_dict(task: StorageMainTask) -> dict:
    return {
        "id": str(task.id),
        "alias": task.alias,
        "display_name": task.display_name,
        "source": task.source,
        "storage_mode": task.storage_mode,
        "status": task.status,
        "total_count": task.total_count,
        "success_count": task.success_count,
        "failed_count": task.failed_count,
        "skipped_count": task.skipped_count,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "error_message": task.error_message,
    }


def storage_subtask_to_dict(task: StorageSubTask) -> dict:
    return {
        "id": str(task.id),
        "main_task_id": str(task.main_task_id),
        "movie_id": str(task.movie_id),
        "movie_code": task.movie_code,
        "movie_title": task.movie_title,
        "status": task.status,
        "step": task.step,
        "storage_mode": task.storage_mode,
        "selected_storage_location": task.selected_storage_location,
        "target_locations": task.target_locations or [],
        "download_path": task.download_path,
        "target_paths": task.target_paths or [],
        "magnet_attempts": task.magnet_attempts or [],
        "current_magnet_id": str(task.current_magnet_id) if task.current_magnet_id else None,
        "current_magnet_url": task.current_magnet_url,
        "renamed_files": task.renamed_files or [],
        "moved_files": task.moved_files or [],
        "skipped_files": task.skipped_files or [],
        "result": task.result or {},
        "skip_reason": task.skip_reason,
        "error_message": task.error_message,
        "queued_at": task.queued_at.isoformat() if task.queued_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }
```

- [ ] **Step 6: Delegate service methods to new helpers**

In `backend/app/modules/storage/tasks/service.py`, add:

```python
from backend.app.modules.storage.tasks.serializers import (
    storage_main_task_to_dict,
    storage_subtask_to_dict,
)
from backend.app.modules.storage.tasks.skip_rules import classify_storage_skip
from backend.app.modules.storage.tasks.target_locations import resolve_target_locations
```

Replace `to_main_response` body with:

```python
return storage_main_task_to_dict(task)
```

Replace `to_subtask_response` body with:

```python
return storage_subtask_to_dict(task)
```

Replace `_classify_skip` body with:

```python
return classify_storage_skip(movie)
```

Replace `_resolve_target_locations` body with:

```python
return resolve_target_locations(self.db, movie, source, selected_storage_location)
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_task_service_units.py tests/test_storage_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/storage/tasks/skip_rules.py backend/app/modules/storage/tasks/target_locations.py backend/app/modules/storage/tasks/serializers.py backend/app/modules/storage/tasks/service.py backend/tests/test_storage_task_service_units.py
git commit -m "refactor: extract storage task service helpers"
```

---

### Task 5: Extract Storage Task Creation Flow

**Files:**
- Create: `backend/app/modules/storage/tasks/creation.py`
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/tests/test_storage_task_service_units.py`
- Modify: `backend/tests/test_storage_tasks_api.py`

**Interfaces:**
- Consumes from Task 4:
  - `classify_storage_skip(movie)`
  - `resolve_target_locations(db, movie, source, selected_storage_location)`
- Produces:
  - `StorageTaskCreator.create_main_task(movie_ids, user_id, source, alias, storage_mode, selected_storage_location) -> StorageMainTask`

- [ ] **Step 1: Add creator unit test**

Append to `backend/tests/test_storage_task_service_units.py`:

```python
def test_storage_task_creator_creates_skipped_subtask_for_movie_without_magnets(db_session, test_user) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.creation import StorageTaskCreator
    from backend.app.modules.storage.tasks.repository import StorageTaskRepository

    movie = Movie(code="NO-MAG", source_name="No Magnet")
    db_session.add(movie)
    db_session.flush()

    class ConfigService:
        def get_raw_config(self):
            return {"target_folder": "/Movies"}

    creator = StorageTaskCreator(
        db=db_session,
        repository=StorageTaskRepository(db_session),
        config_service=ConfigService(),
    )

    main = creator.create_main_task(
        movie_ids=[movie.id],
        user_id=test_user.id,
        source="single",
        alias="manual",
        storage_mode="single",
        selected_storage_location=None,
    )

    assert main.alias == "manual"
    assert main.subtasks[0].status == "skipped"
    assert main.subtasks[0].skip_reason == "no_magnets"
```

- [ ] **Step 2: Run creator test and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_task_service_units.py::test_storage_task_creator_creates_skipped_subtask_for_movie_without_magnets -v
```

Expected: FAIL because `backend.app.modules.storage.tasks.creation` does not exist.

- [ ] **Step 3: Create `creation.py`**

Create `backend/app/modules/storage/tasks/creation.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.content.movies.storage_status import (
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORING,
    set_movie_storage_status,
)
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.tasks.policies import generate_default_alias
from backend.app.modules.storage.tasks.repository import StorageTaskRepository
from backend.app.modules.storage.tasks.skip_rules import classify_storage_skip
from backend.app.modules.storage.tasks.target_locations import resolve_target_locations
from shared.database.models.content import Movie
```

Add class:

```python
class StorageTaskCreator:
    def __init__(self, db: Session, repository: StorageTaskRepository, config_service) -> None:
        self.db = db
        self.repository = repository
        self.config_service = config_service

    def create_main_task(
        self,
        *,
        movie_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        source: str,
        alias: str | None,
        storage_mode: str,
        selected_storage_location: str | None,
    ) -> StorageMainTask:
        if storage_mode not in {"single", "multiple"}:
            raise ValueError("storage_mode must be single or multiple")

        now = datetime.now(timezone.utc)
        sequence = self.repository.count_today_main_tasks() + 1
        final_alias = alias or generate_default_alias(now, sequence)
        main_task = StorageMainTask(
            alias=final_alias,
            display_name=final_alias,
            source=source,
            storage_mode=storage_mode,
            status="queued",
            total_count=0,
            created_by=user_id,
            queued_at=now,
            config_snapshot=self.config_service.get_raw_config(),
        )
        self.db.add(main_task)
        self.db.flush()

        movies = self._load_movies(movie_ids)
        movie_map = {movie.id: movie for movie in movies}
        for movie_id in movie_ids:
            self._create_subtask(
                main_task=main_task,
                movie=movie_map.get(movie_id),
                movie_id=movie_id,
                source=source,
                storage_mode=storage_mode,
                selected_storage_location=selected_storage_location,
                user_id=user_id,
            )

        self.repository.recompute_counts(main_task)
        return main_task
```

Move these private methods from `StorageTaskService` into `StorageTaskCreator` with the same behavior:

```python
_load_movies
_create_subtask
_update_movie_storage_summary
```

Inside moved `_create_subtask`, replace calls:

```python
self._classify_skip(movie, movie_id)
self._resolve_target_locations(movie, source, selected_storage_location)
```

with:

```python
classify_storage_skip(movie)
resolve_target_locations(self.db, movie, source, selected_storage_location)
```

- [ ] **Step 4: Rewire `StorageTaskService._create_main_task`**

In `backend/app/modules/storage/tasks/service.py`, import:

```python
from backend.app.modules.storage.tasks.creation import StorageTaskCreator
```

Replace the body of `_create_main_task` with:

```python
creator = StorageTaskCreator(
    db=self.db,
    repository=self.repository,
    config_service=self.config_service,
)
main_task = creator.create_main_task(
    movie_ids=movie_ids,
    user_id=user_id,
    source=source,
    alias=alias,
    storage_mode=storage_mode,
    selected_storage_location=selected_storage_location,
)
self.db.commit()
self.db.refresh(main_task)

has_queued = any(subtask.status == "queued" for subtask in main_task.subtasks)
if has_queued and self.runtime is not None:
    self.runtime.enqueue_main_task(str(main_task.id))
    ensure_storage_worker_started(
        self.runtime,
        self.config_service.provider_factory,
        self.config_service,
    )

return main_task
```

Delete `_load_movies`, `_create_subtask`, `_classify_skip`, `_resolve_target_locations`, and `_update_movie_storage_summary` from `StorageTaskService` after the moved code is covered by `StorageTaskCreator`.

- [ ] **Step 5: Run storage task tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_task_service_units.py tests/test_storage_tasks_api.py tests/test_storage_task_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Verify service no longer owns creation internals**

Run:

```bash
rg -n "def _load_movies|def _create_subtask|def _classify_skip|def _resolve_target_locations|def _update_movie_storage_summary" backend/app/modules/storage/tasks/service.py
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/storage/tasks/creation.py backend/app/modules/storage/tasks/service.py backend/tests/test_storage_task_service_units.py backend/tests/test_storage_tasks_api.py
git commit -m "refactor: extract storage task creation flow"
```

---

### Task 6: Add Movie Query SQL Builder For Scalar Filters

**Files:**
- Create: `backend/tests/test_content_movie_queries_sql.py`
- Modify: `backend/app/modules/content/movies/queries.py`

**Interfaces:**
- Produces:
  - `requires_python_fallback(db: Session, filters: MovieListFilters) -> bool`
  - `build_movie_list_statement(filters: MovieListFilters, *, sort_by: str, sort_order: int | str)`
  - `count_movies_for_statement(db: Session, statement) -> int`

- [ ] **Step 1: Write SQL query builder tests**

Create `backend/tests/test_content_movie_queries_sql.py`:

```python
from datetime import date
from decimal import Decimal

from backend.app.modules.content.movies.queries import MovieListFilters, list_movies_page
from shared.database.models.content import Movie


def seed_query_movies(db_session) -> None:
    db_session.add_all([
        Movie(
            code="AAA-100",
            source_url="https://example.test/aaa",
            source_name="Alpha Movie",
            release_date=date(2026, 1, 10),
            rating=Decimal("4.8"),
            director="Director A",
            maker="Maker A",
            series="Series A",
            actors=["Actor A"],
            tags=["Tag A"],
        ),
        Movie(
            code="BBB-200",
            source_url="https://example.test/bbb",
            source_name="Beta Movie",
            release_date=date(2026, 2, 20),
            rating=Decimal("2.2"),
            director="Director B",
            maker="Maker B",
            series="Series B",
            actors=["Actor B"],
            tags=["Tag B"],
        ),
    ])
    db_session.commit()


def test_list_movies_page_pushes_scalar_filters_and_sorting(db_session) -> None:
    seed_query_movies(db_session)

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(
            search="Movie",
            rating_min=4,
            release_date_from="2026-01-01",
            release_date_to="2026-01-31",
            director="Director A",
            maker="Maker A",
            series="Series A",
        ),
        sort_by="rating",
        sort_order=-1,
        page=1,
        limit=20,
        skip=None,
    )

    assert total == 1
    assert [movie.code for movie in rows] == ["AAA-100"]


def test_list_movies_page_uses_sql_offset_and_limit_for_scalar_filters(db_session) -> None:
    seed_query_movies(db_session)

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(search="Movie"),
        sort_by="code",
        sort_order="asc",
        page=2,
        limit=1,
        skip=None,
    )

    assert total == 2
    assert [movie.code for movie in rows] == ["BBB-200"]
```

- [ ] **Step 2: Run query tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py -v
```

Expected: PASS with current Python implementation. These tests lock behavior before changing execution strategy.

- [ ] **Step 3: Add SQL builder helpers**

In `backend/app/modules/content/movies/queries.py`, add imports:

```python
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import Select, and_, false, func, not_, or_
```

Add helper functions:

```python
def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_datetime_date(value: str | None) -> date | None:
    return _parse_date(value)


def _case_insensitive_like(column, value: str):
    return func.lower(column).like(f"%{value.lower()}%")


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
```

Add fallback detector:

```python
def requires_python_fallback(db: Session, filters: MovieListFilters) -> bool:
    if filters.storage_status:
        return True
    if db.bind.dialect.name == "sqlite":
        return bool(
            filters.source_task_id
            or filters.actors
            or filters.actors_not
            or filters.actors_count_min is not None
            or filters.actors_count_max is not None
            or filters.tags
            or filters.tags_not
        )
    return False
```

Add builder:

```python
def build_movie_list_statement(
    filters: MovieListFilters,
    *,
    sort_by: str,
    sort_order: int | str,
) -> Select:
    stmt = select(Movie).options(selectinload(Movie.magnets))
    conditions = []

    if filters.search:
        conditions.append(or_(
            _case_insensitive_like(Movie.code, filters.search),
            _case_insensitive_like(Movie.source_name, filters.search),
            _case_insensitive_like(Movie.director, filters.search),
            _case_insensitive_like(Movie.maker, filters.search),
            _case_insensitive_like(Movie.series, filters.search),
        ))
    if filters.rating_min is not None:
        conditions.append(Movie.rating >= filters.rating_min)
    if filters.rating_max is not None:
        conditions.append(Movie.rating <= filters.rating_max)

    release_from = _parse_date(filters.release_date_from)
    release_to = _parse_date(filters.release_date_to)
    if release_from is not None:
        conditions.append(Movie.release_date >= release_from)
    if release_to is not None:
        conditions.append(Movie.release_date <= release_to)

    created_from = _parse_datetime_date(filters.created_at_from)
    created_to = _parse_datetime_date(filters.created_at_to)
    if created_from is not None:
        conditions.append(func.date(Movie.created_at) >= created_from.isoformat())
    if created_to is not None:
        conditions.append(func.date(Movie.created_at) <= created_to.isoformat())

    for value in split_csv(filters.director):
        conditions.append(Movie.director == value)
    for value in split_csv(filters.director_not):
        conditions.append(Movie.director != value)
    for value in split_csv(filters.maker):
        conditions.append(Movie.maker == value)
    for value in split_csv(filters.maker_not):
        conditions.append(Movie.maker != value)
    for value in split_csv(filters.series):
        conditions.append(Movie.series == value)
    for value in split_csv(filters.series_not):
        conditions.append(Movie.series != value)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    normalized_sort_order = normalize_sort_order(sort_order)
    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Movie.created_at)
    order_expression = sort_column.asc() if normalized_sort_order == 1 else sort_column.desc()
    return stmt.order_by(order_expression)
```

Add count helper:

```python
def count_movies_for_statement(db: Session, statement: Select) -> int:
    count_stmt = select(func.count()).select_from(statement.order_by(None).subquery())
    return int(db.scalar(count_stmt) or 0)
```

- [ ] **Step 4: Rewire SQL-only path in `list_movies_page`**

Replace the start of `list_movies_page` with:

```python
    offset = skip if skip is not None else (page - 1) * limit
    statement = build_movie_list_statement(filters, sort_by=sort_by, sort_order=sort_order)
    if not requires_python_fallback(db, filters):
        total = count_movies_for_statement(db, statement)
        rows = list(db.scalars(statement.offset(offset).limit(limit)).unique().all())
        return rows, total
```

Keep the existing Python filtering branch below this block for fallback filters.

- [ ] **Step 5: Run movie query focused tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py tests/test_content_movies_api.py::test_list_movies_supports_original_filter_contract -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/queries.py backend/tests/test_content_movie_queries_sql.py
git commit -m "refactor: add movie query sql builder"
```

---

### Task 7: Add Movie Query Fallback And PostgreSQL Array Branches

**Files:**
- Modify: `backend/app/modules/content/movies/queries.py`
- Modify: `backend/tests/test_content_movie_queries_sql.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes from Task 6:
  - `requires_python_fallback(db, filters)`
  - `build_movie_list_statement(filters, sort_by, sort_order)`
  - `count_movies_for_statement(db, statement)`
- Produces: SQL prefilter plus Python fallback for storage status and SQLite array filters.

- [ ] **Step 1: Add fallback behavior tests**

Append to `backend/tests/test_content_movie_queries_sql.py`:

```python
def test_list_movies_page_preserves_storage_status_fallback(db_session) -> None:
    db_session.add_all([
        Movie(code="STORE-1", source_url="https://example.test/store1", source_name="Stored", storage_summary={"storage_status": "stored", "last_status": "stored"}),
        Movie(code="STORE-2", source_url="https://example.test/store2", source_name="Missing", storage_summary={}),
    ])
    db_session.commit()

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(storage_status="not_stored"),
        sort_by="code",
        sort_order="asc",
        page=1,
        limit=20,
        skip=None,
    )

    assert total == 1
    assert [movie.code for movie in rows] == ["STORE-2"]


def test_list_movies_page_preserves_sqlite_array_filter_fallback(db_session) -> None:
    seed_query_movies(db_session)

    rows, total = list_movies_page(
        db_session,
        MovieListFilters(actors="Actor A", tags_not="Tag B"),
        sort_by="code",
        sort_order="asc",
        page=1,
        limit=20,
        skip=None,
    )

    assert total == 1
    assert [movie.code for movie in rows] == ["AAA-100"]
```

- [ ] **Step 2: Run fallback tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py::test_list_movies_page_preserves_storage_status_fallback tests/test_content_movie_queries_sql.py::test_list_movies_page_preserves_sqlite_array_filter_fallback -v
```

Expected: PASS with the existing Python fallback branch.

- [ ] **Step 3: Ensure fallback prefilters before Python filtering**

In `backend/app/modules/content/movies/queries.py`, replace the fallback branch:

```python
    rows = db.query(Movie).options(selectinload(Movie.magnets)).all()
```

with:

```python
    rows = list(db.scalars(statement).unique().all())
```

Keep this code after it:

```python
    filtered = [movie for movie in rows if movie_matches(movie, filters)]
```

This preserves Python fallback for storage status and SQLite array filters while applying safe SQL filters first.

- [ ] **Step 4: Add PostgreSQL array conditions behind dialect guard**

In `build_movie_list_statement`, add an optional keyword:

```python
def build_movie_list_statement(
    filters: MovieListFilters,
    *,
    sort_by: str,
    sort_order: int | str,
    dialect_name: str | None = None,
) -> Select:
```

In `list_movies_page`, call:

```python
statement = build_movie_list_statement(
    filters,
    sort_by=sort_by,
    sort_order=sort_order,
    dialect_name=db.bind.dialect.name,
)
```

Inside `build_movie_list_statement`, after scalar filters, add:

```python
    if dialect_name == "postgresql":
        if filters.source_task_id:
            source_task_id = _parse_uuid(filters.source_task_id)
            if source_task_id is not None:
                conditions.append(Movie.source_task_ids.contains([source_task_id]))
            else:
                conditions.append(false())
        for actor in split_csv(filters.actors):
            conditions.append(Movie.actors.contains([actor]))
        for actor in split_csv(filters.actors_not):
            conditions.append(not_(Movie.actors.contains([actor])))
        for tag in split_csv(filters.tags):
            conditions.append(Movie.tags.contains([tag]))
        for tag in split_csv(filters.tags_not):
            conditions.append(not_(Movie.tags.contains([tag])))
        if filters.actors_count_min is not None:
            conditions.append(func.array_length(Movie.actors, 1) >= filters.actors_count_min)
        if filters.actors_count_max is not None:
            conditions.append(func.array_length(Movie.actors, 1) <= filters.actors_count_max)
```

Keep SQLite fallback active through `requires_python_fallback`.

- [ ] **Step 5: Run movie query and API tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Verify no full-table path remains for SQL-only filters**

Run:

```bash
rg -n "db\.query\(Movie\).*\.all\(\)|select\(Movie\).*offset|requires_python_fallback|build_movie_list_statement" backend/app/modules/content/movies/queries.py
```

Expected: output includes `requires_python_fallback` and `build_movie_list_statement`; output does not include `db.query(Movie).options(selectinload(Movie.magnets)).all()` in `list_movies_page`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/content/movies/queries.py backend/tests/test_content_movie_queries_sql.py backend/tests/test_content_movies_api.py
git commit -m "refactor: add movie query fallback execution"
```

---

### Task 8: Final Verification

**Files:**
- Modify only if verification exposes integration failures.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: verified BC follow-up optimization.

- [ ] **Step 1: Run active-code legacy reference checks**

Run:

```bash
rg -n "legacyCrawlTasksRoute|/crawl-tasks|backend\.app\.modules\.movies|app\.modules\.movies|scraper\.services\.movie_service|scraper\.database\.repositories" frontend/src backend/app backend/tests shared scraper -g '*.py' -g '*.ts' -g '*.tsx'
```

Expected: no output.

- [ ] **Step 2: Run storage worker focused tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py tests/test_storage_worker_target_files.py tests/test_storage_file_finder_scope.py tests/test_storage_worker_service.py tests/test_storage_worker_timeline.py -v
```

Expected: PASS.

- [ ] **Step 3: Run storage task focused tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_task_service_units.py tests/test_storage_tasks_api.py tests/test_storage_task_models.py tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 4: Run content movie focused tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py tests/test_content_movies_api.py tests/test_movie_persistence.py tests/test_movie_delete_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Run backend full test suite**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 6: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: PASS.

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 8: Run frontend lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 9: Inspect final status**

Run:

```bash
git status --short
```

Expected: no unstaged tracked changes from this plan. Pre-existing untracked plan files may still appear and should not be staged unless the user explicitly asks.

- [ ] **Step 10: Report verification result**

If Steps 1-9 pass with no tracked changes, report that the branch is verified.
If a verification step fails, stop and fix the failing task's owning files in
the task where the regression was introduced, then rerun that task's focused
tests before rerunning final verification.
