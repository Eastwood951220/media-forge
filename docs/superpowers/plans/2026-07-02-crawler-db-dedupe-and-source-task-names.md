# Crawler DB Dedupe And Source Task Names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make crawler list and detail phases skip movies that already exist in the database, persist skipped detail-task status, and append the current crawl task name to existing movies' `source_task_names`.

**Architecture:** The existing `JavdbSpider` already supports `db_check_callback`, `on_detail_check_callback`, and `on_item_already_exists`; this plan wires those callbacks from `backend/app/modules/crawler/runtime/service.py` into database-backed helpers. Existing movie checks stay in a small runtime helper module so the spider remains database-agnostic, while run detail rows record `skipped` with `already_exists` for both list-phase and detail-phase dedupe.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pytest, existing scraper service/spider callbacks.

---

## Context Notes

- Current `scraper/spiders/javdb/javdb_spider.py` already contains the needed dedupe hooks:
  - list phase calls `db_check_callback(codes)` and marks matched list tasks as `status="skipped"`, `reason="already_exists"`;
  - detail phase calls `on_detail_check_callback(code)` before fetching the detail page;
  - skipped existing tasks call `on_item_already_exists(task)`.
- Current `backend/app/modules/crawler/runtime/service.py` calls `MovieService.crawl_javdb_task(...)` but does not pass those database dedupe callbacks.
- The original `jav-scrapling` implementation updates `source_task_name` when an existing movie is encountered, and stores skipped detail tasks with `status="skipped"` and `error="already_exists"`.
- Keep this plan scoped to crawler DB dedupe and `source_task_names`. Do not add storage sync or unrelated crawler modes unless the user asks separately.

## File Structure

- Create `backend/app/modules/crawler/runtime/source_task_names.py`: focused DB helper functions for existing movie code lookup and appending `source_task_names`.
- Create `backend/tests/test_crawler_source_task_names.py`: unit tests for the helper module.
- Modify `backend/app/modules/crawler/runtime/service.py`: wire `db_check_callback`, `on_detail_check_callback`, and `on_item_already_exists`; persist skipped detail tasks and skipped counts.
- Modify `backend/tests/test_crawler_worker_service.py`: runtime tests for list-phase and detail-phase database dedupe.
- Create `scraper/tests/test_javdb_spider_dedupe_callbacks.py`: spider-level regression tests proving list and detail dedupe callbacks are honored without network fetches for skipped existing items.

---

### Task 1: Source Task Name DB Helpers

**Files:**
- Create: `backend/app/modules/crawler/runtime/source_task_names.py`
- Create: `backend/tests/test_crawler_source_task_names.py`

- [ ] **Step 1: Write the failing helper tests**

Create `backend/tests/test_crawler_source_task_names.py`:

```python
from sqlalchemy import select

from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_name_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie


def test_find_existing_movie_codes_returns_only_existing_codes() -> None:
    session = TestingSessionLocal()
    session.add(Movie(code="AAA-001", source_url="https://example.test/aaa", source_task_names=["旧任务"]))
    session.add(Movie(code="BBB-002", source_url="https://example.test/bbb", source_task_names=[]))
    session.commit()

    existing = find_existing_movie_codes(session, ["AAA-001", "AAA-001", "CCC-003", None, ""])

    assert existing == {"AAA-001"}
    assert movie_code_exists(session, "BBB-002") is True
    assert movie_code_exists(session, "CCC-003") is False
    assert movie_code_exists(session, None) is False


def test_add_source_task_name_for_code_appends_once() -> None:
    session = TestingSessionLocal()
    movie = Movie(code="AAA-010", source_url="https://example.test/aaa010", source_task_names=["旧任务"])
    session.add(movie)
    session.commit()

    assert add_source_task_name_for_code(session, "AAA-010", "新任务") is True
    assert add_source_task_name_for_code(session, "AAA-010", "新任务") is False
    assert add_source_task_name_for_code(session, "MISSING", "新任务") is False
    session.commit()

    refreshed = session.scalar(select(Movie).where(Movie.code == "AAA-010"))
    assert refreshed.source_task_names == ["旧任务", "新任务"]
```

- [ ] **Step 2: Run the helper tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_source_task_names.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.modules.crawler.runtime.source_task_names'`.

- [ ] **Step 3: Implement the helper module**

Create `backend/app/modules/crawler/runtime/source_task_names.py`:

```python
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie


def _clean_codes(codes: Iterable[str | None]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for code in codes:
        normalized = str(code or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return cleaned


def find_existing_movie_codes(db: Session, codes: Iterable[str | None]) -> set[str]:
    cleaned = _clean_codes(codes)
    if not cleaned:
        return set()
    rows = db.scalars(select(Movie.code).where(Movie.code.in_(cleaned))).all()
    return {code for code in rows if code}


def movie_code_exists(db: Session, code: str | None) -> bool:
    normalized = str(code or "").strip()
    if not normalized:
        return False
    return db.scalar(select(Movie.id).where(Movie.code == normalized)) is not None


def add_source_task_name_for_code(db: Session, code: str | None, task_name: str) -> bool:
    normalized = str(code or "").strip()
    if not normalized or not task_name:
        return False

    movie = db.scalar(select(Movie).where(Movie.code == normalized))
    if movie is None:
        return False

    current_names = list(movie.source_task_names or [])
    if task_name in current_names:
        return False

    movie.source_task_names = current_names + [task_name]
    db.flush()
    return True
```

- [ ] **Step 4: Run the helper tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_source_task_names.py -v
```

Expected: PASS, 2 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runtime/source_task_names.py backend/tests/test_crawler_source_task_names.py
git commit -m "feat: add crawler source task name helpers"
```

---

### Task 2: Runtime List-Phase DB Dedupe

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Write the failing list-phase runtime test**

Modify `backend/tests/test_crawler_worker_service.py`.

Add this stub class after `FailingPersistenceMovieServiceStub`:

```python
class ListPhaseDedupeMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        existing_codes = kwargs["db_check_callback"](["AAA-010", "AAA-011"])
        batch = [
            {"code": "AAA-010", "url": "https://javdb.com/v/aaa010", "name": "AAA 010"},
            {"code": "AAA-011", "url": "https://javdb.com/v/aaa011", "name": "AAA 011"},
        ]
        for item in batch:
            if item["code"] in existing_codes:
                item["status"] = "skipped"
                item["reason"] = "already_exists"
        kwargs["on_tasks_batch_created"](batch)
        return {
            "total_tasks": 2,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 1,
        }
```

Add this test at the end of the file:

```python
def test_execute_run_marks_list_phase_existing_movies_skipped(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: ListPhaseDedupeMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("list-dedupe")
    session.add(Movie(code="AAA-010", source_url="https://javdb.com/v/aaa010", source_task_names=["旧任务"]))
    session.commit()

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    skipped = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-010").one()
    pending = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-011").one()
    movie = session.scalar(select(Movie).where(Movie.code == "AAA-010"))

    assert skipped.status == "skipped"
    assert skipped.error == "already_exists"
    assert skipped.saved_at is None
    assert pending.status == "pending_crawl"
    assert movie.source_task_names == ["旧任务", run.task_name]
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["skipped_tasks"] == 1
```

- [ ] **Step 2: Run the list-phase test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_marks_list_phase_existing_movies_skipped -v
```

Expected: FAIL with `KeyError: 'db_check_callback'`, or FAIL because the existing detail task is still `pending_crawl`.

- [ ] **Step 3: Import helper functions into runtime service**

Modify `backend/app/modules/crawler/runtime/service.py` imports:

```python
from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_name_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
```

- [ ] **Step 4: Update `on_tasks_batch_created` to persist skipped rows**

In `backend/app/modules/crawler/runtime/service.py`, replace the body of `on_tasks_batch_created` inside `_execute_run` with:

```python
    def on_tasks_batch_created(items: list[dict[str, Any]]) -> None:
        skipped_count = 0
        for item in items:
            is_skipped = item.get("status") == "skipped"
            reason = item.get("reason") if is_skipped else None
            detail = CrawlRunDetailTask(
                run_id=run.id,
                task_name=task.name,
                code=item.get("code"),
                source_url=item.get("url", ""),
                source_name=item.get("name", ""),
                status="skipped" if is_skipped else "pending_crawl",
                error=reason,
                created_at=datetime.now(),
            )
            db.add(detail)
            db.flush()
            remember_detail(detail)
            if is_skipped:
                skipped_count += 1
                if add_source_task_name_for_code(db, item.get("code"), task.name):
                    _append_run_log(str(run.id), f"已存在影片追加任务名: {item.get('code')} -> {task.name}", "INFO", code=item.get("code"))
        progress["total"] += len(items)
        progress["skipped"] += skipped_count
        runtime.write_progress(str(run.id), progress)
        db.commit()
        if items:
            _append_run_log(str(run.id), f"创建子任务 {len(items)} 条，跳过 {skipped_count} 条")
```

- [ ] **Step 5: Add database callbacks and pass them into `crawl_javdb_task`**

Inside `_execute_run`, add these functions after `log_callback`:

```python
    def db_check_callback(codes: list[str]) -> set[str]:
        existing_codes = find_existing_movie_codes(db, codes)
        if existing_codes:
            _append_run_log(str(run.id), f"列表阶段发现已存在影片 {len(existing_codes)} 条", "INFO")
        return existing_codes

    def on_detail_check_callback(code: str) -> bool:
        exists = movie_code_exists(db, code)
        if exists:
            _append_run_log(str(run.id), f"详情阶段跳过已存在影片: {code}", "INFO", code=code)
        return exists
```

In the `movie_service.crawl_javdb_task(...)` call, add these keyword arguments:

```python
            db_check_callback=db_check_callback,
            on_detail_check_callback=on_detail_check_callback,
```

- [ ] **Step 6: Include skipped count in final run result**

In `_execute_run`, after `crawl_failed_count = _count_run_detail_tasks(db, run.id, "crawl_failed")`, add:

```python
        skipped_count = _count_run_detail_tasks(db, run.id, "skipped")
```

In `run.result = { ... }`, add:

```python
            "skipped_tasks": skipped_count,
```

In the completion log message, replace:

```python
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}",
```

with:

```python
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
```

- [ ] **Step 7: Run the list-phase test and verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_marks_list_phase_existing_movies_skipped -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: skip existing movies during crawler list phase"
```

---

### Task 3: Runtime Detail-Phase DB Dedupe

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Write the failing detail-phase runtime test**

Modify `backend/tests/test_crawler_worker_service.py`.

Add this stub class after `ListPhaseDedupeMovieServiceStub`:

```python
class DetailPhaseDedupeMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        detail_task = {"code": "AAA-020", "url": "https://javdb.com/v/aaa020", "name": "AAA 020"}
        kwargs["on_tasks_batch_created"]([detail_task])
        if kwargs["on_detail_check_callback"]("AAA-020"):
            detail_task["status"] = "skipped"
            detail_task["reason"] = "already_exists"
            kwargs["on_item_already_exists"](detail_task)
        return {
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 1,
        }
```

Add this test at the end of the file:

```python
def test_execute_run_marks_detail_phase_existing_movies_skipped(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: DetailPhaseDedupeMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("detail-dedupe")
    session.add(Movie(code="AAA-020", source_url="https://javdb.com/v/aaa020", source_task_names=["旧任务"]))
    session.commit()

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-020").one()
    movie = session.scalar(select(Movie).where(Movie.code == "AAA-020"))

    assert detail.status == "skipped"
    assert detail.error == "already_exists"
    assert detail.crawled_at is not None
    assert detail.saved_at is None
    assert movie.source_task_names == ["旧任务", run.task_name]
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["skipped_tasks"] == 1
```

- [ ] **Step 2: Run the detail-phase test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_marks_detail_phase_existing_movies_skipped -v
```

Expected: FAIL with `KeyError: 'on_item_already_exists'`, or FAIL because the detail row remains `pending_crawl`.

- [ ] **Step 3: Add skipped-detail helper inside `_execute_run`**

In `backend/app/modules/crawler/runtime/service.py`, inside `_execute_run`, add this function after `on_detail_failed`:

```python
    def on_item_already_exists(task_info: dict[str, Any]) -> None:
        detail = find_detail(task_info)
        code = task_info.get("code")
        if detail:
            detail.status = "skipped"
            detail.error = "already_exists"
            detail.crawled_at = datetime.now()
            detail.saved_at = None
        add_source_task_name_for_code(db, code, task.name)
        progress["skipped"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()
        _append_run_log(str(run.id), f"跳过已存在影片并追加任务名: {code}", "INFO", code=code)
```

- [ ] **Step 4: Pass `on_item_already_exists` into `crawl_javdb_task`**

In the `movie_service.crawl_javdb_task(...)` call in `backend/app/modules/crawler/runtime/service.py`, add:

```python
            on_item_already_exists=on_item_already_exists,
```

- [ ] **Step 5: Avoid double-counting skipped rows already marked during list phase**

Update `on_item_already_exists` to only increment `progress["skipped"]` when the detail was not already skipped:

```python
    def on_item_already_exists(task_info: dict[str, Any]) -> None:
        detail = find_detail(task_info)
        code = task_info.get("code")
        was_skipped = detail is not None and detail.status == "skipped"
        if detail:
            detail.status = "skipped"
            detail.error = "already_exists"
            detail.crawled_at = detail.crawled_at or datetime.now()
            detail.saved_at = None
        add_source_task_name_for_code(db, code, task.name)
        if not was_skipped:
            progress["skipped"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()
        _append_run_log(str(run.id), f"跳过已存在影片并追加任务名: {code}", "INFO", code=code)
```

- [ ] **Step 6: Run the detail-phase test and verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_marks_detail_phase_existing_movies_skipped -v
```

Expected: PASS.

- [ ] **Step 7: Run the worker service tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS for all tests in `test_crawler_worker_service.py`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: skip existing movies during crawler detail phase"
```

---

### Task 4: Spider Dedupe Callback Contract Tests

**Files:**
- Create: `scraper/tests/test_javdb_spider_dedupe_callbacks.py`

- [ ] **Step 1: Write spider callback contract tests**

Create `scraper/tests/test_javdb_spider_dedupe_callbacks.py`:

```python
import pytest

from scraper.spiders.javdb import javdb_spider as spider_module
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTaskUrlEntry


class Fetcher:
    def fetch(self, url: str):
        return "<html></html>"


def test_list_phase_marks_existing_codes_skipped(monkeypatch) -> None:
    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "MAX_LIST_PAGES", 1)
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)
    monkeypatch.setattr(
        spider_module,
        "parse_search_page",
        lambda page, source_page: [
            {"code": "AAA-030", "url": "https://javdb.com/v/aaa030", "name": "AAA 030"},
            {"code": "AAA-031", "url": "https://javdb.com/v/aaa031", "name": "AAA 031"},
        ],
    )

    created_batches = []
    result = spider.collect_detail_tasks_for_url(
        url_entry=CrawlTaskUrlEntry(url="https://javdb.com/actors/a", url_type="actors"),
        task_name="任务",
        db_check_callback=lambda codes: {"AAA-030"},
        on_tasks_batch_created=created_batches.append,
    )

    assert result[0]["status"] == "skipped"
    assert result[0]["reason"] == "already_exists"
    assert "status" not in result[1]
    assert created_batches[0][0]["code"] == "AAA-030"


def test_detail_phase_skips_existing_code_without_fetching(monkeypatch) -> None:
    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)

    def fail_fetch(url: str):
        raise AssertionError("fetch should not be called for existing code")

    monkeypatch.setattr(spider, "fetch", fail_fetch)
    already_exists = []

    result = spider.run_detail_tasks(
        [{"code": "AAA-040", "url": "https://javdb.com/v/aaa040", "name": "AAA 040"}],
        task_name="任务",
        on_detail_check_callback=lambda code: code == "AAA-040",
        on_item_already_exists=already_exists.append,
    )

    assert result[0]["status"] == "skipped"
    assert result[0]["reason"] == "already_exists"
    assert already_exists[0]["code"] == "AAA-040"
```

- [ ] **Step 2: Run the spider tests**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
```

Expected: PASS. If the first test fails because `scraper/tests` does not exist, create the directory and rerun the command:

```bash
mkdir -p scraper/tests
source .venv/bin/activate
python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
```

- [ ] **Step 3: Commit**

```bash
git add scraper/tests/test_javdb_spider_dedupe_callbacks.py
git commit -m "test: cover javdb spider db dedupe callbacks"
```

---

### Task 5: Full Backend Verification

**Files:**
- No planned code changes.

- [ ] **Step 1: Run focused crawler verification**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_source_task_names.py backend/tests/test_crawler_worker_service.py scraper/tests/test_javdb_spider_dedupe_callbacks.py -v
```

Expected: PASS.

- [ ] **Step 2: Run crawler API regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 3: Manual runtime check**

Run backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Expected manual behavior:

- Start a crawler run for a task whose list pages include a code already present in `movies.code`.
- The run detail task for that code is `skipped` with `error="already_exists"`.
- The existing movie row now includes the crawler task name in `movies.source_task_names`.
- If a movie is inserted after list collection but before detail fetch, the detail phase skips it before fetching the page and also appends the task name.
- `run.result["skipped_tasks"]` reflects skipped detail-task rows.

---

## Self-Review

- Spec coverage:
  - Task 2 covers list-phase DB comparison, skipped detail status, and `source_task_names` update.
  - Task 3 covers detail-phase DB comparison before fetch, skipped detail status, and `source_task_names` update.
  - Task 4 protects the existing spider callback behavior from regressing.
  - The plan reuses the original `jav-scrapling` callback design without adding unrelated storage-sync behavior.
- Placeholder scan:
  - No forbidden placeholder terms are present.
  - Every code-changing step contains exact code to add or replace.
- Type consistency:
  - Helper functions accept SQLAlchemy `Session` and are called from `runtime/service.py` with the current worker session.
  - Detail-task skipped status uses existing `status="skipped"` and `error="already_exists"` consistently.
  - Runtime result uses the existing `skipped_tasks` key already produced by `scraper/services/movie_result.py`.
