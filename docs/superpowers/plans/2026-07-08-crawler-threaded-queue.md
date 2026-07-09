# Crawler Threaded Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build configurable multi-threaded crawler execution with URL-level list workers and persistent pending-detail workers.

**Architecture:** Keep the existing `execute_run -> engine -> spider` entry shape, but move run execution to a small coordinator that runs a list worker pool first and a detail worker pool second. Persist detail tasks into `crawl_run_detail_tasks`; detail workers claim `pending_crawl` rows with their own SQLAlchemy sessions and update rows through `crawling`, `saved`, `crawl_failed`, or `save_failed`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, pytest, React 19, TypeScript, Ant Design, Vitest.

## Global Constraints

- Use separate config fields for list and detail concurrency: `LIST_MAX_WORKERS` and `DETAIL_MAX_WORKERS`.
- Keep strict two-phase execution: all list URL crawling must finish before any detail task crawling starts.
- Use a persistent queue model for detail tasks. Detail workers claim rows from `crawl_run_detail_tasks` instead of sharing an in-memory task list.
- Each detail worker claims only one pending detail row at a time. After that row is crawled successfully and saved, the worker waits for a random delay between `DETAIL_PAGE_DELAY_MIN` and `DETAIL_PAGE_DELAY_MAX` before claiming the next row.
- Keep the implementation scoped to the current backend process. Multiple processes or distributed workers are out of scope.
- Existing defaults keep current serial behavior until the user increases worker counts.
- Each worker uses its own SQLAlchemy `Session`; workers must not share the main run session or ORM objects.
- Do not introduce distributed workers, Redis-backed detail task queues, new crawler sites, or unrelated frontend workflows.

---

## File Structure

- Modify `backend/app/modules/crawler/config/conf_reader.py`: add config keys and defaults.
- Modify `backend/app/modules/crawler/config/schemas.py`: validate new config fields.
- Modify `frontend/src/api/crawler/crawlerConfig/types.ts`: type new fields.
- Modify `frontend/src/pages/crawler/config/ConfigPage.tsx`: render new worker count inputs.
- Modify `backend/app/models/crawl_run.py`: add indexes or constraints needed for detail queue lookup and dedupe.
- Create `backend/alembic/versions/20260708_0002_add_crawler_detail_queue_indexes.py`: database migration for queue indexes or uniqueness.
- Modify `backend/app/modules/crawler/runtime/details.py`: include `crawling` in unfinished detail status handling.
- Create `backend/app/modules/crawler/runtime/detail_queue.py`: persistent create, claim, reset, and count helpers.
- Create `backend/app/modules/crawler/runtime/threaded.py`: list and detail phase coordinator.
- Modify `backend/app/modules/crawler/runtime/executor.py`: route normal runs and detail retries through the threaded coordinator.
- Modify `backend/app/modules/crawler/runtime/finalize.py`: count `crawling` as unfinished on stopped/interrupted runs.
- Modify `scraper/spiders/javdb/javdb_spider.py`: expose single-detail crawl helper without requiring in-memory list traversal.
- Add or modify backend tests in `backend/tests/test_crawler_config_api.py`, `backend/tests/test_crawler_detail_queue.py`, `backend/tests/test_crawler_threaded_runtime.py`, and `backend/tests/test_crawler_worker_service.py`.
- Modify frontend tests in `frontend/tests/crawler-config.ui.test.tsx`.

---

### Task 1: Backend Worker Count Config

**Files:**
- Modify: `backend/app/modules/crawler/config/conf_reader.py`
- Modify: `backend/app/modules/crawler/config/schemas.py`
- Test: `backend/tests/test_crawler_config_api.py`

**Interfaces:**
- Consumes: existing `read_crawler_config_dict(base_dir: Path | None = None) -> dict[str, int | float]`
- Produces: `CrawlerRuntimeConfig.LIST_MAX_WORKERS: int` and `CrawlerRuntimeConfig.DETAIL_MAX_WORKERS: int`

- [ ] **Step 1: Write failing config tests**

Add these assertions to `test_get_crawler_config_returns_original_keys`:

```python
assert "LIST_MAX_WORKERS" in body["data"]
assert "DETAIL_MAX_WORKERS" in body["data"]
assert body["data"]["LIST_MAX_WORKERS"] >= 1
assert body["data"]["DETAIL_MAX_WORKERS"] >= 1
```

Add this test to `backend/tests/test_crawler_config_api.py`:

```python
def test_crawler_config_reads_worker_counts_from_conf_file(tmp_path) -> None:
    from backend.app.modules.crawler.config.conf_reader import read_crawler_config_dict

    conf_dir = tmp_path / "data" / "configs"
    conf_dir.mkdir(parents=True)
    (conf_dir / "crawler.conf").write_text(
        "LIST_MAX_WORKERS=3\n"
        "DETAIL_MAX_WORKERS=5\n",
        encoding="utf-8",
    )

    data = read_crawler_config_dict(tmp_path)

    assert data["LIST_MAX_WORKERS"] == 3
    assert data["DETAIL_MAX_WORKERS"] == 5
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_config_api.py -v`

Expected: FAIL because `LIST_MAX_WORKERS` and `DETAIL_MAX_WORKERS` are absent.

- [ ] **Step 3: Implement config fields**

In `conf_reader.py`, add both keys to `CONFIG_KEYS`, add fields to `CrawlerRuntimeConfig`, and coerce them as integers:

```python
CONFIG_KEYS: tuple[str, ...] = (
    "MAX_LIST_PAGES",
    "LIST_MAX_WORKERS",
    "DETAIL_MAX_WORKERS",
    "LIST_PAGE_DELAY_MIN",
    "LIST_PAGE_DELAY_MAX",
    "DETAIL_PAGE_DELAY_MIN",
    "DETAIL_PAGE_DELAY_MAX",
    "SECURITY_WAIT_SECONDS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
)

@dataclass(frozen=True)
class CrawlerRuntimeConfig:
    MAX_LIST_PAGES: int = 50
    LIST_MAX_WORKERS: int = 1
    DETAIL_MAX_WORKERS: int = 1
    LIST_PAGE_DELAY_MIN: float = 4.0
    LIST_PAGE_DELAY_MAX: float = 5.0
    DETAIL_PAGE_DELAY_MIN: float = 2.0
    DETAIL_PAGE_DELAY_MAX: float = 3.0
    SECURITY_WAIT_SECONDS: float = 120.0
    REQUEST_TIMEOUT: int = 30
    INCREMENTAL_EXIST_THRESHOLD: int = 0
```

Update integer coercion:

```python
integer_keys = {
    "MAX_LIST_PAGES",
    "LIST_MAX_WORKERS",
    "DETAIL_MAX_WORKERS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
}
if key in integer_keys:
    try:
        result[key] = int(coerced)
    except (TypeError, ValueError):
        result[key] = defaults[key]
```

Clamp worker counts after `MAX_LIST_PAGES`:

```python
result["MAX_LIST_PAGES"] = min(int(result["MAX_LIST_PAGES"]), 50)
result["LIST_MAX_WORKERS"] = max(1, int(result["LIST_MAX_WORKERS"]))
result["DETAIL_MAX_WORKERS"] = max(1, int(result["DETAIL_MAX_WORKERS"]))
```

In `schemas.py`, add:

```python
LIST_MAX_WORKERS: int | None = Field(None, ge=1, le=32)
DETAIL_MAX_WORKERS: int | None = Field(None, ge=1, le=32)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_config_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/config/conf_reader.py backend/app/modules/crawler/config/schemas.py backend/tests/test_crawler_config_api.py
git commit -m "feat: add crawler worker count config"
```

---

### Task 2: Persistent Detail Queue Helpers

**Files:**
- Modify: `backend/app/models/crawl_run.py`
- Create: `backend/alembic/versions/20260708_0002_add_crawler_detail_queue_indexes.py`
- Modify: `backend/app/modules/crawler/runtime/details.py`
- Create: `backend/app/modules/crawler/runtime/detail_queue.py`
- Test: `backend/tests/test_crawler_detail_queue.py`

**Interfaces:**
- Consumes: `CrawlRunDetailTask`
- Produces:
  - `upsert_detail_task(db: Session, *, run: CrawlRun, task_name: str, item: dict[str, Any]) -> CrawlRunDetailTask | None`
  - `claim_next_pending_detail(db: Session, run_id: uuid.UUID) -> CrawlRunDetailTask | None`
  - `reset_crawling_details_to_pending(db: Session, run: CrawlRun) -> list[CrawlRunDetailTask]`

- [ ] **Step 1: Write failing queue tests**

Create `backend/tests/test_crawler_detail_queue.py`:

```python
import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.modules.crawler.runtime.detail_queue import (
    claim_next_pending_detail,
    reset_crawling_details_to_pending,
    upsert_detail_task,
)


def make_run(db_session) -> CrawlRun:
    run = CrawlRun(
        id=uuid.uuid4(),
        task_id=None,
        task_name="queue-test",
        status="running",
        crawl_mode="incremental",
        queued_at=datetime.now(),
    )
    db_session.add(run)
    db_session.commit()
    return run


def test_upsert_detail_task_dedupes_by_code(db_session) -> None:
    run = make_run(db_session)
    item = {"code": "AAA-001", "url": "https://javdb.com/v/aaa001", "name": "AAA 001"}

    first = upsert_detail_task(db_session, run=run, task_name=run.task_name, item=item)
    second = upsert_detail_task(db_session, run=run, task_name=run.task_name, item={**item, "name": "Duplicate"})
    db_session.commit()

    rows = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    assert first is not None
    assert second is None
    assert len(rows) == 1
    assert rows[0].code == "AAA-001"


def test_claim_next_pending_detail_marks_row_crawling(db_session) -> None:
    run = make_run(db_session)
    first = CrawlRunDetailTask(
        run_id=run.id,
        task_name=run.task_name,
        code="AAA-001",
        source_url="https://javdb.com/v/aaa001",
        source_name="AAA 001",
        status="pending_crawl",
        created_at=datetime(2026, 1, 1, 1, 0, 0),
    )
    second = CrawlRunDetailTask(
        run_id=run.id,
        task_name=run.task_name,
        code="AAA-002",
        source_url="https://javdb.com/v/aaa002",
        source_name="AAA 002",
        status="pending_crawl",
        created_at=datetime(2026, 1, 1, 2, 0, 0),
    )
    db_session.add_all([second, first])
    db_session.commit()

    claimed = claim_next_pending_detail(db_session, run.id)

    assert claimed is not None
    assert claimed.code == "AAA-001"
    assert claimed.status == "crawling"


def test_reset_crawling_details_to_pending(db_session) -> None:
    run = make_run(db_session)
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=run.task_name,
        code="AAA-003",
        source_url="https://javdb.com/v/aaa003",
        source_name="AAA 003",
        status="crawling",
        error="interrupted",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()

    reset = reset_crawling_details_to_pending(db_session, run)
    db_session.commit()

    assert [row.code for row in reset] == ["AAA-003"]
    db_session.refresh(detail)
    assert detail.status == "pending_crawl"
    assert detail.error is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_detail_queue.py -v`

Expected: FAIL because `detail_queue.py` does not exist.

- [ ] **Step 3: Implement queue helpers**

Create `backend/app/modules/crawler/runtime/detail_queue.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask


def _detail_identity_filter(run_id: uuid.UUID, item: dict[str, Any]):
    code = item.get("code")
    source_url = item.get("url") or item.get("source_url")
    if code:
        return (CrawlRunDetailTask.run_id == run_id) & (CrawlRunDetailTask.code == str(code))
    return (CrawlRunDetailTask.run_id == run_id) & (CrawlRunDetailTask.source_url == str(source_url or ""))


def upsert_detail_task(
    db: Session,
    *,
    run: CrawlRun,
    task_name: str,
    item: dict[str, Any],
) -> CrawlRunDetailTask | None:
    existing = db.scalar(select(CrawlRunDetailTask).where(_detail_identity_filter(run.id, item)).limit(1))
    if existing is not None:
        return None
    is_skipped = item.get("status") == "skipped"
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task_name,
        code=item.get("code"),
        source_url=item.get("url") or item.get("source_url") or "",
        source_name=item.get("name") or item.get("source_name") or "",
        source_url_name=item.get("_task_url_name"),
        task_url=item.get("_task_url"),
        task_final_url=item.get("_task_final_url"),
        task_url_type=item.get("_task_url_type"),
        status="skipped" if is_skipped else "pending_crawl",
        error=item.get("reason") if is_skipped else None,
        created_at=datetime.now(),
    )
    db.add(detail)
    db.flush()
    return detail


def claim_next_pending_detail(db: Session, run_id: uuid.UUID) -> CrawlRunDetailTask | None:
    detail = db.scalar(
        select(CrawlRunDetailTask)
        .where(
            CrawlRunDetailTask.run_id == run_id,
            CrawlRunDetailTask.status == "pending_crawl",
        )
        .order_by(CrawlRunDetailTask.created_at.asc())
        .limit(1)
    )
    if detail is None:
        return None
    detail.status = "crawling"
    detail.error = None
    db.commit()
    db.refresh(detail)
    return detail


def reset_crawling_details_to_pending(db: Session, run: CrawlRun) -> list[CrawlRunDetailTask]:
    details = (
        db.query(CrawlRunDetailTask)
        .filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "crawling")
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
```

In `details.py`, update unfinished statuses:

```python
UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawling", "crawl_failed", "save_failed"}
```

- [ ] **Step 4: Add database indexes or constraints**

In `backend/app/models/crawl_run.py`, add lookup indexes:

```python
Index("idx_crawl_detail_claim", "run_id", "status", "created_at"),
Index("idx_crawl_detail_run_code", "run_id", "code"),
```

Create Alembic migration:

```python
"""add crawler detail queue indexes

Revision ID: 20260708_0002
Revises: 20260708_0001
Create Date: 2026-07-08
"""

from alembic import op

revision = "20260708_0002"
down_revision = "20260708_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_crawl_detail_claim", "crawl_run_detail_tasks", ["run_id", "status", "created_at"])
    op.create_index("idx_crawl_detail_run_code", "crawl_run_detail_tasks", ["run_id", "code"])


def downgrade() -> None:
    op.drop_index("idx_crawl_detail_run_code", table_name="crawl_run_detail_tasks")
    op.drop_index("idx_crawl_detail_claim", table_name="crawl_run_detail_tasks")
```

- [ ] **Step 5: Run queue tests**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_detail_queue.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/crawl_run.py backend/alembic/versions/20260708_0002_add_crawler_detail_queue_indexes.py backend/app/modules/crawler/runtime/details.py backend/app/modules/crawler/runtime/detail_queue.py backend/tests/test_crawler_detail_queue.py
git commit -m "feat: add crawler detail queue helpers"
```

---

### Task 3: Single Detail Crawl Interface

**Files:**
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Test: `scraper/tests/test_javdb_spider_dedupe_callbacks.py`

**Interfaces:**
- Consumes: existing `JavdbSpider.run_detail_tasks(...)`
- Produces: `JavdbSpider.run_single_detail_task(task: dict, *, task_name: str | None, ...) -> dict`

- [ ] **Step 1: Write failing single-detail spider test**

Add to `scraper/tests/test_javdb_spider_dedupe_callbacks.py`:

```python
def test_run_single_detail_task_processes_one_detail(monkeypatch) -> None:
    spider = JavdbSpider(fetcher=Fetcher())
    monkeypatch.setattr(spider_module, "random_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(spider_module, "is_security_check_page", lambda page: False)
    monkeypatch.setattr(spider, "fetch", lambda url: "<html>detail</html>")
    monkeypatch.setattr(
        spider_module,
        "parse_detail_page",
        lambda page: {"code": "AAA-060", "source_name": "AAA 060"},
    )
    completed: list[dict] = []

    result = spider.run_single_detail_task(
        {"code": "AAA-060", "url": "https://javdb.com/v/aaa060", "name": "AAA 060"},
        task_name="任务",
        on_detail_completed=completed.append,
    )

    assert result["status"] == "completed"
    assert result["detail"]["code"] == "AAA-060"
    assert completed[0]["code"] == "AAA-060"
```

- [ ] **Step 2: Run test to verify failure**

Run: `source .venv/bin/activate && python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py::test_run_single_detail_task_processes_one_detail -v`

Expected: FAIL because `run_single_detail_task` does not exist.

- [ ] **Step 3: Implement single-detail wrapper**

Add to `JavdbSpider`:

```python
def run_single_detail_task(
    self,
    task: dict,
    task_name: str | None = None,
    on_detail_completed=None,
    on_detail_failed=None,
    stop_check=None,
    log_callback=None,
    on_detail_check_callback=None,
    on_item_already_exists=None,
) -> dict:
    result = self.run_detail_tasks(
        [task],
        task_name=task_name,
        on_detail_completed=on_detail_completed,
        on_detail_failed=on_detail_failed,
        stop_check=stop_check,
        log_callback=log_callback,
        on_detail_check_callback=on_detail_check_callback,
        on_item_already_exists=on_item_already_exists,
    )
    return result[0] if result else task
```

- [ ] **Step 4: Run spider tests**

Run: `source .venv/bin/activate && python -m pytest scraper/tests/test_javdb_spider_dedupe_callbacks.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/spiders/javdb/javdb_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py
git commit -m "feat: add single detail spider crawl"
```

---

### Task 4: Threaded Runtime Coordinator

**Files:**
- Create: `backend/app/modules/crawler/runtime/threaded.py`
- Modify: `backend/app/modules/crawler/runtime/engine.py`
- Test: `backend/tests/test_crawler_threaded_runtime.py`

**Interfaces:**
- Consumes:
  - `read_crawler_runtime_config() -> CrawlerRuntimeConfig`
  - `upsert_detail_task(...)`
  - `claim_next_pending_detail(...)`
  - `detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]`
- Produces:
  - `execute_threaded_crawl(db: Session, run: CrawlRun, task: CrawlTask, runtime: CrawlerRuntimeState, *, detail_only: bool = False) -> dict[str, Any]`

- [ ] **Step 1: Write failing coordinator tests**

Create `backend/tests/test_crawler_threaded_runtime.py`:

```python
import uuid
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime.threaded import execute_threaded_crawl


class Runtime:
    def __init__(self) -> None:
        self.progress: dict[str, int] = {}

    def is_stop_requested(self, run_id: str) -> bool:
        return False

    def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
        self.progress = dict(progress)


class FakeSpider:
    def __init__(self) -> None:
        self.list_started = False
        self.detail_started = False

    def collect_detail_tasks_for_url(self, *, url_entry, task_name, crawl_mode, incremental_threshold, stop_check, log_callback, db_check_callback, on_item_already_exists):
        self.list_started = True
        assert self.detail_started is False
        return [
            {"code": f"{url_entry.url_type}-001", "url": f"https://javdb.com/v/{url_entry.url_type}001", "name": url_entry.url_type}
        ]

    def run_single_detail_task(self, task, *, task_name, on_detail_completed, on_detail_failed, stop_check, log_callback, on_detail_check_callback, on_item_already_exists):
        self.detail_started = True
        completed = {**task, "status": "completed", "detail": {"code": task["code"], "source_name": task["name"]}}
        on_detail_completed(completed)
        return completed


class FakePipeline:
    def process_item(self, item, task_name=None, task_id=None):
        return {**item, "source_task_id": task_id}


def make_task_and_run(db_session) -> tuple[CrawlTask, CrawlRun]:
    task = CrawlTask(id=uuid.uuid4(), name="threaded", owner_id=uuid.uuid4(), is_skip=False)
    task.urls = [
        CrawlTaskUrl(position=0, url="https://javdb.com/a", url_type="A", final_url="https://javdb.com/a", source="javdb"),
        CrawlTaskUrl(position=1, url="https://javdb.com/b", url_type="B", final_url="https://javdb.com/b", source="javdb"),
    ]
    db_session.add(task)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="incremental", queued_at=datetime.now())
    db_session.add(run)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(run)
    return task, run


def test_execute_threaded_crawl_finishes_list_before_detail(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    spider = FakeSpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime())

    assert result["total_tasks"] == 2
    assert result["saved"] == 2
    rows = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    assert sorted(row.status for row in rows) == ["saved", "saved"]
```

Add a detail-worker pacing test:

```python
def test_detail_worker_waits_after_successful_save_before_next_claim(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    sleeps: list[tuple[float, float]] = []

    class TwoItemSpider(FakeSpider):
        def collect_detail_tasks_for_url(self, **kwargs):
            return [
                {"code": "WAIT-001", "url": "https://javdb.com/v/wait001", "name": "WAIT 001"},
                {"code": "WAIT-002", "url": "https://javdb.com/v/wait002", "name": "WAIT 002"},
            ]

    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: TwoItemSpider())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())
    monkeypatch.setattr(
        "backend.app.modules.crawler.runtime.threaded.random_sleep",
        lambda min_delay, max_delay: sleeps.append((min_delay, max_delay)),
    )

    execute_threaded_crawl(db_session, run, task, Runtime())

    assert sleeps
    assert all(min_delay == 2.0 and max_delay == 3.0 for min_delay, max_delay in sleeps)
```

- [ ] **Step 2: Run test to verify failure**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_threaded_runtime.py -v`

Expected: FAIL because `threaded.py` does not exist.

- [ ] **Step 3: Implement coordinator skeleton**

Create `backend/app/modules/crawler/runtime/threaded.py` with these boundaries:

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
from backend.app.modules.crawler.runtime.detail_queue import claim_next_pending_detail, upsert_detail_task
from backend.app.modules.crawler.runtime.details import detail_row_to_task_info
from backend.app.modules.crawler.runtime.events import append_run_log_for_run
from backend.app.modules.crawler.runtime.progress import new_progress, write_progress
from backend.app.modules.crawler.runtime.source_task_names import find_existing_movie_codes, movie_code_exists
from backend.app.modules.content.movies.persistence import append_source_task_id, upsert_movie_with_magnets
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.core.throttle import random_sleep
from scraper.pipelines.movie_pipeline import MoviePipeline
from scraper.spiders.javdb.javdb_spider import JavdbSpider


def build_spider() -> JavdbSpider:
    runtime_config = read_crawler_runtime_config()
    cookies = CookieManager(JAVDB_SITE["cookie_file"]).load()
    fetcher = ScraplingFetcher(headers=JAVDB_SITE["headers"], cookies=cookies, timeout=runtime_config.REQUEST_TIMEOUT)
    return JavdbSpider(fetcher=fetcher)


def build_pipeline() -> MoviePipeline:
    return MoviePipeline()


def execute_threaded_crawl(db: Session, run: CrawlRun, task: CrawlTask, runtime: Any, *, detail_only: bool = False) -> dict[str, Any]:
    config = read_crawler_runtime_config()
    progress = new_progress()
    if not detail_only:
        _run_list_phase(db, run, task, runtime, config)
    _run_detail_phase(db, run, task, runtime, config, progress)
    write_progress(runtime, str(run.id), progress)
    return _build_threaded_result(db, run, task, runtime)
```

Implement `_run_list_phase`, `_run_detail_phase`, and `_build_threaded_result` in the same file. Keep this first implementation serial internally when `LIST_MAX_WORKERS == 1` and `DETAIL_MAX_WORKERS == 1`, but preserve the ThreadPoolExecutor structure:

```python
with ThreadPoolExecutor(max_workers=max(1, config.LIST_MAX_WORKERS)) as pool:
    futures = [pool.submit(_collect_url, entry) for entry in task.urls]
    for future in as_completed(futures):
        for item in future.result():
            upsert_detail_task(db, run=run, task_name=task.name, item=item)
        db.commit()
```

For detail completion, build item data the same way as `JavdbCrawlerEngine._build_detail_item`:

```python
detail_info = detail_row_to_task_info(detail)
result = spider.run_single_detail_task(...)
item = {**(result.get("detail") or {}), "source_url": result.get("url"), "source_name": result.get("name")}
cleaned = pipeline.process_item(item, task_name=task.name, task_id=str(task.id))
movie_id = upsert_movie_with_magnets(worker_db, {**cleaned, "source_task_ids": [task.id]})
```

Detail workers must not prefetch multiple rows. Implement the worker loop as a
single-row claim, crawl, save, sleep cycle:

```python
def _detail_worker(run_id, task_id, task_name, runtime, config, progress):
    spider = build_spider()
    pipeline = build_pipeline()
    while not runtime.is_stop_requested(str(run_id)):
        with SessionLocal() as worker_db:
            detail = claim_next_pending_detail(worker_db, run_id)
            if detail is None:
                return
            detail_info = detail_row_to_task_info(detail)
            result = spider.run_single_detail_task(...)
            item = {
                **(result.get("detail") or {}),
                "source_url": result.get("url"),
                "source_name": result.get("name"),
            }
            cleaned = pipeline.process_item(item, task_name=task_name, task_id=str(task_id))
            upsert_movie_with_magnets(worker_db, {**cleaned, "source_task_ids": [task_id]})
            detail.status = "saved"
            worker_db.commit()

        if not runtime.is_stop_requested(str(run_id)):
            random_sleep(config.DETAIL_PAGE_DELAY_MIN, config.DETAIL_PAGE_DELAY_MAX)
```

If the detail crawl fails or save fails, mark that single row `crawl_failed` or
`save_failed`, commit the row state, and then continue the loop. The delay is
required after a successful crawl and save; implementation may also apply the
same delay after failures to preserve the existing detail-page throttling.

- [ ] **Step 4: Run coordinator test**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_threaded_runtime.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runtime/threaded.py backend/app/modules/crawler/runtime/engine.py backend/tests/test_crawler_threaded_runtime.py
git commit -m "feat: add threaded crawler runtime coordinator"
```

---

### Task 5: Wire Executor, Stop, Restart, and Retry

**Files:**
- Modify: `backend/app/modules/crawler/runtime/executor.py`
- Modify: `backend/app/modules/crawler/runtime/finalize.py`
- Modify: `backend/app/modules/crawler/runtime/details.py`
- Test: `backend/tests/test_crawler_worker_service.py`
- Test: `backend/tests/test_crawler_threaded_runtime.py`

**Interfaces:**
- Consumes: `execute_threaded_crawl(..., detail_only: bool = False) -> dict[str, Any]`
- Produces: `execute_run` uses the persistent queue path for normal runs and detail retries.

- [ ] **Step 1: Write failing executor tests**

Add to `backend/tests/test_crawler_worker_service.py`:

```python
def test_execute_run_uses_threaded_detail_retry_path(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    calls = []

    def fake_threaded(db, run_obj, task_obj, runtime_obj, *, detail_only=False):
        calls.append(detail_only)
        detail = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run_obj.id).one()
        detail.status = "saved"
        db.commit()
        return {"total_tasks": 1, "saved": 1}

    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.execute_threaded_crawl", fake_threaded)
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("threaded-retry")
    run_obj = session.get(CrawlRun, run.id)
    run_obj.result = {"detail_retry": True}
    session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="RETRY-001",
        source_url="https://javdb.com/v/retry001",
        source_name="RETRY 001",
        status="pending_crawl",
        created_at=datetime.now(),
    ))
    session.commit()

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    assert calls == [True]
    assert session.get(CrawlRun, run.id).status == "completed"
```

Add:

```python
def test_finalize_resets_crawling_details_when_stopped(db_session) -> None:
    from backend.app.modules.crawler.runtime.finalize import finalize_run

    run = CrawlRun(task_id=None, task_name="stop", status="running", crawl_mode="incremental", queued_at=datetime.now())
    db_session.add(run)
    db_session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name="stop",
        code="STOP-QUEUE",
        source_url="https://javdb.com/v/stopqueue",
        source_name="STOP QUEUE",
        status="crawling",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()

    class Runtime:
        pass

    finalize_run(db_session, run, Runtime(), {"total_tasks": 1}, stopped=True)

    db_session.refresh(detail)
    assert detail.status == "pending_crawl"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_uses_threaded_detail_retry_path backend/tests/test_crawler_worker_service.py::test_finalize_resets_crawling_details_when_stopped -v`

Expected: FAIL until executor imports `execute_threaded_crawl` and unfinished statuses include `crawling`.

- [ ] **Step 3: Wire executor**

In `executor.py`, import:

```python
from backend.app.modules.crawler.runtime.threaded import execute_threaded_crawl
```

Replace the old `engine.crawl_task` / `engine.crawl_detail_tasks` branch with:

```python
detail_phase_restart = has_detail_phase_started(db, run)
detail_retry_requested = bool((run.result or {}).get("detail_retry"))
pending_detail_retry_rows = (
    db.query(CrawlRunDetailTask)
    .filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "pending_crawl")
    .order_by(CrawlRunDetailTask.created_at.asc())
    .all()
)
detail_only = bool(pending_detail_retry_rows and (detail_phase_restart or detail_retry_requested))
if detail_only:
    append_run_log_for_run(db, run, f"检测到待重试详情子任务 {len(pending_detail_retry_rows)} 条，跳过列表收集直接重试详情", "INFO")

result = execute_threaded_crawl(db, run, task, runtime, detail_only=detail_only)
```

Keep finalization:

```python
stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
finalize_run(db, run, runtime, result, stopped=stopped)
```

- [ ] **Step 4: Verify stop reset covers `crawling`**

Confirm `details.py` has:

```python
UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawling", "crawl_failed", "save_failed"}
TERMINAL_DETAIL_STATUSES = {"saved", "skipped"}
```

- [ ] **Step 5: Run backend crawler tests**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_threaded_runtime.py backend/tests/test_crawler_realtime_events.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/executor.py backend/app/modules/crawler/runtime/finalize.py backend/app/modules/crawler/runtime/details.py backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_threaded_runtime.py
git commit -m "feat: run crawler through threaded queue"
```

---

### Task 6: Frontend Config Inputs

**Files:**
- Modify: `frontend/src/api/crawler/crawlerConfig/types.ts`
- Modify: `frontend/src/pages/crawler/config/ConfigPage.tsx`
- Test: `frontend/tests/crawler-config.ui.test.tsx`

**Interfaces:**
- Consumes: API fields `LIST_MAX_WORKERS?: number` and `DETAIL_MAX_WORKERS?: number`
- Produces: editable Ant Design `InputNumber` fields submitted with the config form.

- [ ] **Step 1: Write failing frontend test**

In `frontend/tests/crawler-config.ui.test.tsx`, add expectations after the config page renders:

```ts
expect(await screen.findByLabelText('列表线程数')).toBeInTheDocument()
expect(screen.getByLabelText('详情线程数')).toBeInTheDocument()
```

Extend the mocked config response:

```ts
LIST_MAX_WORKERS: 2,
DETAIL_MAX_WORKERS: 4,
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend && npm test -- crawler-config.ui.test.tsx`

Expected: FAIL because the labels are missing.

- [ ] **Step 3: Add TypeScript fields**

In `frontend/src/api/crawler/crawlerConfig/types.ts`, add:

```ts
LIST_MAX_WORKERS?: number
DETAIL_MAX_WORKERS?: number
```

- [ ] **Step 4: Add form inputs**

In `ConfigPage.tsx`, place these after `MAX_LIST_PAGES`:

```tsx
<Form.Item
    name="LIST_MAX_WORKERS"
    label="列表线程数"
    tooltip="列表阶段并发处理 URL 的线程数；每个线程会顺序爬完一个 URL 的所有页"
>
    <InputNumber min={1} max={32} style={{width: '100%'}}/>
</Form.Item>
<Form.Item
    name="DETAIL_MAX_WORKERS"
    label="详情线程数"
    tooltip="详情阶段并发领取 pending 子任务的线程数"
>
    <InputNumber min={1} max={32} style={{width: '100%'}}/>
</Form.Item>
```

- [ ] **Step 5: Run frontend test**

Run: `cd frontend && npm test -- crawler-config.ui.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/crawler/crawlerConfig/types.ts frontend/src/pages/crawler/config/ConfigPage.tsx frontend/tests/crawler-config.ui.test.tsx
git commit -m "feat: expose crawler worker config"
```

---

### Task 7: Full Regression and Cleanup

**Files:**
- Modify only files already touched if regression failures reveal small integration issues.
- Test: backend crawler tests, scraper tests, frontend config test.

**Interfaces:**
- Consumes: all previous task deliverables.
- Produces: verified implementation ready for review.

- [ ] **Step 1: Run focused backend regression**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_crawler_config_api.py \
  backend/tests/test_crawler_detail_queue.py \
  backend/tests/test_crawler_threaded_runtime.py \
  backend/tests/test_crawler_worker_service.py \
  backend/tests/test_crawler_realtime_events.py \
  backend/tests/test_crawler_runtime_redis.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run scraper regression**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused regression**

Run:

```bash
cd frontend
npm test -- crawler-config.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run static build checks if focused tests pass**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended crawler config, crawler runtime, migration, tests, and frontend config files are modified.

- [ ] **Step 6: Commit final cleanup if needed**

If Step 5 shows small integration fixes not already committed:

```bash
git add <specific-files>
git commit -m "test: verify threaded crawler queue"
```

If Step 5 shows no uncommitted implementation files, do not create an empty commit.

---

## Self-Review

- Spec coverage: The plan covers separate worker config, two-phase execution, persistent detail queue, per-worker sessions, stop/restart/retry behavior, backend tests, and frontend config inputs.
- Placeholder scan: No unresolved placeholders or open-ended deferred steps are present.
- Type consistency: The plan consistently uses `LIST_MAX_WORKERS`, `DETAIL_MAX_WORKERS`, `upsert_detail_task`, `claim_next_pending_detail`, `reset_crawling_details_to_pending`, and `execute_threaded_crawl`.
- Scope check: The plan stays within the existing crawler runtime and config UI. It does not add distributed workers, Redis detail queues, new crawler sites, or unrelated modules.
