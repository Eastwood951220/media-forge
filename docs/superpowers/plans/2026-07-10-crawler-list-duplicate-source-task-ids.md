# Crawler List Duplicate Source Task IDs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure crawler list-stage duplicate movies append the current crawler task ID to `movies.source_task_ids` for both incremental and full crawls.

**Architecture:** Add one persistence helper that appends a task ID to every existing movie code returned by list-stage duplicate checks, preserving the existing single-code helper for detail-stage skips. Wire that helper into both callback runtimes: the normal `build_crawl_callbacks().db_check_callback` path and the threaded list worker session path. Keep duplicate detection behavior unchanged: existing movies still do not create detail subtasks, and detail-stage already-exists handling still appends the task ID idempotently.

**Tech Stack:** Python 3.12+, SQLAlchemy ORM sessions, FastAPI backend test fixtures, pytest.

## Global Constraints

- Incremental crawl list-stage duplicates must append the current `CrawlTask.id` to existing `Movie.source_task_ids`.
- Full crawl list-stage duplicates must append the current `CrawlTask.id` to existing `Movie.source_task_ids`.
- Duplicate task IDs must not be appended twice to the same movie.
- Movies that do not exist must not be created by the list-stage duplicate helper.
- Existing detail-stage `on_item_already_exists` behavior must remain idempotent.
- Existing list-stage duplicate behavior must still exclude duplicate movies from detail subtasks.
- Threaded list workers must continue using isolated worker sessions rather than the main crawler session.

---

## File Structure

- Modify `backend/app/modules/content/movies/movie_persistence.py`: add a bulk source-task append helper for list-stage duplicate codes.
- Modify `backend/app/modules/content/movies/persistence.py`: export the new helper through the existing facade.
- Modify `backend/app/modules/crawler/runtime/callbacks.py`: make `db_check_callback` append the current task ID for existing movie codes.
- Modify `backend/app/modules/crawler/runtime/threaded.py`: make threaded list worker `db_check_callback` append the current task ID inside its worker session.
- Modify `backend/tests/test_movie_persistence.py`: cover the bulk helper and facade export.
- Modify `backend/tests/test_crawler_worker_service.py`: cover normal callback list-stage duplicates for incremental and full modes.
- Modify `backend/tests/test_crawler_threaded_runtime.py`: cover threaded list-stage duplicates for incremental and full modes without requiring `on_item_already_exists`.

### Task 1: Bulk Source Task ID Persistence Helper

**Files:**
- Modify: `backend/app/modules/content/movies/movie_persistence.py`
- Modify: `backend/app/modules/content/movies/persistence.py`
- Test: `backend/tests/test_movie_persistence.py`

**Interfaces:**
- Consumes: `append_source_task_id(session: Session, code: str | None, task_id: UUID) -> bool`
- Produces: `append_source_task_ids_for_codes(session: Session, codes: Iterable[str | None], task_id: UUID) -> set[str]`

- [ ] **Step 1: Write the failing bulk helper test**

Append this test to `backend/tests/test_movie_persistence.py`:

```python
def test_append_source_task_ids_for_codes_adds_unique_ids_to_existing_movies() -> None:
    session = TestingSessionLocal()
    task_id = uuid.uuid4()
    existing_task_id = uuid.uuid4()
    first_id = upsert_movie(session, {"code": "BULK-001", "source_url": "https://javdb.com/v/bulk001"})
    second_id = upsert_movie(session, {
        "code": "BULK-002",
        "source_url": "https://javdb.com/v/bulk002",
        "source_task_ids": [existing_task_id],
    })
    session.commit()

    changed = append_source_task_ids_for_codes(
        session,
        ["BULK-001", "BULK-002", "BULK-001", "MISSING-001", None, ""],
        task_id,
    )
    session.commit()

    first = session.get(Movie, first_id)
    second = session.get(Movie, second_id)

    assert changed == {"BULK-001", "BULK-002"}
    assert [str(value) for value in first.source_task_ids] == [str(task_id)]
    assert [str(value) for value in second.source_task_ids] == [str(existing_task_id), str(task_id)]

    changed_again = append_source_task_ids_for_codes(session, ["BULK-001", "BULK-002"], task_id)
    session.commit()

    assert changed_again == set()
    assert [str(value) for value in first.source_task_ids] == [str(task_id)]
    assert [str(value) for value in second.source_task_ids] == [str(existing_task_id), str(task_id)]

    session.close()
```

Update the import block in `backend/tests/test_movie_persistence.py`:

```python
from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    append_source_task_ids_for_codes,
    compute_magnet_weight,
    extract_info_hash,
    sync_movie_filters,
    upsert_magnets,
    upsert_movie,
    upsert_movie_with_magnets,
)
```

Update `test_movie_persistence_facade_exports_existing_public_functions`:

```python
def test_movie_persistence_facade_exports_existing_public_functions() -> None:
    from backend.app.modules.content.movies import persistence
    from backend.app.modules.content.movies import magnet_identity, magnet_persistence, magnet_scoring, movie_persistence, filter_sync

    assert persistence.extract_info_hash is magnet_identity.extract_info_hash
    assert persistence.compute_magnet_weight is magnet_scoring.compute_magnet_weight
    assert persistence.upsert_magnets is magnet_persistence.upsert_magnets
    assert persistence.upsert_movie is movie_persistence.upsert_movie
    assert persistence.append_source_task_id is movie_persistence.append_source_task_id
    assert persistence.append_source_task_ids_for_codes is movie_persistence.append_source_task_ids_for_codes
    assert persistence.sync_movie_filters is filter_sync.sync_movie_filters
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_movie_persistence.py::test_append_source_task_ids_for_codes_adds_unique_ids_to_existing_movies backend/tests/test_movie_persistence.py::test_movie_persistence_facade_exports_existing_public_functions -v
```

Expected: FAIL with `ImportError` or `AttributeError` for `append_source_task_ids_for_codes`.

- [ ] **Step 3: Implement the helper**

Modify `backend/app/modules/content/movies/movie_persistence.py`:

```python
from collections.abc import Iterable
```

Add this helper below `append_source_task_id`:

```python
def append_source_task_ids_for_codes(session: Session, codes: Iterable[str | None], task_id: UUID) -> set[str]:
    cleaned_codes: list[str] = []
    seen_codes: set[str] = set()
    for code in codes:
        normalized = str(code or "").strip()
        if normalized and normalized not in seen_codes:
            seen_codes.add(normalized)
            cleaned_codes.append(normalized)
    if not cleaned_codes:
        return set()

    movies = session.scalars(select(Movie).where(Movie.code.in_(cleaned_codes))).all()
    task_id_text = str(task_id)
    changed_codes: set[str] = set()

    for movie in movies:
        existing_ids = [str(value) for value in (movie.source_task_ids or [])]
        if task_id_text in existing_ids:
            continue
        movie.source_task_ids = list(movie.source_task_ids or []) + [task_id]
        if movie.code:
            changed_codes.add(movie.code)

    if changed_codes:
        session.flush()
    return changed_codes
```

Modify `backend/app/modules/content/movies/persistence.py`:

```python
from backend.app.modules.content.movies.movie_persistence import append_source_task_id, append_source_task_ids_for_codes, upsert_movie
```

Update `__all__` in the same file:

```python
__all__ = [
    "append_source_task_id",
    "append_source_task_ids_for_codes",
    "auto_select_best_magnet",
    "build_magnet_dedupe_key",
    "compute_magnet_weight",
    "extract_info_hash",
    "has_chinese_sub",
    "normalize_magnet",
    "parse_size_mb",
    "sync_movie_filters",
    "upsert_magnets",
    "upsert_movie",
    "upsert_movie_with_magnets",
]
```

- [ ] **Step 4: Run the helper tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_movie_persistence.py::test_append_source_task_ids_for_codes_adds_unique_ids_to_existing_movies backend/tests/test_movie_persistence.py::test_movie_persistence_facade_exports_existing_public_functions -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/content/movies/movie_persistence.py backend/app/modules/content/movies/persistence.py backend/tests/test_movie_persistence.py
git commit -m "fix: add bulk source task id append helper"
```

### Task 2: Normal Callback List-Stage Duplicate Handling

**Files:**
- Modify: `backend/app/modules/crawler/runtime/callbacks.py`
- Test: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes: `append_source_task_ids_for_codes(session: Session, codes: Iterable[str | None], task_id: UUID) -> set[str]`
- Produces: `db_check_callback(codes: list[str]) -> set[str]` that also appends `ctx.task.id` to existing movie codes.

- [ ] **Step 1: Write failing callback tests for incremental and full modes**

Add this test to `backend/tests/test_crawler_worker_service.py` near the existing callback tests:

```python
def test_db_check_callback_appends_source_task_ids_for_list_duplicates_in_incremental_and_full_modes(db_session, admin_user) -> None:
    from backend.app.modules.crawler.runtime.callbacks import CrawlerCallbackContext, build_crawl_callbacks
    from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
    from backend.app.modules.crawler.runtime.progress import new_progress

    class Runtime:
        def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
            return None

        def is_stop_requested(self, run_id: str) -> bool:
            return False

    for crawl_mode in ("incremental", "full"):
        task = CrawlTask(name=f"任务-list-duplicate-{crawl_mode}", owner_id=admin_user.id, is_skip=False)
        db_session.add(task)
        db_session.flush()
        run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode=crawl_mode, queued_at=datetime.now())
        db_session.add(run)
        db_session.add(Movie(code=f"LIST-DUP-{crawl_mode.upper()}", source_url=f"https://javdb.com/v/list-dup-{crawl_mode}", source_task_ids=[]))
        db_session.commit()

        callbacks = build_crawl_callbacks(CrawlerCallbackContext(
            db=db_session,
            run=run,
            task=task,
            runtime=Runtime(),
            detail_index=DetailTaskIndex(),
            progress=new_progress(),
        ))

        existing_codes = callbacks.db_check_callback([f"LIST-DUP-{crawl_mode.upper()}", "LIST-MISSING"])
        db_session.commit()

        movie = db_session.scalar(select(Movie).where(Movie.code == f"LIST-DUP-{crawl_mode.upper()}"))

        assert existing_codes == {f"LIST-DUP-{crawl_mode.upper()}"}
        assert str(task.id) in [str(value) for value in movie.source_task_ids]
        assert db_session.scalar(select(Movie).where(Movie.code == "LIST-MISSING")) is None
```

- [ ] **Step 2: Run the callback test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_db_check_callback_appends_source_task_ids_for_list_duplicates_in_incremental_and_full_modes -v
```

Expected: FAIL because `movie.source_task_ids` does not contain the current `task.id`.

- [ ] **Step 3: Append task IDs inside `db_check_callback`**

Modify the import in `backend/app/modules/crawler/runtime/callbacks.py`:

```python
from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    append_source_task_ids_for_codes,
    upsert_movie_with_magnets,
)
```

Replace `db_check_callback` in the same file:

```python
    def db_check_callback(codes: list[str]) -> set[str]:
        existing_codes = find_existing_movie_codes(ctx.db, codes)
        if existing_codes:
            changed_codes = append_source_task_ids_for_codes(ctx.db, existing_codes, ctx.task.id)
            append_run_log_for_run(ctx.db, ctx.run, f"列表阶段发现已存在影片 {len(existing_codes)} 条", "INFO")
            if changed_codes:
                append_run_log_for_run(ctx.db, ctx.run, f"列表阶段已存在影片追加任务ID {len(changed_codes)} 条", "INFO")
        return existing_codes
```

- [ ] **Step 4: Run callback tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_db_check_callback_appends_source_task_ids_for_list_duplicates_in_incremental_and_full_modes backend/tests/test_crawler_worker_service.py::test_on_tasks_batch_created_recreates_deleted_indexed_detail -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runtime/callbacks.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: append source task ids during crawler list dedupe"
```

### Task 3: Threaded Runtime List Worker Duplicate Handling

**Files:**
- Modify: `backend/app/modules/crawler/runtime/threaded.py`
- Test: `backend/tests/test_crawler_threaded_runtime.py`

**Interfaces:**
- Consumes: `append_source_task_ids_for_codes(session: Session, codes: Iterable[str | None], task_id: UUID) -> set[str]`
- Produces: threaded list `db_check_callback` that returns existing codes and appends `task_id` in the worker session.

- [ ] **Step 1: Write failing threaded list tests for incremental and full modes**

Update the import block in `backend/tests/test_crawler_threaded_runtime.py`:

```python
import pytest
```

Add this test below `test_list_phase_db_callbacks_use_isolated_sessions`:

```python
@pytest.mark.parametrize("crawl_mode", ["incremental", "full"])
def test_threaded_list_db_check_appends_source_task_id_without_already_exists_callback(db_session, monkeypatch, crawl_mode) -> None:
    task, run = make_task_and_run(db_session)
    run.crawl_mode = crawl_mode
    existing_code = f"A-{run.id.hex[:8]}"
    db_session.add(Movie(code=existing_code, source_name="Existing A", source_task_ids=[]))
    db_session.commit()

    class DbCheckOnlySpider(FakeSpider):
        def collect_detail_tasks_for_url(
            self,
            *,
            url_entry,
            task_name,
            crawl_mode,
            incremental_threshold,
            stop_check,
            log_callback,
            db_check_callback,
            on_item_already_exists,
        ):
            self.list_started = True
            if url_entry.url_type == "A":
                assert existing_code in db_check_callback([existing_code])
                return []
            return [
                {
                    "code": f"B-{run.id.hex[:8]}",
                    "url": f"https://javdb.com/v/b{run.id.hex[:8]}",
                    "name": "B",
                }
            ]

    spider = DbCheckOnlySpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime())
    movie = db_session.scalar(select(Movie).where(Movie.code == existing_code))

    assert result["total_tasks"] == 1
    assert result["saved"] == 1
    assert str(task.id) in [str(value) for value in movie.source_task_ids]
```

Also update the existing imports in `backend/tests/test_crawler_threaded_runtime.py`:

```python
from sqlalchemy import select
```

- [ ] **Step 2: Run the threaded test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py::test_threaded_list_db_check_appends_source_task_id_without_already_exists_callback -v
```

Expected: FAIL because the threaded `db_check_callback` finds the existing code but does not append `task.id`.

- [ ] **Step 3: Implement threaded worker session append**

Modify imports in `backend/app/modules/crawler/runtime/threaded.py`:

```python
from backend.app.modules.content.movies.persistence import append_source_task_id, append_source_task_ids_for_codes, upsert_movie_with_magnets
```

Replace `_find_existing_movie_codes_in_worker_session` with this function:

```python
def _find_existing_movie_codes_in_worker_session(
    session_factory: sessionmaker,
    codes: list[str | None],
    task_id: Any,
    db_lock: threading.Lock,
) -> set[str]:
    with db_lock:
        worker_db = session_factory()
        try:
            existing_codes = find_existing_movie_codes(worker_db, codes)
            if existing_codes:
                append_source_task_ids_for_codes(worker_db, existing_codes, task_id)
                worker_db.commit()
            return existing_codes
        except Exception:
            worker_db.rollback()
            raise
        finally:
            worker_db.close()
```

Update the `db_check_callback` lambda in `_run_list_phase`:

```python
            db_check_callback=lambda codes: _find_existing_movie_codes_in_worker_session(
                worker_session_factory,
                codes,
                task_id,
                list_db_lock,
            ),
```

- [ ] **Step 4: Run threaded tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py::test_threaded_list_db_check_appends_source_task_id_without_already_exists_callback backend/tests/test_crawler_threaded_runtime.py::test_list_phase_db_callbacks_use_isolated_sessions backend/tests/test_crawler_threaded_runtime.py::test_list_phase_snapshots_worker_inputs_before_main_commit -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_threaded_runtime.py
git commit -m "fix: append threaded crawler list duplicate task ids"
```

### Task 4: Regression Test Sweep

**Files:**
- Verify: `backend/tests/test_movie_persistence.py`
- Verify: `backend/tests/test_crawler_worker_service.py`
- Verify: `backend/tests/test_crawler_threaded_runtime.py`
- Verify: `backend/tests/test_crawler_source_task_names.py`

**Interfaces:**
- Consumes: all interfaces from Tasks 1-3.
- Produces: verified crawler duplicate handling for list-stage and detail-stage paths.

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_movie_persistence.py \
  backend/tests/test_crawler_worker_service.py::test_execute_run_excludes_list_phase_existing_movies_from_detail_tasks \
  backend/tests/test_crawler_worker_service.py::test_execute_run_marks_detail_phase_existing_movies_skipped \
  backend/tests/test_crawler_worker_service.py::test_db_check_callback_appends_source_task_ids_for_list_duplicates_in_incremental_and_full_modes \
  backend/tests/test_crawler_threaded_runtime.py \
  backend/tests/test_crawler_source_task_names.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Inspect git diff for accidental scope creep**

Run:

```bash
git diff --stat
git diff -- backend/app/modules/content/movies/movie_persistence.py backend/app/modules/content/movies/persistence.py backend/app/modules/crawler/runtime/callbacks.py backend/app/modules/crawler/runtime/threaded.py backend/tests/test_movie_persistence.py backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_threaded_runtime.py
```

Expected: only the helper, callback wiring, threaded wiring, and tests changed.

- [ ] **Step 3: Commit the verification note if code changed during regression**

If Step 1 required any code or test edits, commit those exact files:

```bash
git add backend/app/modules/content/movies/movie_persistence.py backend/app/modules/content/movies/persistence.py backend/app/modules/crawler/runtime/callbacks.py backend/app/modules/crawler/runtime/threaded.py backend/tests/test_movie_persistence.py backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_threaded_runtime.py
git commit -m "test: cover crawler duplicate source task id regressions"
```

If Step 1 passed without edits, do not create an empty commit.
