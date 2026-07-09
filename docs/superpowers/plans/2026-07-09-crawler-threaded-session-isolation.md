# Crawler Threaded Session Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent threaded crawler list-phase worker callbacks from reusing the main SQLAlchemy `Session`, so list collection can finish and the detail phase can start.

**Architecture:** Keep the existing threaded crawler flow. Add isolated short-lived sessions for worker-thread database callbacks while keeping main-thread detail task persistence on the existing run session. Prove the boundary with a regression test that fails if the main session is passed into list worker DB callbacks.

**Tech Stack:** Python 3.12+, FastAPI backend, SQLAlchemy ORM sessions, pytest, existing crawler threaded runtime.

## Global Constraints

- Keep scope anchored to refactor and optimization of existing `jav-scrapling` behavior.
- Do not redesign the crawler engine.
- Do not merge threaded and callback-based runtimes.
- Do not move list-phase dedupe semantics out of the scraper.
- Do not change incremental/full mode behavior.
- Do not add new UI behavior.
- Worker-thread DB callbacks must not reuse the main crawler SQLAlchemy `Session`.
- Use `.venv/` at project root for backend test commands.

---

## File Structure

- Modify `backend/app/modules/crawler/runtime/threaded.py`: add isolated session helpers and route list-phase worker callbacks through them.
- Modify `backend/tests/test_crawler_threaded_runtime.py`: add a regression test covering DB callback session isolation and detail-phase continuation.

No new runtime module is needed. The helper functions are local to `threaded.py` because this fix is specific to the threaded crawler runtime and should not change the callback-based runtime.

---

### Task 1: Regression Test for List Worker Session Isolation

**Files:**
- Modify: `backend/tests/test_crawler_threaded_runtime.py`

**Interfaces:**
- Consumes: `execute_threaded_crawl(db: Session, run: CrawlRun, task: CrawlTask, runtime: Any, *, detail_only: bool = False) -> dict[str, Any]`
- Produces: A failing test named `test_list_phase_db_callbacks_use_isolated_sessions`

- [ ] **Step 1: Write the failing test**

Add these imports near the top of `backend/tests/test_crawler_threaded_runtime.py`:

```python
import threading

from shared.database.models.content import Movie
```

Add this test after `test_execute_threaded_crawl_finishes_list_before_detail`:

```python
def test_list_phase_db_callbacks_use_isolated_sessions(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    db_session.add(Movie(code="A-001", title="Existing A"))
    db_session.commit()

    main_thread_id = threading.get_ident()
    original_scalars = db_session.scalars

    def scalars_guard(*args, **kwargs):
        if threading.get_ident() != main_thread_id:
            raise AssertionError("main crawler session was used from a list worker thread")
        return original_scalars(*args, **kwargs)

    db_session.scalars = scalars_guard

    class DedupeSpider(FakeSpider):
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
            existing_codes = db_check_callback([f"{url_entry.url_type}-001"])
            if f"{url_entry.url_type}-001" in existing_codes:
                on_item_already_exists(
                    {
                        "code": f"{url_entry.url_type}-001",
                        "url": f"https://javdb.com/v/{url_entry.url_type.lower()}001",
                        "name": url_entry.url_type,
                    }
                )
                return []
            return [
                {
                    "code": f"{url_entry.url_type}-001",
                    "url": f"https://javdb.com/v/{url_entry.url_type.lower()}001",
                    "name": url_entry.url_type,
                }
            ]

    spider = DedupeSpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime())

    assert result["total_tasks"] == 1
    assert result["saved"] == 1
    assert spider.detail_started is True
    rows = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    assert [row.code for row in rows] == ["B-001"]
    assert rows[0].status == "saved"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py::test_list_phase_db_callbacks_use_isolated_sessions -q
```

Expected: FAIL with `AssertionError: main crawler session was used from a list worker thread`.

- [ ] **Step 3: Commit the failing test only if using a review checkpoint**

Do not commit by default. This task is complete when the test fails for the expected reason.

---

### Task 2: Isolate Threaded List-Phase DB Callbacks

**Files:**
- Modify: `backend/app/modules/crawler/runtime/threaded.py`
- Test: `backend/tests/test_crawler_threaded_runtime.py`

**Interfaces:**
- Consumes: `find_existing_movie_codes(db: Session, codes: Iterable[str | None]) -> set[str]`
- Consumes: `append_source_task_id(db: Session, code: str | None, task_id: uuid.UUID) -> bool`
- Produces: `_find_existing_movie_codes_in_worker_session(session_factory: sessionmaker, codes: list[str | None]) -> set[str]`
- Produces: `_handle_already_exists_in_worker_session(session_factory: sessionmaker, run: CrawlRun, task: CrawlTask, task_info: dict) -> None`

- [ ] **Step 1: Add isolated session helpers**

In `backend/app/modules/crawler/runtime/threaded.py`, add this import after the existing SQLAlchemy import:

```python
from sqlalchemy.orm import Session, sessionmaker
```

Replace the existing `from sqlalchemy.orm import Session` import with the combined import above.

Add these helper functions after `build_pipeline`:

```python
def _worker_session_factory(db: Session) -> sessionmaker:
    return sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)


def _find_existing_movie_codes_in_worker_session(
    session_factory: sessionmaker,
    codes: list[str | None],
) -> set[str]:
    worker_db = session_factory()
    try:
        return find_existing_movie_codes(worker_db, codes)
    finally:
        worker_db.close()


def _handle_already_exists_in_worker_session(
    session_factory: sessionmaker,
    run: CrawlRun,
    task: CrawlTask,
    task_info: dict,
) -> None:
    worker_db = session_factory()
    try:
        worker_run = worker_db.merge(run, load=False)
        worker_task = worker_db.merge(task, load=False)
        _handle_already_exists(worker_db, worker_run, worker_task, task_info)
        worker_db.commit()
    except Exception:
        worker_db.rollback()
        raise
    finally:
        worker_db.close()
```

- [ ] **Step 2: Route worker callbacks through isolated helpers**

In `_run_list_phase`, add a session factory before `_collect_url` is defined:

```python
worker_session_factory = _worker_session_factory(db)
```

Then replace the two callback lambdas:

```python
db_check_callback=lambda codes: find_existing_movie_codes(db, codes),
on_item_already_exists=lambda task_info: _handle_already_exists(db, run, task, task_info),
```

with:

```python
db_check_callback=lambda codes: _find_existing_movie_codes_in_worker_session(worker_session_factory, codes),
on_item_already_exists=lambda task_info: _handle_already_exists_in_worker_session(
    worker_session_factory,
    run,
    task,
    task_info,
),
```

- [ ] **Step 3: Run the regression test to verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py::test_list_phase_db_callbacks_use_isolated_sessions -q
```

Expected: PASS.

- [ ] **Step 4: Run the threaded runtime test file**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit the implementation**

Run:

```bash
git add backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_threaded_runtime.py
git commit -m "fix: isolate threaded crawler list sessions"
```

---

### Task 3: Verify Crawler Runtime Regression Set

**Files:**
- Verify: `backend/app/modules/crawler/runtime/threaded.py`
- Verify: `backend/app/modules/crawler/runtime/finalize.py`
- Verify: `backend/tests/test_crawler_threaded_runtime.py`
- Verify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes: implementation from Task 2.
- Produces: verified crawler runtime behavior.

- [ ] **Step 1: Run the focused crawler runtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py backend/tests/test_crawler_worker_service.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the broader crawler API/runtime set**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_threaded_runtime.py backend/tests/test_crawler_detail_queue.py backend/tests/test_crawler_worker_service.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Inspect the diff**

Run:

```bash
git diff -- backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_threaded_runtime.py
```

Expected: the diff only contains the isolated worker session helpers, callback rewiring, and the regression test.

- [ ] **Step 4: Report verification**

Report the exact pytest commands and pass counts. Also mention any unrelated dirty working tree files that were not touched by this implementation.
