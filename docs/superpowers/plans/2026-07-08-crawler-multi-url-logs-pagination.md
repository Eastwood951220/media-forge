# Crawler Multi-URL Logs And Detail List Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make multi-URL crawler runs clearly identify each URL by `url_name`, preserve that context through detail tasks and retries, and make the run detail child task table scale to thousands of rows.

**Architecture:** Keep the current sequential crawler run architecture. Add URL-entry context as nullable fields on `CrawlRunDetailTask`, pass those fields through runtime callbacks and retry conversion, format spider logs with a URL-aware prefix, and move the frontend run detail task table from local pagination to server-side pagination.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Pytest, React 19, TypeScript 6, Vite 8, Ant Design 6, Vitest, React Testing Library.

## Global Constraints

- Do not change queue scheduling between different crawler runs.
- Do not split one crawler task into separate URL-level runs.
- Do not redesign the run detail page beyond the child task table behavior and source URL context needed for this issue.
- Do not change JavDB parsing rules or movie persistence rules.
- Preserve existing run lifecycle, retry, stop, realtime, and movie persistence behavior.
- Existing rows must remain valid; new detail task URL context fields are nullable.
- Use server-side pagination for run detail child tasks; do not accumulate thousands of child tasks in the browser.

---

## File Structure

- Modify `backend/app/models/crawl_run.py`: add nullable URL-entry context columns to `CrawlRunDetailTask`.
- Create `backend/alembic/versions/20260708_0001_add_url_context_to_crawl_run_detail_tasks.py`: add and drop the nullable columns.
- Modify `backend/app/modules/crawler/runs/schemas.py`: expose URL-entry context fields in `CrawlRunDetailTaskRead`.
- Modify `backend/app/modules/crawler/runs/router.py`: include `source_url_name` in keyword filtering.
- Modify `backend/app/modules/crawler/runtime/callbacks.py`: persist URL-entry context when creating detail task rows.
- Modify `backend/app/modules/crawler/runtime/details.py`: preserve URL-entry context when retrying detail rows.
- Modify `backend/app/modules/crawler/runtime/events.py`: include URL-entry context in realtime detail payloads.
- Modify `scraper/spiders/javdb/javdb_spider.py`: add URL-aware log prefix helpers and use them in list and detail phases.
- Modify `backend/tests/test_crawler_runs_api.py`: cover persisted fields, API return, keyword filtering, and pagination.
- Create `backend/tests/test_javdb_spider_multi_url.py`: cover multi-URL progression and URL-aware logs.
- Modify `frontend/src/api/crawlerRun/types.ts`: add optional URL context fields.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`: track `taskPage`, `taskTotal`, server-side fetch params, and page resets.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`: merge only current-page rows and refresh current page when membership changes.
- Modify `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`: controlled server-side pagination and source URL column.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: pass new pagination and refresh props.
- Modify `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`: update mocks and add pagination/filter assertions.

---

### Task 1: Persist And Expose Detail Task URL Context

**Files:**
- Create: `backend/alembic/versions/20260708_0001_add_url_context_to_crawl_run_detail_tasks.py`
- Modify: `backend/app/models/crawl_run.py`
- Modify: `backend/app/modules/crawler/runs/schemas.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Produces ORM fields on `CrawlRunDetailTask`: `source_url_name: str | None`, `task_url: str | None`, `task_final_url: str | None`, `task_url_type: str | None`.
- Produces API fields on `CrawlRunDetailTaskRead` with the same names and nullable string types.
- Produces keyword behavior: `keyword` matches `code`, `source_name`, or `source_url_name`.

- [ ] **Step 1: Write failing API tests**

Append these tests to `backend/tests/test_crawler_runs_api.py`:

```python
def test_run_tasks_returns_url_context_and_supports_keyword_filter(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(
            run_id=run.id,
            task_name="任务",
            code="AAA-001",
            source_url="https://javdb.com/v/aaa001",
            source_name="AAA 001",
            source_url_name="演员A",
            task_url="https://javdb.com/actors/a",
            task_final_url="https://javdb.com/actors/a?page=1",
            task_url_type="actors",
            status="saved",
            created_at=datetime.now(),
        ),
        CrawlRunDetailTask(
            run_id=run.id,
            task_name="任务",
            code="BBB-001",
            source_url="https://javdb.com/v/bbb001",
            source_name="BBB 001",
            source_url_name="标签B",
            task_url="https://javdb.com/tags/b",
            task_final_url="https://javdb.com/tags/b?page=1",
            task_url_type="tags",
            status="pending_crawl",
            created_at=datetime.now(),
        ),
    ])
    session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks?keyword=标签B", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "BBB-001"
    assert body["rows"][0]["source_url_name"] == "标签B"
    assert body["rows"][0]["task_url"] == "https://javdb.com/tags/b"
    assert body["rows"][0]["task_final_url"] == "https://javdb.com/tags/b?page=1"
    assert body["rows"][0]["task_url_type"] == "tags"


def test_run_tasks_uses_server_side_pagination(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    for index in range(5):
        session.add(
            CrawlRunDetailTask(
                run_id=run.id,
                task_name="任务",
                code=f"PAGE-{index}",
                source_url=f"https://javdb.com/v/page-{index}",
                source_name=f"PAGE {index}",
                source_url_name="分页来源",
                status="pending_crawl",
                created_at=datetime(2026, 7, 8, 0, 0, index),
            )
        )
    session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks?skip=2&limit=2", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 5
    assert [row["code"] for row in body["rows"]] == ["PAGE-2", "PAGE-3"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runs_api.py::test_run_tasks_returns_url_context_and_supports_keyword_filter tests/test_crawler_runs_api.py::test_run_tasks_uses_server_side_pagination -v
```

Expected: FAIL because `CrawlRunDetailTask` does not accept `source_url_name` yet.

- [ ] **Step 3: Add ORM columns**

In `backend/app/models/crawl_run.py`, extend `CrawlRunDetailTask` after `source_name`:

```python
    source_url_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    task_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_url_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/alembic/versions/20260708_0001_add_url_context_to_crawl_run_detail_tasks.py`:

```python
"""add url context to crawl run detail tasks

Revision ID: 20260708_0001
Revises: 20260704_0001
Create Date: 2026-07-08 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260708_0001"
down_revision = "20260704_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_run_detail_tasks", sa.Column("source_url_name", sa.String(length=200), nullable=True))
    op.add_column("crawl_run_detail_tasks", sa.Column("task_url", sa.Text(), nullable=True))
    op.add_column("crawl_run_detail_tasks", sa.Column("task_final_url", sa.Text(), nullable=True))
    op.add_column("crawl_run_detail_tasks", sa.Column("task_url_type", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_run_detail_tasks", "task_url_type")
    op.drop_column("crawl_run_detail_tasks", "task_final_url")
    op.drop_column("crawl_run_detail_tasks", "task_url")
    op.drop_column("crawl_run_detail_tasks", "source_url_name")
```

- [ ] **Step 5: Expose fields in schema**

In `backend/app/modules/crawler/runs/schemas.py`, add these fields to `CrawlRunDetailTaskRead` after `source_name`:

```python
    source_url_name: str | None = None
    task_url: str | None = None
    task_final_url: str | None = None
    task_url_type: str | None = None
```

- [ ] **Step 6: Extend keyword filtering**

In `backend/app/modules/crawler/runs/router.py`, replace the `if keyword:` filter block with:

```python
    if keyword:
        query = query.filter(
            CrawlRunDetailTask.code.ilike(f"%{keyword}%")
            | CrawlRunDetailTask.source_name.ilike(f"%{keyword}%")
            | CrawlRunDetailTask.source_url_name.ilike(f"%{keyword}%")
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runs_api.py::test_run_tasks_returns_url_context_and_supports_keyword_filter tests/test_crawler_runs_api.py::test_run_tasks_uses_server_side_pagination -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/crawl_run.py backend/app/modules/crawler/runs/schemas.py backend/app/modules/crawler/runs/router.py backend/alembic/versions/20260708_0001_add_url_context_to_crawl_run_detail_tasks.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: expose crawler detail url context"
```

---

### Task 2: Preserve URL Context Through Runtime Callbacks And Detail Retry

**Files:**
- Modify: `backend/app/modules/crawler/runtime/callbacks.py`
- Modify: `backend/app/modules/crawler/runtime/details.py`
- Modify: `backend/app/modules/crawler/runtime/events.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Consumes `CrawlRunDetailTask` URL context fields from Task 1.
- Produces `detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]` with `_task_url`, `_task_final_url`, `_task_url_type`, and `_task_url_name`.
- Runtime callback copies `_task_url`, `_task_final_url`, `_task_url_type`, and `_task_url_name` into database fields.
- Realtime detail payloads include `source_url_name`, `task_url`, `task_final_url`, and `task_url_type`.

- [ ] **Step 1: Write failing callback and retry tests**

Append these tests to `backend/tests/test_crawler_runs_api.py`:

Add `CrawlTask` to the existing model imports:

```python
from backend.app.models.crawl_task import CrawlTask
```

```python
def test_detail_row_to_task_info_preserves_url_context() -> None:
    detail = CrawlRunDetailTask(
        run_id=uuid.uuid4(),
        task_name="任务",
        code="AAA-001",
        source_url="https://javdb.com/v/aaa001",
        source_name="AAA 001",
        source_url_name="演员A",
        task_url="https://javdb.com/actors/a",
        task_final_url="https://javdb.com/actors/a?page=1",
        task_url_type="actors",
        status="pending_crawl",
        created_at=datetime.now(),
    )

    from backend.app.modules.crawler.runtime.details import detail_row_to_task_info

    assert detail_row_to_task_info(detail) == {
        "code": "AAA-001",
        "url": "https://javdb.com/v/aaa001",
        "name": "AAA 001",
        "_task_url": "https://javdb.com/actors/a",
        "_task_final_url": "https://javdb.com/actors/a?page=1",
        "_task_url_type": "actors",
        "_task_url_name": "演员A",
    }


def test_on_tasks_batch_created_persists_url_context(admin_user) -> None:
    from backend.app.modules.crawler.runtime.callbacks import CrawlerCallbackContext, build_crawl_callbacks
    from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
    from backend.app.modules.crawler.runtime.progress import new_progress

    class Runtime:
        def write_progress(self, _run_id: str, _progress: dict) -> None:
            return None

        def is_stop_requested(self, _run_id: str) -> bool:
            return False

    session = TestingSessionLocal()
    task = CrawlTask(name="任务", storage_location="local", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.commit()

    ctx = CrawlerCallbackContext(
        db=session,
        run=run,
        task=task,
        runtime=Runtime(),
        detail_index=DetailTaskIndex(),
        progress=new_progress(),
    )
    callbacks = build_crawl_callbacks(ctx)

    callbacks.on_tasks_batch_created([
        {
            "code": "AAA-001",
            "url": "https://javdb.com/v/aaa001",
            "name": "AAA 001",
            "_task_url_name": "演员A",
            "_task_url": "https://javdb.com/actors/a",
            "_task_final_url": "https://javdb.com/actors/a?page=1",
            "_task_url_type": "actors",
        }
    ])

    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).one()

    assert detail.source_url_name == "演员A"
    assert detail.task_url == "https://javdb.com/actors/a"
    assert detail.task_final_url == "https://javdb.com/actors/a?page=1"
    assert detail.task_url_type == "actors"


def test_run_task_rows_created_from_spider_payload_keep_url_context(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="AAA-001",
        source_url="https://javdb.com/v/aaa001",
        source_name="AAA 001",
        source_url_name="演员A",
        task_url="https://javdb.com/actors/a",
        task_final_url="https://javdb.com/actors/a?page=1",
        task_url_type="actors",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    session.add(detail)
    session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=headers)

    assert response.status_code == HTTPStatus.OK
    row = response.json()["rows"][0]
    assert row["source_url_name"] == "演员A"
    assert row["task_url"] == "https://javdb.com/actors/a"
    assert row["task_final_url"] == "https://javdb.com/actors/a?page=1"
    assert row["task_url_type"] == "actors"
```

The callback test protects runtime persistence. The API test protects serialized output while Task 2 changes runtime conversion.

- [ ] **Step 2: Run retry conversion test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runs_api.py::test_detail_row_to_task_info_preserves_url_context -v
```

Expected: FAIL because `detail_row_to_task_info()` returns only `code`, `url`, and `name`.

- [ ] **Step 3: Update detail retry conversion**

In `backend/app/modules/crawler/runtime/details.py`, replace `detail_row_to_task_info()` with:

```python
def detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]:
    return {
        "code": detail.code,
        "url": detail.source_url,
        "name": detail.source_name,
        "_task_url": detail.task_url,
        "_task_final_url": detail.task_final_url,
        "_task_url_type": detail.task_url_type,
        "_task_url_name": detail.source_url_name,
    }
```

- [ ] **Step 4: Persist URL context from list batches**

In `backend/app/modules/crawler/runtime/callbacks.py`, inside `on_tasks_batch_created()`, add the URL fields to the `CrawlRunDetailTask(...)` constructor:

```python
                    source_url_name=item.get("_task_url_name"),
                    task_url=item.get("_task_url"),
                    task_final_url=item.get("_task_final_url"),
                    task_url_type=item.get("_task_url_type"),
```

Inside the `elif detail.status not in {"saved", "skipped"}:` block, set the same fields when refreshing an existing row:

```python
                detail.source_url_name = item.get("_task_url_name")
                detail.task_url = item.get("_task_url")
                detail.task_final_url = item.get("_task_final_url")
                detail.task_url_type = item.get("_task_url_type")
```

- [ ] **Step 5: Include URL context in realtime detail events**

In `backend/app/modules/crawler/runtime/events.py`, inside `publish_run_detail_updated()`, add these payload fields after `"source_name": detail.source_name,`:

```python
                    "source_url_name": detail.source_url_name,
                    "task_url": detail.task_url,
                    "task_final_url": detail.task_final_url,
                    "task_url_type": detail.task_url_type,
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_runs_api.py::test_detail_row_to_task_info_preserves_url_context tests/test_crawler_runs_api.py::test_on_tasks_batch_created_persists_url_context tests/test_crawler_runs_api.py::test_run_task_rows_created_from_spider_payload_keep_url_context -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/callbacks.py backend/app/modules/crawler/runtime/details.py backend/app/modules/crawler/runtime/events.py backend/tests/test_crawler_runs_api.py
git commit -m "fix: preserve crawler detail url context"
```

---

### Task 3: Add URL-Aware Spider Logs And Multi-URL Progression Coverage

**Files:**
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Create: `backend/tests/test_javdb_spider_multi_url.py`

**Interfaces:**
- Produces `JavdbSpider._url_label(url_entry: CrawlTaskUrlEntry) -> str`.
- Produces `JavdbSpider._task_prefix(task_name: str | None, url_label: str | None = None) -> str`.
- List and detail log messages include `[URL: <label>]` when URL context exists.

- [ ] **Step 1: Write failing spider tests**

Create `backend/tests/test_javdb_spider_multi_url.py`:

```python
from __future__ import annotations

from scraper.spiders.javdb import javdb_spider
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


class FakeFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> str:
        self.urls.append(url)
        return url


def test_collect_all_detail_tasks_continues_to_next_url_after_empty_page(monkeypatch) -> None:
    fetcher = FakeFetcher()
    spider = JavdbSpider(fetcher)
    logs: list[str] = []

    monkeypatch.setattr(javdb_spider, "MAX_LIST_PAGES", 2)
    monkeypatch.setattr(javdb_spider, "random_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(javdb_spider, "is_security_check_page", lambda _page: False)

    def fake_parse_search_page(page: str, source_page: int) -> list[dict]:
        if "actors/a" in page and source_page == 1:
            return [{"code": "AAA-001", "url": "https://javdb.com/v/aaa001", "name": "AAA 001"}]
        if "actors/a" in page and source_page == 2:
            return []
        if "tags/b" in page and source_page == 1:
            return [{"code": "BBB-001", "url": "https://javdb.com/v/bbb001", "name": "BBB 001"}]
        return []

    monkeypatch.setattr(javdb_spider, "parse_search_page", fake_parse_search_page)

    task = CrawlTask(
        name="任务",
        urls=[
            CrawlTaskUrlEntry(
                url="https://javdb.com/actors/a",
                url_type="actors",
                final_url="https://javdb.com/actors/a?page=1",
                url_name="演员A",
            ),
            CrawlTaskUrlEntry(
                url="https://javdb.com/tags/b",
                url_type="tags",
                final_url="https://javdb.com/tags/b?page=1",
                url_name="标签B",
            ),
        ],
    )

    detail_tasks = spider.collect_all_detail_tasks(task, log_callback=lambda message, _level="INFO": logs.append(message))

    assert [item["code"] for item in detail_tasks] == ["AAA-001", "BBB-001"]
    assert any("actors/a?page=1" in url for url in fetcher.urls)
    assert any("actors/a?page=2" in url for url in fetcher.urls)
    assert any("tags/b?page=1" in url for url in fetcher.urls)
    assert any("[任务][URL: 演员A] 列表页 2 无数据" in message for message in logs)
    assert any("[任务][URL: 标签B] 正在获取列表页 1/2" in message for message in logs)


def test_run_detail_tasks_logs_url_name(monkeypatch) -> None:
    fetcher = FakeFetcher()
    spider = JavdbSpider(fetcher)
    logs: list[str] = []

    monkeypatch.setattr(javdb_spider, "random_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(javdb_spider, "is_security_check_page", lambda _page: False)
    monkeypatch.setattr(javdb_spider, "parse_detail_page", lambda _page: {"code": "AAA-001", "source_name": "AAA 001"})

    spider.run_detail_tasks(
        [
            {
                "code": "AAA-001",
                "url": "https://javdb.com/v/aaa001",
                "name": "AAA 001",
                "_task_url_name": "演员A",
            }
        ],
        task_name="任务",
        log_callback=lambda message, _level="INFO": logs.append(message),
    )

    assert any("[任务][URL: 演员A] 详情 1/1 处理中" in message for message in logs)
    assert any("[任务][URL: 演员A] 详情 1/1 完成" in message for message in logs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_javdb_spider_multi_url.py -v
```

Expected: FAIL because current logs do not include `[URL: ...]`.

- [ ] **Step 3: Add prefix helpers**

In `scraper/spiders/javdb/javdb_spider.py`, add these methods inside `JavdbSpider` below `_emit()`:

```python
    @staticmethod
    def _url_label(url_entry: CrawlTaskUrlEntry) -> str:
        return (
            (url_entry.url_name or "").strip()
            or (url_entry.url_type or "").strip()
            or (url_entry.final_url or url_entry.url or "").strip()
            or "-"
        )

    @staticmethod
    def _detail_url_label(task: dict) -> str:
        return (
            str(task.get("_task_url_name") or "").strip()
            or str(task.get("_task_url_type") or "").strip()
            or str(task.get("_task_final_url") or task.get("_task_url") or "").strip()
        )

    @staticmethod
    def _task_prefix(task_name: str | None, url_label: str | None = None) -> str:
        prefix = f"[{task_name}]" if task_name else ""
        if url_label:
            prefix = f"{prefix}[URL: {url_label}]"
        return prefix
```

- [ ] **Step 4: Use URL prefix in list collection**

In `collect_detail_tasks_for_url()`, after `verification_count = 0`, add:

```python
        url_label = self._url_label(url_entry)
        prefix = self._task_prefix(task_name, url_label)
```

Then replace list-phase message prefixes in this method from `[{task_name}]` to `{prefix}`. For example:

```python
        msg = f"{prefix} 增量阈值: {incremental_threshold}, 爬取模式: {crawl_mode}"
        msg = f"{prefix} 开始收集列表页 url={final_url}, 最大页数={max_pages}"
        msg = f"{prefix} 列表页 {page_no} 收到停止信号"
        msg = f"{prefix} 正在获取列表页 {page_no}/{max_pages}"
        msg = f"{prefix} 列表页 {page_no} 无数据, 停止收集"
        msg = f"{prefix} URL 列表收集完成: 共 {len(detail_tasks)} 条任务"
```

Keep the existing message content after the prefix.

- [ ] **Step 5: Improve all-URL transition logs**

In `collect_all_detail_tasks()`, replace the per-URL log:

```python
            url_label = self._url_label(url_entry)
            msg = f"[{task.name}][URL: {url_label}] 处理 URL {i}/{len(task.urls)}: {url_entry.url_type}"
            self._emit(msg, log_callback)
```

Keep the final all-URL completion log unchanged.

- [ ] **Step 6: Use URL prefix in detail processing**

In `run_detail_tasks()`, keep the initial and final summary prefix as task-only. Inside the loop after `task = tasks[index]`, add:

```python
            detail_prefix = self._task_prefix(task_name, self._detail_url_label(task))
```

Then use `detail_prefix` for per-detail skip, DB skip, missing URL, processing, security verification, completed, and failed messages. For example:

```python
                msg = (
                    f"{detail_prefix} 详情 {index + 1}/{total} 跳过: "
                    f"name={task.get('name')} reason={task.get('reason')}"
                )
```

- [ ] **Step 7: Run spider tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_javdb_spider_multi_url.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add scraper/spiders/javdb/javdb_spider.py backend/tests/test_javdb_spider_multi_url.py
git commit -m "fix: add crawler url-aware logs"
```

---

### Task 4: Convert Run Detail Task Table To Server-Side Pagination

**Files:**
- Modify: `frontend/src/api/crawlerRun/types.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
- Modify: `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Modify: `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`

**Interfaces:**
- Consumes backend fields from Task 1.
- Produces hook state: `taskPage: number`, `taskTotal: number`, `setTaskPage(page: number): void`, `handleTaskTableChange(page: number, size: number): void`.
- `RunTaskTable` receives controlled pagination props: `current`, `pageSize`, `total`, `onPageChange`.
- `useRunDetailRealtime` receives `fetchTasks: () => Promise<void>` and refreshes the current page when realtime membership changes.

- [ ] **Step 1: Update frontend tests to expect server-side paging**

In `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`, add this import:

```typescript
import userEvent from '@testing-library/user-event'
```

Add these tests inside the existing `describe('RunDetail retry controls', () => { ... })` block:

```typescript
  it('fetches first task page with skip and limit', async () => {
    render(<RunDetailPage />)

    await screen.findByText('FAIL-001')

    expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
      skip: 0,
      limit: 50,
      status: undefined,
      keyword: undefined,
    })
  })

  it('resets to first page and fetches keyword filter from server', async () => {
    const user = userEvent.setup()
    render(<RunDetailPage />)

    await screen.findByText('FAIL-001')
    const search = screen.getByPlaceholderText('搜索番号或名称')
    await user.type(search, '演员A')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(getCrawlerRunTasks).toHaveBeenLastCalledWith('run-1', {
        skip: 0,
        limit: 50,
        status: undefined,
        keyword: '演员A',
      })
    })
  })
```

Update the `failedTask` fixture to include URL context:

```typescript
  source_url_name: '演员A',
  task_url: 'https://javdb.com/actors/a',
  task_final_url: 'https://javdb.com/actors/a?page=1',
  task_url_type: 'actors',
```

The `savedTask` fixture can inherit these fields.

- [ ] **Step 2: Run frontend tests to verify they fail**

Run:

```bash
cd frontend
npm test -- --run src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
```

Expected: FAIL because current `getCrawlerRunTasks()` call omits `skip` and uses `limit: 200`.

- [ ] **Step 3: Add optional URL fields to API type**

In `frontend/src/api/crawlerRun/types.ts`, add these fields to `CrawlRunDetailTask` after `source_name`:

```typescript
  source_url_name?: string | null
  task_url?: string | null
  task_final_url?: string | null
  task_url_type?: string | null
```

- [ ] **Step 4: Update `useRunDetail` state and fetch params**

In `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`, add state:

```typescript
  const [taskPage, setTaskPage] = useState(1)
  const [taskTotal, setTaskTotal] = useState(0)
```

Reset these when `id` changes:

```typescript
    setTaskPage(1)
    setTaskTotal(0)
```

Replace `fetchTasks` with:

```typescript
  const fetchTasks = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await getCrawlerRunTasks(id, {
        skip: (taskPage - 1) * pageSize,
        limit: pageSize,
        status: statusFilter,
        keyword: keyword || undefined,
      })
      setTasks(data.rows)
      setTaskTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [id, keyword, pageSize, statusFilter, taskPage])
```

Add handlers:

```typescript
  const handleStatusChange = useCallback((value: string | undefined) => {
    setStatusFilter(value)
    setTaskPage(1)
  }, [])

  const handleKeywordSearch = useCallback((value: string) => {
    setKeyword(value)
    setTaskPage(1)
  }, [])

  const handleTaskPageChange = useCallback((page: number, size: number) => {
    setTaskPage(page)
    setPageSize(size)
  }, [])
```

Return these names instead of exposing raw setters for table controls:

```typescript
    handleKeywordSearch,
    handleStatusChange,
    handleTaskPageChange,
    taskPage,
    taskTotal,
```

- [ ] **Step 5: Update realtime hook contract**

In `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`, add `fetchTasks` to the args type and destructuring:

```typescript
  fetchTasks: () => Promise<void>
```

Inside the detail update subscriber, replace the current `setTasks()` block with:

```typescript
        let needsRefresh = false
        setTasks((currentTasks) => {
          const byId = new Map(currentTasks.map((task) => [task.id, task]))
          const normalizedKeyword = keyword.trim().toLowerCase()
          for (const task of event.payload.tasks) {
            const wasPresent = byId.has(task.id)
            const matchesStatus = !statusFilter || task.status === statusFilter
            const matchesKeyword = !normalizedKeyword
              || (task.code ?? '').toLowerCase().includes(normalizedKeyword)
              || task.source_name.toLowerCase().includes(normalizedKeyword)
              || (task.source_url_name ?? '').toLowerCase().includes(normalizedKeyword)
            if (wasPresent && matchesStatus && matchesKeyword) {
              byId.set(task.id, task)
            } else if (wasPresent) {
              byId.delete(task.id)
              needsRefresh = true
            } else if (matchesStatus && matchesKeyword) {
              needsRefresh = true
            }
          }
          return Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
        })
        if (needsRefresh) {
          void fetchTasks()
        }
```

Add `fetchTasks` to the effect dependency list.

- [ ] **Step 6: Update `RunTaskTable` props and pagination**

In `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`, add props:

```typescript
  current: number
  total: number
  onPageChange: (page: number, size: number) => void
```

Add a source URL column after `来源`:

```tsx
    {
      title: 'URL来源',
      dataIndex: 'source_url_name',
      key: 'source_url_name',
      width: 140,
      ellipsis: true,
      render: (_, record) => record.source_url_name || record.task_url_type || '-',
    },
```

Replace the pagination block with:

```tsx
        pagination={{
          current,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100', '200'],
          showTotal: (count) => `共 ${count} 条`,
          onChange: onPageChange,
        }}
```

- [ ] **Step 7: Wire page props in `RunDetailPage`**

In `frontend/src/pages/crawler/runs/RunDetailPage.tsx`, pass `fetchTasks` to realtime:

```tsx
    fetchTasks: detail.fetchTasks,
```

Pass the table props:

```tsx
        current={detail.taskPage}
        onKeywordSearch={detail.handleKeywordSearch}
        onPageChange={detail.handleTaskPageChange}
        onStatusChange={detail.handleStatusChange}
        total={detail.taskTotal}
```

Remove old `onPageSizeChange={detail.setPageSize}`.

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/crawlerRun/types.ts frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts frontend/src/pages/crawler/runs/components/RunTaskTable.tsx frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
git commit -m "fix: paginate crawler run detail tasks"
```

---

### Task 5: Focused Regression Verification

**Files:**
- No new files.
- Verify files changed in Tasks 1-4.

**Interfaces:**
- Consumes all previous task deliverables.
- Produces verified backend and frontend behavior for the crawler multi-URL logs and paginated child task list feature.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_javdb_spider_multi_url.py tests/test_crawler_runs_api.py tests/test_crawler_run_logs.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend
npm test -- --run src/pages/crawler/runs
```

Expected: PASS.

- [ ] **Step 3: Run backend full test suite if focused tests pass**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/ -v
```

Expected: PASS. If unrelated pre-existing failures appear, record exact test names and failure messages before continuing.

- [ ] **Step 4: Run frontend build and lint**

Run:

```bash
cd frontend
npm run build
npm run lint
```

Expected: both commands exit 0.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended implementation files are modified or the working tree is clean after task commits.

- [ ] **Step 6: Commit verification-only adjustments if needed**

If Step 1-5 required small fixes, commit them:

```bash
git add backend frontend scraper
git commit -m "test: verify crawler multi-url detail pagination"
```

If no fixes were needed, do not create an empty commit.
