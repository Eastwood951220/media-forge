# Fullstack Structure Follow-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the current structure cleanup by removing duplicate backend helper logic, splitting remaining large backend modules, and lightly splitting large frontend pages without changing behavior.

**Architecture:** Keep current public APIs stable while moving implementation into focused same-domain modules. Backend phases run first so duplicate and high-coupling code is removed before frontend structural cleanup. Frontend changes are local module moves only: components, hooks, and pure utilities leave page files, but routes, UI, API calls, and realtime behavior stay unchanged.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, Vitest, ESLint.

## Global Constraints

- Do not change database schema or Alembic migrations.
- Do not change API response shapes or request parameters.
- Do not change crawler run semantics, crawler detail statuses, or dedupe behavior.
- Do not change storage worker behavior, CloudDrive2 calls, retry policy, or step names.
- Do not change frontend routes, visual layout, Ant Design component choices, or realtime subscription semantics.
- Do not introduce new state management libraries.
- Do not remove historical docs or previous plan files.
- Leave pre-existing untracked plan files unstaged unless the user explicitly asks to stage them.

---

## File Structure

### Create

- `backend/app/modules/crawler/runtime/events.py`
  - Owns run owner lookup, realtime event publication, and run log publication.
- `backend/app/modules/crawler/runtime/details.py`
  - Owns detail status constants, detail reset/clear/count helpers, and detail row conversion.
- `backend/app/modules/crawler/runtime/executor.py`
  - Owns crawl execution and engine callbacks.
- `backend/app/modules/crawler/runtime/worker.py`
  - Owns worker lock, worker loop, interrupted cleanup, `process_next_run`, and `process_run`.
- `backend/app/modules/storage/worker/file_identity.py`
  - Owns remote file normalization and original path resolution.
- `backend/app/modules/storage/worker/file_candidates.py`
  - Owns candidate accept/reject rules.
- `backend/app/modules/storage/worker/file_result.py`
  - Owns `ScopedSearchResult`.
- `backend/app/modules/storage/worker/file_listing.py`
  - Owns recursive list scanning and `find_listed_video_files`.
- `backend/app/modules/storage/worker/file_search.py`
  - Owns scoped search, existing file search, and recovery search.
- `backend/app/modules/content/movies/filters.py`
  - Owns `MovieListFilters`, `split_csv`, and `VALID_FILTER_TYPES`.
- `backend/app/modules/content/movies/filter_options.py`
  - Owns movie filter option lookup.
- `backend/app/modules/content/movies/fallback.py`
  - Owns Python fallback matching.
- `backend/app/modules/content/movies/sql_builder.py`
  - Owns SQL statement building, parsing helpers, fallback detection, count, and sort normalization.
- `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx`
- `frontend/src/pages/crawler/tasks/hooks/useTaskFormSubmit.ts`
- `frontend/src/pages/storage/config/components/SectionTitle.tsx`
- `frontend/src/pages/storage/config/components/SelectTags.tsx`
- `frontend/src/pages/storage/config/components/TestResultCard.tsx`
- `frontend/src/pages/storage/config/utils/error.ts`
- `frontend/src/pages/storage/tasks/components/SubtaskStepTimeline.tsx`
- `frontend/src/pages/storage/tasks/components/SubtaskLogList.tsx`
- `frontend/src/pages/storage/tasks/utils/format.ts`
- `frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts`
- `frontend/src/pages/content/movies/utils/sort.ts`

### Modify

- `backend/app/modules/storage/tasks/service.py`
  - Delegate to already-extracted storage task helpers and delete duplicate private methods.
- `backend/tests/test_storage_task_service_units.py`
  - Add service facade regression.
- `backend/app/modules/crawler/runtime/service.py`
  - Become a facade for service methods and compatibility imports.
- `backend/tests/test_crawler_worker_service.py`
  - Keep importing from `service.py`; tests verify compatibility imports.
- `backend/app/modules/storage/worker/file_finder.py`
  - Become a compatibility facade.
- `backend/tests/test_storage_file_finder_scope.py`
  - Add focused candidate/original path regression coverage.
- `backend/app/modules/content/movies/queries.py`
  - Become a facade and re-export stable public query names.
- `backend/tests/test_content_movie_queries_sql.py`
  - Add import compatibility regression.
- Frontend page files:
  - `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
  - `frontend/src/pages/storage/config/StorageConfigPage.tsx`
  - `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`
  - `frontend/src/pages/content/movies/MovieListPage.tsx`

---

### Task 1: Wire Storage Task Service To Extracted Helpers

**Files:**
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/tests/test_storage_task_service_units.py`

**Interfaces:**
- Consumes:
  - `StorageTaskCreator.create_main_task(movie_ids, user_id, source, alias, storage_mode, selected_storage_location) -> StorageMainTask`
  - `storage_main_task_to_dict(task: StorageMainTask) -> dict`
  - `storage_subtask_to_dict(task: StorageSubTask) -> dict`
- Produces:
  - `StorageTaskService._create_main_task(movie_ids, user_id, source, alias, storage_mode, selected_storage_location) -> StorageMainTask` delegates creation.
  - `StorageTaskService.to_main_response(task) -> dict` delegates serialization.
  - `StorageTaskService.to_subtask_response(task) -> dict` delegates serialization.

- [ ] **Step 1: Add service facade regression**

Append this test to `backend/tests/test_storage_task_service_units.py`:

```python
def test_storage_task_service_create_single_push_uses_creator_path(db_session, test_user, monkeypatch) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.schemas import StorageSinglePushRequest
    from backend.app.modules.storage.tasks.service import StorageTaskService
    from shared.database.models.content import Movie

    movie = Movie(code="SVC-001", source_name="Service Movie")
    db_session.add(movie)
    db_session.flush()

    class ConfigService:
        provider_factory = None

        def get_raw_config(self):
            return {"target_folder": "/Movies"}

    service = StorageTaskService(db_session, ConfigService(), runtime=None)
    body = StorageSinglePushRequest(
        movie_id=movie.id,
        alias="service-path",
        storage_mode="single",
        selected_storage_location=None,
    )

    main_task = service.create_single_push(body, test_user.id)

    assert main_task.alias == "service-path"
    assert main_task.subtasks[0].status == "skipped"
    assert main_task.subtasks[0].skip_reason == "no_magnets"
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_task_service_units.py::test_storage_task_service_create_single_push_uses_creator_path -v
```

Expected: PASS, proving current behavior before deleting duplicate code.

- [ ] **Step 3: Import extracted helpers in service**

In `backend/app/modules/storage/tasks/service.py`, add:

```python
from backend.app.modules.storage.tasks.creation import StorageTaskCreator
from backend.app.modules.storage.tasks.serializers import (
    storage_main_task_to_dict,
    storage_subtask_to_dict,
)
```

Remove imports that become unused after deletion:

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.app.modules.content.movies.storage_status import (
    STORAGE_STATUS_NOT_STORED,
    STORAGE_STATUS_STORING,
    set_movie_storage_status,
)
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from shared.database.models.content import Movie
```

Keep these imports because service still uses them:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.tasks.logs import delete_storage_subtask_log
from backend.app.modules.storage.tasks.policies import generate_default_alias
from backend.app.modules.storage.tasks.repository import StorageTaskRepository
from backend.app.modules.storage.tasks.schemas import (
    StorageBatchPushRequest,
    StorageMainTaskResponse,
    StorageSinglePushRequest,
)
from backend.app.modules.storage.worker.runner import ensure_storage_worker_started
```

- [ ] **Step 4: Delegate response serializers**

Replace `to_main_response` body with:

```python
    def to_main_response(self, task: StorageMainTask) -> dict:
        return storage_main_task_to_dict(task)
```

Replace `to_subtask_response` body with:

```python
    def to_subtask_response(self, task: StorageSubTask) -> dict:
        return storage_subtask_to_dict(task)
```

- [ ] **Step 5: Delegate creation and delete duplicate private helpers**

Replace the full body of `_create_main_task` with:

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

Delete these methods from `StorageTaskService`:

```python
_load_movies
_create_subtask
_classify_skip
_resolve_target_locations
_update_movie_storage_summary
```

- [ ] **Step 6: Run storage task tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_task_service_units.py tests/test_storage_tasks_api.py tests/test_storage_task_models.py -v
```

Expected: PASS.

- [ ] **Step 7: Verify duplicate helpers are gone**

Run:

```bash
rg -n "def _load_movies|def _create_subtask|def _classify_skip|def _resolve_target_locations|def _update_movie_storage_summary|set_movie_storage_status|write_storage_subtask_log" backend/app/modules/storage/tasks/service.py
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/storage/tasks/service.py backend/tests/test_storage_task_service_units.py
git commit -m "refactor: wire storage task service helpers"
```

---

### Task 2: Extract Crawler Runtime Events And Details

**Files:**
- Create: `backend/app/modules/crawler/runtime/events.py`
- Create: `backend/app/modules/crawler/runtime/details.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Produces:
  - `publish_run_updated(db: Session, run: CrawlRun) -> None`
  - `publish_run_detail_updated(db: Session, run: CrawlRun, details: list[CrawlRunDetailTask]) -> None`
  - `publish_queue_updated(db: Session, runtime: CrawlerRuntimeState, owner_id: str | None = None) -> None`
  - `append_run_log_for_run(db: Session, run: CrawlRun, message: str, level: str = "INFO", **context: Any) -> None`
  - `has_detail_phase_started(db: Session, run: CrawlRun) -> bool`
  - `reset_unfinished_detail_tasks_to_pending(db: Session, run: CrawlRun) -> list[CrawlRunDetailTask]`
  - `clear_run_detail_tasks(db: Session, run: CrawlRun) -> None`
  - `count_run_detail_tasks(db: Session, run_id: uuid.UUID, status: str | None = None) -> int`
  - `detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]`

- [ ] **Step 1: Add compatibility import regression**

Append this test to `backend/tests/test_crawler_worker_service.py`:

```python
def test_crawler_runtime_service_keeps_public_runtime_imports() -> None:
    from backend.app.modules.crawler.runtime import service

    assert callable(service.process_next_run)
    assert callable(service.process_run)
    assert callable(service.publish_run_updated)
    assert callable(service.publish_run_detail_updated)
    assert callable(service.append_run_log_for_run)
```

- [ ] **Step 2: Run compatibility test**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_crawler_runtime_service_keeps_public_runtime_imports -v
```

Expected: PASS before extraction and PASS after extraction.

- [ ] **Step 3: Create `details.py`**

Create `backend/app/modules/crawler/runtime/details.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask

UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawl_failed", "save_failed"}
RESTARTABLE_DETAIL_STATUSES = UNFINISHED_DETAIL_STATUSES
TERMINAL_DETAIL_STATUSES = {"saved", "skipped"}
DETAIL_PHASE_STARTED_STATUSES = {"saved", "crawl_failed", "save_failed"}


def has_detail_phase_started(db: Session, run: CrawlRun) -> bool:
    return db.query(CrawlRunDetailTask.id).filter(
        CrawlRunDetailTask.run_id == run.id,
        (
            CrawlRunDetailTask.status.in_(DETAIL_PHASE_STARTED_STATUSES)
            | CrawlRunDetailTask.crawled_at.isnot(None)
            | CrawlRunDetailTask.saved_at.isnot(None)
        ),
    ).first() is not None


def reset_unfinished_detail_tasks_to_pending(
    db: Session,
    run: CrawlRun,
) -> list[CrawlRunDetailTask]:
    details = (
        db.query(CrawlRunDetailTask)
        .filter(
            CrawlRunDetailTask.run_id == run.id,
            CrawlRunDetailTask.status.notin_(TERMINAL_DETAIL_STATUSES),
        )
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    for detail in details:
        detail.status = "pending_crawl"
        detail.error = None
        detail.crawled_at = None
        detail.saved_at = None
    db.flush()
    return details


def clear_run_detail_tasks(db: Session, run: CrawlRun) -> None:
    db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete(synchronize_session=False)


def count_run_detail_tasks(db: Session, run_id: uuid.UUID, status: str | None = None) -> int:
    query = db.query(func.count(CrawlRunDetailTask.id)).filter(CrawlRunDetailTask.run_id == run_id)
    if status is not None:
        query = query.filter(CrawlRunDetailTask.status == status)
    return int(query.scalar() or 0)


def detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]:
    return {
        "code": detail.code,
        "url": detail.source_url,
        "name": detail.source_name,
    }
```

- [ ] **Step 4: Create `events.py`**

Create `backend/app/modules/crawler/runtime/events.py`:

```python
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.tasks.runtime_status import publish_task_status_updated

logger = logging.getLogger(__name__)


def run_owner_id(db: Session, run: CrawlRun) -> str | None:
    if run.task_id is None:
        return None
    task = db.get(CrawlTask, run.task_id)
    return str(task.owner_id) if task is not None else None
```

Move these functions from `service.py` into this file without changing payload shapes:

```python
publish_run_updated
publish_run_detail_updated
publish_queue_updated
append_run_log_for_run
```

Inside the moved functions, replace `_run_owner_id(db, run)` with `run_owner_id(db, run)`.

- [ ] **Step 5: Rewire `service.py` imports**

In `backend/app/modules/crawler/runtime/service.py`, import:

```python
from backend.app.modules.crawler.runtime.details import (
    RESTARTABLE_DETAIL_STATUSES,
    clear_run_detail_tasks,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)
from backend.app.modules.crawler.runtime.events import (
    append_run_log_for_run,
    publish_queue_updated,
    publish_run_detail_updated,
    publish_run_updated,
)
```

Delete these local definitions from `service.py`:

```python
UNFINISHED_DETAIL_STATUSES
RESTARTABLE_DETAIL_STATUSES
TERMINAL_DETAIL_STATUSES
DETAIL_PHASE_STARTED_STATUSES
has_detail_phase_started
reset_unfinished_detail_tasks_to_pending
clear_run_detail_tasks
_append_run_log
_run_owner_id
publish_run_updated
publish_run_detail_updated
publish_queue_updated
append_run_log_for_run
```

- [ ] **Step 6: Run crawler runtime tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py tests/test_crawler_realtime_events.py tests/test_crawler_runs_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Verify moved definitions are not duplicated**

Run:

```bash
rg -n "def publish_run_updated|def publish_run_detail_updated|def append_run_log_for_run|def reset_unfinished_detail_tasks_to_pending|def has_detail_phase_started" backend/app/modules/crawler/runtime/service.py
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/runtime/events.py backend/app/modules/crawler/runtime/details.py backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "refactor: extract crawler runtime events and details"
```

---

### Task 3: Extract Crawler Runtime Worker And Executor

**Files:**
- Create: `backend/app/modules/crawler/runtime/worker.py`
- Create: `backend/app/modules/crawler/runtime/executor.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes from Task 2:
  - `append_run_log_for_run`
  - `publish_run_updated`
  - `publish_run_detail_updated`
  - `count_run_detail_tasks`
  - `detail_row_to_task_info`
- Produces:
  - `ensure_crawler_worker_started(runtime: CrawlerRuntimeState) -> None`
  - `cleanup_interrupted_runs(db: Session, runtime: CrawlerRuntimeState) -> int`
  - `process_next_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState) -> bool`
  - `process_run(db_factory: sessionmaker, runtime: CrawlerRuntimeState, run_id: str) -> bool`
  - `execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None`

- [ ] **Step 1: Rename executor monkeypatch targets in tests**

In `backend/tests/test_crawler_worker_service.py`, replace monkeypatch targets for execution:

```python
monkeypatch.setattr("backend.app.modules.crawler.runtime.service._execute_run", mock_execute_run)
```

with:

```python
monkeypatch.setattr("backend.app.modules.crawler.runtime.worker.execute_run", mock_execute_run)
```

Replace imports:

```python
from backend.app.modules.crawler.runtime.service import _execute_run
```

with:

```python
from backend.app.modules.crawler.runtime.executor import execute_run
```

Then replace every `_execute_run(session, session.get(CrawlRun, run.id), runtime)` call with `execute_run(session, session.get(CrawlRun, run.id), runtime)`.

- [ ] **Step 2: Create `executor.py`**

Create `backend/app/modules/crawler/runtime/executor.py` with imports:

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    sync_movie_filters,
    upsert_movie_with_magnets,
)
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
from backend.app.modules.crawler.runtime.details import (
    RESTARTABLE_DETAIL_STATUSES,
    count_run_detail_tasks,
    detail_row_to_task_info,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)
from backend.app.modules.crawler.runtime.engine import CrawlCallbacks, get_crawler_engine
from backend.app.modules.crawler.runtime.events import (
    append_run_log_for_run,
    publish_run_detail_updated,
    publish_run_updated,
)
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.source_task_names import (
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.app.modules.crawler.runtime.task_adapter import to_scraper_task

logger = logging.getLogger(__name__)
```

Move `_execute_run` from `service.py` into this file and rename it:

```python
def execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None:
```

Inside it:

```python
movie_id = _persist_crawled_item(db, item_data_with_task_ids)
```

becomes:

```python
movie_id = upsert_movie_with_magnets(db, item_data_with_task_ids)
```

and:

```python
incremental_threshold = _read_incremental_threshold_from_conf()
```

becomes:

```python
incremental_threshold = read_incremental_threshold_from_conf()
```

and calls such as `_count_run_detail_tasks(db, run.id, "saved")` become `count_run_detail_tasks(db, run.id, "saved")`.

- [ ] **Step 3: Create `worker.py`**

Create `backend/app/modules/crawler/runtime/worker.py`:

```python
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from shared.database.session import get_session_factory
from backend.app.models.crawl_run import CrawlRun
from backend.app.modules.crawler.runtime.details import reset_unfinished_detail_tasks_to_pending
from backend.app.modules.crawler.runtime.events import publish_run_updated
from backend.app.modules.crawler.runtime.executor import execute_run
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.tasks.runtime_status import publish_task_status_updated

logger = logging.getLogger(__name__)
_worker_lock = threading.Lock()
_worker_running = False
```

Move `cleanup_interrupted_runs`, `process_next_run`, and `process_run` from `service.py` into this file. In `process_run`, replace `_execute_run(db, run, runtime)` with `execute_run(db, run, runtime)`.

Add:

```python
def ensure_crawler_worker_started(runtime: CrawlerRuntimeState) -> None:
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
        thread = threading.Thread(target=_worker_loop, args=(runtime,), daemon=True)
        thread.start()


def _worker_loop(runtime: CrawlerRuntimeState) -> None:
    global _worker_running
    try:
        while True:
            run_id = runtime.claim_next_run()
            if run_id is None:
                break
            process_run(get_session_factory(), runtime, run_id)
    finally:
        with _worker_lock:
            _worker_running = False
```

- [ ] **Step 4: Rewire `CrawlerRunService`**

In `backend/app/modules/crawler/runtime/service.py`, import:

```python
from backend.app.modules.crawler.runtime.worker import (
    cleanup_interrupted_runs,
    ensure_crawler_worker_started,
    process_next_run,
    process_run,
)
```

Replace `_ensure_worker_started` body with:

```python
    def _ensure_worker_started(self) -> None:
        ensure_crawler_worker_started(self.runtime)
```

Delete `_worker_lock`, `_worker_running`, `_worker_loop`, `process_next_run`, `process_run`, `_read_incremental_threshold_from_conf`, `_persist_crawled_item`, and `_count_run_detail_tasks` from `service.py`.

- [ ] **Step 5: Run crawler worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py tests/test_crawler_runs_api.py tests/test_crawler_runtime_redis.py -v
```

Expected: PASS.

- [ ] **Step 6: Verify service is a facade**

Run:

```bash
rg -n "def _execute_run|def process_next_run|def process_run|def _worker_loop|def _persist_crawled_item|def _read_incremental_threshold_from_conf|def _count_run_detail_tasks|CrawlCallbacks\\(" backend/app/modules/crawler/runtime/service.py
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/worker.py backend/app/modules/crawler/runtime/executor.py backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "refactor: extract crawler runtime worker and executor"
```

---

### Task 4: Split Storage File Finder Identity And Candidate Rules

**Files:**
- Create: `backend/app/modules/storage/worker/file_identity.py`
- Create: `backend/app/modules/storage/worker/file_candidates.py`
- Modify: `backend/app/modules/storage/worker/file_finder.py`
- Modify: `backend/tests/test_storage_file_finder_scope.py`

**Interfaces:**
- Produces:
  - `raw_file_to_dict(file_obj) -> dict`
  - `is_virtual_search_path(path: str) -> bool`
  - `is_search_result(file_obj, raw_item: dict) -> bool`
  - `resolve_file_candidate(provider, file_obj) -> tuple[dict, dict, str | None, dict | None]`
  - `file_to_dict(provider, file_obj) -> dict`
  - `is_usable_video(file_dict: dict, config: dict) -> bool`
  - `path_is_under(path: str, folder: str) -> bool`
  - `movie_code_matches(file_dict: dict, movie_code: str) -> bool`
  - `rejection_reason(file_dict, *, config, movie_code, search_scope, task_download_folder) -> str | None`
  - `rejected_file(raw_item, resolved_item, reason, error=None) -> dict`
  - `append_candidate(*, raw_candidate, candidate, accepted, rejected, seen, config, movie_code, search_scope, task_download_folder, resolution_error=None) -> None`

- [ ] **Step 1: Add original path failure regression**

Append this test to `backend/tests/test_storage_file_finder_scope.py`:

```python
def test_search_result_original_path_failure_is_rejected() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    @dataclass
    class File:
        name: str
        full_path: str
        size: int
        is_directory: bool = False
        is_search_result: bool = True

    class Provider:
        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return [File("ABC-123.mp4", "/[Search]/ABC-123.mp4", 500 * 1024 * 1024)]

        def get_original_path(self, path):
            raise RuntimeError("original path failed")

        def list_files(self, path):
            return []

    result = find_scoped_video_files(
        provider=Provider(),
        search_terms=["ABC-123"],
        search_path="/Downloads",
        search_scope="download_root",
        movie_code="ABC-123",
        task_download_folder="/Downloads/storage-1",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert result.accepted_files == []
    assert result.log_context["rejected_files"][0]["reason"] == "missing_original_path"
```

- [ ] **Step 2: Run file finder regression**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_file_finder_scope.py::test_search_result_original_path_failure_is_rejected -v
```

Expected: PASS before extraction and PASS after extraction.

- [ ] **Step 3: Create `file_identity.py`**

Create `backend/app/modules/storage/worker/file_identity.py` and move these functions from `file_finder.py`, renaming public helpers by dropping the leading underscore:

```python
_raw_file_to_dict -> raw_file_to_dict
_is_virtual_search_path -> is_virtual_search_path
_is_search_result -> is_search_result
_resolve_file_candidate -> resolve_file_candidate
_file_to_dict -> file_to_dict
```

Use these imports:

```python
from __future__ import annotations

from pathlib import PurePosixPath
```

Update internal calls in moved code to the new helper names.

- [ ] **Step 4: Create `file_candidates.py`**

Create `backend/app/modules/storage/worker/file_candidates.py` and move these functions from `file_finder.py`, renaming public helpers by dropping the leading underscore:

```python
_is_usable_video -> is_usable_video
_path_is_under -> path_is_under
_movie_code_matches -> movie_code_matches
_rejection_reason -> rejection_reason
_rejected_file -> rejected_file
_append_candidate -> append_candidate
```

Use these imports:

```python
from __future__ import annotations

from pathlib import PurePosixPath

from backend.app.modules.storage.worker.file_identity import is_virtual_search_path
```

Update internal calls in moved code to the new helper names.

- [ ] **Step 5: Rewire `file_finder.py` to imported helpers**

In `backend/app/modules/storage/worker/file_finder.py`, import:

```python
from backend.app.modules.storage.worker.file_candidates import (
    append_candidate,
    is_usable_video,
    path_is_under,
    rejected_file,
)
from backend.app.modules.storage.worker.file_identity import (
    file_to_dict,
    is_virtual_search_path,
    raw_file_to_dict,
    resolve_file_candidate,
)
```

Replace calls:

```python
_raw_file_to_dict -> raw_file_to_dict
_is_virtual_search_path -> is_virtual_search_path
_file_to_dict -> file_to_dict
_is_usable_video -> is_usable_video
_path_is_under -> path_is_under
_rejected_file -> rejected_file
_append_candidate -> append_candidate
_resolve_file_candidate -> resolve_file_candidate
```

Delete the moved definitions from `file_finder.py`.

- [ ] **Step 6: Run storage file finder tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_file_finder_scope.py tests/test_storage_worker_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 7: Verify moved helpers are gone from facade**

Run:

```bash
rg -n "def _raw_file_to_dict|def _is_virtual_search_path|def _resolve_file_candidate|def _append_candidate|def _rejection_reason" backend/app/modules/storage/worker/file_finder.py
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/storage/worker/file_identity.py backend/app/modules/storage/worker/file_candidates.py backend/app/modules/storage/worker/file_finder.py backend/tests/test_storage_file_finder_scope.py
git commit -m "refactor: extract storage file identity and candidates"
```

---

### Task 5: Split Storage File Finder Listing And Search Flow

**Files:**
- Create: `backend/app/modules/storage/worker/file_result.py`
- Create: `backend/app/modules/storage/worker/file_listing.py`
- Create: `backend/app/modules/storage/worker/file_search.py`
- Modify: `backend/app/modules/storage/worker/file_finder.py`
- Modify: `backend/tests/test_storage_file_finder_scope.py`

**Interfaces:**
- Produces:
  - `ScopedSearchResult`
  - `find_listed_video_files(provider, search_path, search_scope, movie_code, task_download_folder, config) -> ScopedSearchResult`
  - `find_scoped_video_files(provider, search_terms, search_path, search_scope, movie_code, task_download_folder, config) -> ScopedSearchResult`
  - `find_existing_video_files(provider, search_terms, search_paths, config) -> list[dict]`
  - `find_recovery_video_files(provider, search_terms, task_download_folder, download_root, movie_code, config) -> ScopedSearchResult`

- [ ] **Step 1: Add public facade import regression**

Append this test to `backend/tests/test_storage_file_finder_scope.py`:

```python
def test_file_finder_facade_exports_public_search_functions() -> None:
    from backend.app.modules.storage.worker import file_finder

    assert callable(file_finder.find_listed_video_files)
    assert callable(file_finder.find_scoped_video_files)
    assert callable(file_finder.find_existing_video_files)
    assert callable(file_finder.find_recovery_video_files)
```

- [ ] **Step 2: Run facade import regression**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_file_finder_scope.py::test_file_finder_facade_exports_public_search_functions -v
```

Expected: PASS before extraction and PASS after extraction.

- [ ] **Step 3: Create `file_result.py`**

Create `backend/app/modules/storage/worker/file_result.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScopedSearchResult:
    accepted_files: list[dict]
    log_context: dict
```

- [ ] **Step 4: Create `file_listing.py`**

Create `backend/app/modules/storage/worker/file_listing.py` with:

```python
from __future__ import annotations

from pathlib import PurePosixPath

from backend.app.modules.storage.worker.file_candidates import (
    append_candidate,
    rejected_file,
)
from backend.app.modules.storage.worker.file_identity import (
    is_virtual_search_path,
    raw_file_to_dict,
)
from backend.app.modules.storage.worker.file_result import ScopedSearchResult
```

Move these functions from `file_finder.py`, renaming private helpers by dropping the leading underscore:

```python
_raw_entry_log -> raw_entry_log
_list_real_files_recursive -> list_real_files_recursive
_recursive_list -> recursive_list
find_listed_video_files
```

Update internal calls to use `append_candidate`, `rejected_file`, `is_virtual_search_path`, and `raw_file_to_dict`.

- [ ] **Step 5: Create `file_search.py`**

Create `backend/app/modules/storage/worker/file_search.py` with:

```python
from __future__ import annotations

from backend.app.modules.storage.worker.file_result import ScopedSearchResult
```

Move these functions from `file_finder.py`:

```python
find_scoped_video_files
find_existing_video_files
find_recovery_video_files
```

Add imports in `file_search.py`:

```python
from backend.app.modules.storage.worker.file_candidates import append_candidate
from backend.app.modules.storage.worker.file_identity import resolve_file_candidate
from backend.app.modules.storage.worker.file_listing import find_listed_video_files
```

For the recursive listing branch inside `find_scoped_video_files`, import and call `recursive_list` from `file_listing.py`.

- [ ] **Step 6: Convert `file_finder.py` to facade**

Replace `backend/app/modules/storage/worker/file_finder.py` contents with:

```python
from __future__ import annotations

from backend.app.modules.storage.worker.file_result import ScopedSearchResult
from backend.app.modules.storage.worker.file_listing import find_listed_video_files
from backend.app.modules.storage.worker.file_search import (
    find_existing_video_files,
    find_recovery_video_files,
    find_scoped_video_files,
)

__all__ = [
    "ScopedSearchResult",
    "find_existing_video_files",
    "find_listed_video_files",
    "find_recovery_video_files",
    "find_scoped_video_files",
]
```

- [ ] **Step 7: Run storage file finder and worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_file_finder_scope.py tests/test_storage_worker_pipeline.py tests/test_storage_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Verify facade is thin**

Run:

```bash
wc -l backend/app/modules/storage/worker/file_finder.py
rg -n "def " backend/app/modules/storage/worker/file_finder.py
```

Expected: line count is under 40 and `rg` prints no function definitions.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/worker/file_result.py backend/app/modules/storage/worker/file_listing.py backend/app/modules/storage/worker/file_search.py backend/app/modules/storage/worker/file_finder.py backend/tests/test_storage_file_finder_scope.py
git commit -m "refactor: split storage file finder search flow"
```

---

### Task 6: Split Movie Query Modules

**Files:**
- Create: `backend/app/modules/content/movies/filters.py`
- Create: `backend/app/modules/content/movies/filter_options.py`
- Create: `backend/app/modules/content/movies/fallback.py`
- Create: `backend/app/modules/content/movies/sql_builder.py`
- Modify: `backend/app/modules/content/movies/queries.py`
- Modify: `backend/tests/test_content_movie_queries_sql.py`

**Interfaces:**
- Produces:
  - `MovieListFilters`
  - `split_csv(value: str | None) -> list[str]`
  - `list_filter_values(db: Session, filter_type: str) -> list[str]`
  - `movie_matches(movie: Movie, filters: MovieListFilters) -> bool`
  - `build_movie_list_statement(filters, sort_by, sort_order, dialect_name=None) -> Select`
  - `requires_python_fallback(db: Session, filters: MovieListFilters) -> bool`
  - `count_movies_for_statement(db: Session, statement: Select) -> int`
  - `normalize_sort_order(sort_order: int | str) -> int`
  - `list_movies_page(db, filters, *, sort_by, sort_order, page, limit, skip) -> tuple[list[Movie], int]`

- [ ] **Step 1: Add query facade import regression**

Append this test to `backend/tests/test_content_movie_queries_sql.py`:

```python
def test_queries_module_keeps_public_imports() -> None:
    from backend.app.modules.content.movies import queries

    assert callable(queries.list_movies_page)
    assert callable(queries.list_filter_values)
    assert callable(queries.build_movie_list_statement)
    assert callable(queries.requires_python_fallback)
    assert callable(queries.movie_matches)
    assert queries.MovieListFilters(search="x").search == "x"
```

- [ ] **Step 2: Run query facade regression**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py::test_queries_module_keeps_public_imports -v
```

Expected: PASS before extraction and PASS after extraction.

- [ ] **Step 3: Create `filters.py`**

Create `backend/app/modules/content/movies/filters.py` and move:

```python
MovieListFilters
split_csv
VALID_FILTER_TYPES
```

Use:

```python
from __future__ import annotations

from dataclasses import dataclass

VALID_FILTER_TYPES = {"actor", "tag", "director", "maker", "series"}
```

- [ ] **Step 4: Create `filter_options.py`**

Create `backend/app/modules/content/movies/filter_options.py` and move:

```python
unique_sorted
sqlite_filter_values
cached_filter_values
list_filter_values
```

Use imports:

```python
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie, MovieFilter
```

- [ ] **Step 5: Create `fallback.py`**

Create `backend/app/modules/content/movies/fallback.py` and move `movie_matches`.

Use imports:

```python
from __future__ import annotations

from backend.app.modules.content.movies.filters import MovieListFilters, split_csv
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from shared.database.models.content import Movie
```

- [ ] **Step 6: Create `sql_builder.py`**

Create `backend/app/modules/content/movies/sql_builder.py` and move:

```python
ALLOWED_SORT_FIELDS
_parse_date
_parse_datetime_date
_case_insensitive_like
_parse_uuid
_postgres_array_contains
requires_python_fallback
build_movie_list_statement
count_movies_for_statement
normalize_sort_order
```

Use imports:

```python
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, false, func, not_, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.filters import MovieListFilters, split_csv
from shared.database.models.content import Movie
```

- [ ] **Step 7: Convert `queries.py` to facade**

Replace `backend/app/modules/content/movies/queries.py` content with:

```python
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.modules.content.movies.fallback import movie_matches
from backend.app.modules.content.movies.filter_options import list_filter_values
from backend.app.modules.content.movies.filters import (
    MovieListFilters,
    VALID_FILTER_TYPES,
    split_csv,
)
from backend.app.modules.content.movies.sql_builder import (
    ALLOWED_SORT_FIELDS,
    build_movie_list_statement,
    count_movies_for_statement,
    normalize_sort_order,
    requires_python_fallback,
)
from shared.database.models.content import Movie


def list_movies_page(
    db: Session,
    filters: MovieListFilters,
    *,
    sort_by: str,
    sort_order: int | str,
    page: int,
    limit: int,
    skip: int | None,
) -> tuple[list[Movie], int]:
    offset = skip if skip is not None else (page - 1) * limit
    statement = build_movie_list_statement(
        filters,
        sort_by=sort_by,
        sort_order=sort_order,
        dialect_name=db.bind.dialect.name,
    )

    if not requires_python_fallback(db, filters):
        total = count_movies_for_statement(db, statement)
        rows = list(db.scalars(statement.offset(offset).limit(limit)).unique().all())
        return rows, total

    rows = list(db.scalars(statement).unique().all())
    filtered = [movie for movie in rows if movie_matches(movie, filters)]
    total = len(filtered)
    return filtered[offset:offset + limit], total


__all__ = [
    "ALLOWED_SORT_FIELDS",
    "MovieListFilters",
    "VALID_FILTER_TYPES",
    "build_movie_list_statement",
    "count_movies_for_statement",
    "list_filter_values",
    "list_movies_page",
    "movie_matches",
    "normalize_sort_order",
    "requires_python_fallback",
    "split_csv",
]
```

- [ ] **Step 8: Run content movie tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py tests/test_content_movies_api.py tests/test_content_movie_serializers.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/content/movies/filters.py backend/app/modules/content/movies/filter_options.py backend/app/modules/content/movies/fallback.py backend/app/modules/content/movies/sql_builder.py backend/app/modules/content/movies/queries.py backend/tests/test_content_movie_queries_sql.py
git commit -m "refactor: split movie query modules"
```

---

### Task 7: Split Frontend Task Form And Storage Config Pages

**Files:**
- Create: `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx`
- Create: `frontend/src/pages/crawler/tasks/hooks/useTaskFormSubmit.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Create: `frontend/src/pages/storage/config/components/SectionTitle.tsx`
- Create: `frontend/src/pages/storage/config/components/SelectTags.tsx`
- Create: `frontend/src/pages/storage/config/components/TestResultCard.tsx`
- Create: `frontend/src/pages/storage/config/utils/error.ts`
- Modify: `frontend/src/pages/storage/config/StorageConfigPage.tsx`

**Interfaces:**
- Produces:
  - `UrlEntryCard` component with the same props currently used in `TaskFormPage.tsx`.
  - `useTaskFormSubmit` hook that returns submit handlers used by `TaskFormPage.tsx`.
  - `SectionTitle`, `SelectTags`, `TestResultCard`, and `getErrorMessage`.

- [ ] **Step 1: Extract `UrlEntryCard`**

Move the existing `UrlEntryCard` function from `TaskFormPage.tsx` to `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx`.

The new file must export a component with this signature and the full existing component body. Move the current return tree from `TaskFormPage.tsx`; do not replace it with a stub.

```tsx
import type { FormListFieldData } from 'antd/es/form/FormList'

export default function UrlEntryCard({
  field,
  index,
  remove,
}: {
  field: FormListFieldData
  index: number
  remove: (index: number | number[]) => void
}): JSX.Element
```

The committed file must contain the current `UrlEntryCard` return tree from `TaskFormPage.tsx`. Do not change field names, `Form.Item` name paths, extraction behavior, labels, or imports from `taskUrlUtils`.

- [ ] **Step 2: Import `UrlEntryCard` in page**

In `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`, delete the local `UrlEntryCard` function and add:

```ts
import UrlEntryCard from './components/UrlEntryCard'
```

- [ ] **Step 3: Extract task form submit hook**

Create `frontend/src/pages/crawler/tasks/hooks/useTaskFormSubmit.ts`:

```ts
import { App } from 'antd'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useState } from 'react'
import { createCrawlTask, updateCrawlTask } from '@/api/crawlTask'
import type { CrawlTaskCreateParams } from '@/api/crawlTask/types'

export function useTaskFormSubmit(
  taskId: string | undefined,
  isEdit: boolean,
  options: {
    onCancel: () => void
    onSuccess: () => void
  },
) {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [submitting, setSubmitting] = useState(false)

  const submit = useCallback(async (payload: CrawlTaskCreateParams) => {
    setSubmitting(true)
    try {
      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('任务已更新')
      } else {
        await createCrawlTask(payload)
        message.success('任务已创建')
      }
      options.onSuccess()
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }, [isEdit, message, navigate, options, taskId])

  const cancel = useCallback(() => {
    options.onCancel()
    void navigate({ to: '/crawler/tasks' })
  }, [navigate, options])

  return { cancel, submit, submitting }
}
```

Then update `TaskFormPage.tsx` to use this hook. Preserve duplicate URL checks, `enrichUrlEntries`, URL type validation, `form.setFieldsValue({ urls: enrichedEntries })`, and payload construction in the page before calling `submit(payload)`. Pass `onSuccess: closeCurrentTag` and `onCancel: () => { form.resetFields(); closeCurrentTag() }`.

- [ ] **Step 4: Extract storage config local components**

Move from `StorageConfigPage.tsx`:

```tsx
SectionTitle -> components/SectionTitle.tsx
SelectTags -> components/SelectTags.tsx
TestResultCard -> components/TestResultCard.tsx
getErrorMessage -> utils/error.ts
```

Exports:

```tsx
export default function SectionTitle({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <span className={styles.sectionTitle}>{icon}{text}</span>
}

export default function SelectTags({
  value,
  onChange,
  placeholder,
}: {
  value?: string[]
  onChange?: (val: string[]) => void
  placeholder?: string
}): JSX.Element

export default function TestResultCard({ result }: { result: StorageTestResult }): JSX.Element

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}
```

`SelectTags` must contain the current state, handlers, `Tag` list, and `Input` JSX from `StorageConfigPage.tsx`. `TestResultCard` must contain the current `items`, `failedItems`, `allPassed`, `Card`, `Descriptions`, and `Alert` implementation.

- [ ] **Step 5: Rewire storage config imports**

In `frontend/src/pages/storage/config/StorageConfigPage.tsx`, delete the moved local definitions and add:

```ts
import SectionTitle from './components/SectionTitle'
import SelectTags from './components/SelectTags'
import TestResultCard from './components/TestResultCard'
import { getErrorMessage } from './utils/error'
```

- [ ] **Step 6: Run frontend verification**

Run:

```bash
cd frontend
npm test -- --run
npm run build
npm run lint
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx frontend/src/pages/crawler/tasks/hooks/useTaskFormSubmit.ts frontend/src/pages/storage/config/StorageConfigPage.tsx frontend/src/pages/storage/config/components/SectionTitle.tsx frontend/src/pages/storage/config/components/SelectTags.tsx frontend/src/pages/storage/config/components/TestResultCard.tsx frontend/src/pages/storage/config/utils/error.ts
git commit -m "refactor: split task form and storage config pages"
```

---

### Task 8: Split Frontend Storage Subtask And Movie List Pages

**Files:**
- Create: `frontend/src/pages/storage/tasks/components/SubtaskStepTimeline.tsx`
- Create: `frontend/src/pages/storage/tasks/components/SubtaskLogList.tsx`
- Create: `frontend/src/pages/storage/tasks/utils/format.ts`
- Modify: `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`
- Create: `frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts`
- Create: `frontend/src/pages/content/movies/utils/sort.ts`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`

**Interfaces:**
- Produces:
  - `SubtaskStepTimeline`
  - `SubtaskLogList`
  - `formatTime`
  - `parseSortDefault`
  - `useMovieListRealtime`

- [ ] **Step 1: Extract storage subtask format utilities**

Create `frontend/src/pages/storage/tasks/utils/format.ts` and move:

```ts
export function formatTime(value: string) {
  if (!value) return '-'
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}
```

Also move `logsForStep` and `stepColor` from `StorageSubTaskDetailPage.tsx`, exporting both functions with these signatures:

```ts
export function logsForStep(logs: StorageTaskLog[], step: string): StorageTaskLog[]
export function stepColor(subtask: StorageSubTask, logs: StorageTaskLog[], step: string): 'red' | 'green' | 'blue' | 'gray'
```

- [ ] **Step 2: Extract subtask timeline component**

Create `frontend/src/pages/storage/tasks/components/SubtaskStepTimeline.tsx` and move the timeline JSX from `StorageSubTaskDetailPage.tsx`.

Export this component signature and move the current `Timeline` item construction from `StorageSubTaskDetailPage.tsx` into the component body:

```tsx
export default function SubtaskStepTimeline({
  subtask,
  logs,
}: {
  subtask: StorageSubTask
  logs: StorageTaskLog[]
}): JSX.Element
```

The committed component must contain the current `Timeline` rendering from `StorageSubTaskDetailPage.tsx`, including the current `stepOrder`, `stepLabels`, `logsForStep`, and `stepColor` usage.

- [ ] **Step 3: Extract subtask log list component**

Create `frontend/src/pages/storage/tasks/components/SubtaskLogList.tsx` and move the log list rendering from `StorageSubTaskDetailPage.tsx`.

Export this component signature and move the current log list rendering from `StorageSubTaskDetailPage.tsx` into the component body:

```tsx
export default function SubtaskLogList({ logs }: { logs: StorageTaskLog[] }): JSX.Element
```

The committed component must preserve log level colors, message text, context display, and timestamps.

- [ ] **Step 4: Rewire `StorageSubTaskDetailPage.tsx`**

Import:

```ts
import SubtaskStepTimeline from './components/SubtaskStepTimeline'
import SubtaskLogList from './components/SubtaskLogList'
import { formatTime } from './utils/format'
```

Delete the moved local helpers and JSX blocks. Replace them with the new components. Keep data loading and realtime effects in the page.

- [ ] **Step 5: Extract movie sort utility**

Create `frontend/src/pages/content/movies/utils/sort.ts`:

```ts
import type { MovieFilterConfig } from '@/api/movie/types'

export function parseSortDefault(config: MovieFilterConfig | undefined): { sortBy: string; sortOrder: number } | undefined {
  const raw = config?.sortBy?.defaultValue
  if (typeof raw !== 'string' || !raw.includes(':')) return undefined
  const [field, order] = raw.split(':')
  const parsed = Number(order)
  if (!field || (parsed !== 1 && parsed !== -1)) return undefined
  return { sortBy: field, sortOrder: parsed }
}
```

Delete the local `parseSortDefault` from `MovieListPage.tsx` and import this function.

- [ ] **Step 6: Extract movie realtime hook**

Create `frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts`:

```ts
import { useEffect } from 'react'
import type { Movie } from '@/api/movie/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { MovieStorageUpdatedPayload, RealtimeEvent } from '@/realtime/types'

export function useMovieListRealtime(
  updateMovie: (movieId: string, updater: (movie: Movie) => Movie) => void,
) {
  useEffect(() => {
    connectRealtime()
    const unsubscribe = subscribeRealtime<MovieStorageUpdatedPayload>(
      'movie.storage.updated',
      (event: RealtimeEvent<MovieStorageUpdatedPayload>) => {
        updateMovie(event.payload.movie_id, (movie) => ({
          ...movie,
          storage_status: String(event.payload.storage_summary.storage_status || 'not_stored') as Movie['storage_status'],
          storage_summary: {
            ...movie.storage_summary,
            ...event.payload.storage_summary,
          },
        }))
      },
    )
    return unsubscribe
  }, [updateMovie])
}
```

- [ ] **Step 7: Rewire `MovieListPage.tsx`**

Import:

```ts
import { useMovieListRealtime } from './hooks/useMovieListRealtime'
import { parseSortDefault } from './utils/sort'
```

Replace the moved realtime effect with:

```ts
useMovieListRealtime(list.updateMovie)
```

- [ ] **Step 8: Run frontend verification**

Run:

```bash
cd frontend
npm test -- --run
npm run build
npm run lint
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx frontend/src/pages/storage/tasks/components/SubtaskStepTimeline.tsx frontend/src/pages/storage/tasks/components/SubtaskLogList.tsx frontend/src/pages/storage/tasks/utils/format.ts frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts frontend/src/pages/content/movies/utils/sort.ts
git commit -m "refactor: split subtask detail and movie list pages"
```

---

### Task 9: Final Verification

**Files:**
- Modify only the owning phase files if verification exposes an integration failure.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: verified fullstack structure follow-up.

- [ ] **Step 1: Run backend full test suite**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run frontend lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 5: Run duplicate implementation reference checks**

Run:

```bash
rg -n "def _load_movies|def _create_subtask|def _classify_skip|def _resolve_target_locations|def _update_movie_storage_summary" backend/app/modules/storage/tasks/service.py
rg -n "def _execute_run|def _worker_loop|CrawlCallbacks\\(" backend/app/modules/crawler/runtime/service.py
rg -n "def " backend/app/modules/storage/worker/file_finder.py
rg -n "class MovieListFilters|def build_movie_list_statement|def movie_matches|def list_filter_values" backend/app/modules/content/movies/queries.py
```

Expected:

- first command: no output;
- second command: no output;
- third command: no output;
- fourth command: output only if `queries.py` re-exports via imports, not local definitions.

- [ ] **Step 6: Inspect final status**

Run:

```bash
git status --short
```

Expected: no unstaged tracked changes from this plan. Pre-existing untracked plan files may still appear and should not be staged unless the user explicitly asks.
