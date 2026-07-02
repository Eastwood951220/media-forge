# Crawler Run Save And Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix crawler run detail tasks so `saved` means the movie was actually persisted, and restore run logs in the run detail page with virtualized rendering instead of a fixed display-count cap.

**Architecture:** Backend runtime will persist crawled items through the existing PostgreSQL `MovieRepository` and `MovieMagnetRepository` before marking a detail task as `saved`; persistence failures become `save_failed` detail tasks with log entries. Run logs are JSONL files under `data/run_data/logs/crawler/runs`, loaded into the run detail API response as in the original `jav-scrapling` implementation, while the frontend renders them with a dedicated virtualized component.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pytest, React 19, TypeScript 6, Ant Design 6, Vitest, `@tanstack/react-virtual`.

---

## Context Notes

- Current `media-forge` bug source: `backend/app/modules/crawler/runtime/service.py` marks a detail task as `saved` in `on_item_saved`, but does not call `MovieRepository.upsert_movie()` or `MovieMagnetRepository.upsert_many()`.
- Current run detail API returns only `CrawlRun` fields; it has no `logs` field and no log-loading module.
- Original reference paths:
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/runs/RunDetail.tsx`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/frontend/src/features/crawler/runs/components/RunLogsTimeline.tsx`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/runs/logs.py`
  - `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/crawler/runs/queue.py`
- Virtualization choice: use `@tanstack/react-virtual`. Official TanStack docs describe it as a headless virtualizer and install the React adapter with `npm install @tanstack/react-virtual`: https://tanstack.com/virtual/latest/docs/installation
- This repository currently uses `frontend/package-lock.json` and `npm` scripts. Do not introduce `pnpm-lock.yaml` in this task unless the user separately requests a package-manager migration.

## File Structure

- Create `backend/app/modules/crawler/runs/logs.py`: crawler run JSONL log path, append, load, delete, and log-entry builder.
- Modify `backend/app/modules/crawler/runs/schemas.py`: add `RunLogEntry` and `logs` to `CrawlRunRead`.
- Modify `backend/app/modules/crawler/runs/router.py`: include `logs` for run detail and empty `logs` for list rows; import log loader.
- Modify `backend/app/modules/crawler/runtime/service.py`: persist items before `saved`, write run logs, and compute final result from detail-task statuses.
- Modify `backend/tests/test_crawler_runs_api.py`: assert run detail returns logs.
- Create `backend/tests/test_crawler_run_logs.py`: cover JSONL append/load/delete behavior.
- Modify `backend/tests/test_crawler_worker_service.py`: cover real movie persistence and save-failure status.
- Modify `frontend/package.json` and `frontend/package-lock.json`: add `@tanstack/react-virtual`.
- Modify `frontend/src/api/crawlerRun/types.ts`: add `RunLogEntry` and `logs` on `CrawlRun`.
- Create `frontend/src/pages/crawler/runs/components/RunLogsTimeline.tsx`: virtualized log list.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: render run logs and poll while active.
- Create `frontend/tests/crawler-run-detail.ui.test.tsx`: cover logs rendering and active empty state.

---

### Task 1: Backend Run JSONL Log Helpers

**Files:**
- Create: `backend/app/modules/crawler/runs/logs.py`
- Create: `backend/tests/test_crawler_run_logs.py`

- [ ] **Step 1: Write the failing log-helper tests**

Create `backend/tests/test_crawler_run_logs.py`:

```python
from backend.app.modules.crawler.runs import logs as run_logs


def test_run_logs_append_load_and_delete(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))

    entry = run_logs.build_run_log("INFO", "任务开始执行")
    run_logs.append_run_log("run-1", entry)

    loaded = run_logs.load_run_logs("run-1")
    assert loaded == [entry]

    assert run_logs.delete_run_logs("run-1") is True
    assert run_logs.load_run_logs("run-1") == []
    assert run_logs.delete_run_logs("run-1") is False


def test_run_log_entry_has_expected_shape() -> None:
    entry = run_logs.build_run_log("WARNING", "入库失败", code="AAA-001")

    assert entry["level"] == "WARNING"
    assert entry["message"] == "入库失败"
    assert entry["component"] == "crawler.run"
    assert entry["event"] == "run_log"
    assert entry["context"] == {"code": "AAA-001"}
    assert isinstance(entry["timestamp"], str)
```

- [ ] **Step 2: Run the log-helper tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_run_logs.py -v
```

Expected: FAIL with `ImportError` or `AttributeError` because `backend.app.modules.crawler.runs.logs` does not exist yet.

- [ ] **Step 3: Implement the run log helper module**

Create `backend/app/modules/crawler/runs/logs.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from scraper.config.settings import RUN_DATA_DIR
from shared.logging.jsonl import append_jsonl_log, build_log_entry, delete_jsonl_logs, load_jsonl_logs

RUN_LOG_DIR = str(RUN_DATA_DIR / "logs" / "crawler" / "runs")


def run_log_filename(run_id: str) -> str:
    return f"{run_id}.jsonl"


def build_run_log(level: str, message: str, **context: Any) -> dict[str, Any]:
    return build_log_entry(
        level=level,
        component="crawler.run",
        event="run_log",
        message=message,
        **context,
    )


def append_run_log(run_id: str, entry: dict[str, Any]) -> None:
    append_jsonl_log(RUN_LOG_DIR, run_log_filename(run_id), entry)


def load_run_logs(run_id: str) -> list[dict[str, Any]]:
    return load_jsonl_logs(RUN_LOG_DIR, run_log_filename(run_id))


def delete_run_logs(run_id: str) -> bool:
    path = Path(RUN_LOG_DIR) / run_log_filename(run_id)
    existed = path.exists()
    delete_jsonl_logs(RUN_LOG_DIR, run_log_filename(run_id))
    return existed
```

- [ ] **Step 4: Run the log-helper tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_run_logs.py -v
```

Expected: PASS, 2 tests passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runs/logs.py backend/tests/test_crawler_run_logs.py
git commit -m "feat: add crawler run jsonl logs"
```

---

### Task 2: Include Logs In Run Detail API

**Files:**
- Modify: `backend/app/modules/crawler/runs/schemas.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Modify: `backend/tests/test_crawler_runs_api.py`

- [ ] **Step 1: Write the failing API test**

Modify `backend/tests/test_crawler_runs_api.py`:

1. Add this import near the existing imports:

```python
from backend.app.modules.crawler.runs.logs import append_run_log, build_run_log
```

2. Add this test after `test_run_list_and_detail_endpoints`:

```python
def test_run_detail_includes_jsonl_logs(client: TestClient, admin_user, monkeypatch, tmp_path) -> None:
    from backend.app.modules.crawler.runs import logs as run_logs

    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.commit()
    run_id = str(run.id)

    append_run_log(run_id, build_run_log("INFO", "任务开始执行"))
    append_run_log(run_id, build_run_log("ERROR", "入库失败", code="AAA-001"))

    response = client.get(f"/api/crawler/runs/{run_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()["data"]
    assert body["id"] == run_id
    assert [entry["message"] for entry in body["logs"]] == ["任务开始执行", "入库失败"]
    assert body["logs"][1]["context"] == {"code": "AAA-001"}
```

- [ ] **Step 2: Run the API test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_run_detail_includes_jsonl_logs -v
```

Expected: FAIL because `body["logs"]` is missing.

- [ ] **Step 3: Add log types to backend schemas**

Modify `backend/app/modules/crawler/runs/schemas.py`:

1. Add this class after `RunCreateRequest`:

```python
class RunLogEntry(BaseModel):
    timestamp: datetime
    level: str
    component: str | None = None
    event: str | None = None
    message: str
    context: dict[str, Any] = {}
```

2. Add this field to `CrawlRunRead`:

```python
    logs: list[RunLogEntry] = []
```

- [ ] **Step 4: Load logs in the runs router**

Modify `backend/app/modules/crawler/runs/router.py`:

1. Add this import:

```python
from backend.app.modules.crawler.runs.logs import load_run_logs
```

2. In `list_runs`, replace the `rows=[...]` expression with this code before `return paginated(...)`:

```python
    payload_rows = []
    for row in rows:
        payload = CrawlRunRead.model_validate(row).model_dump(mode="json")
        payload["logs"] = []
        payload_rows.append(payload)
```

Then return:

```python
    return paginated(rows=payload_rows, total=total)
```

3. In `get_run`, replace the return line with:

```python
    payload = CrawlRunRead.model_validate(run).model_dump(mode="json")
    payload["logs"] = load_run_logs(str(run_id))
    return success(data=payload)
```

- [ ] **Step 5: Run the API test and verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_run_detail_includes_jsonl_logs -v
```

Expected: PASS.

- [ ] **Step 6: Run the crawler run API suite**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -v
```

Expected: PASS for all tests in `test_crawler_runs_api.py`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runs/schemas.py backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: expose crawler run logs"
```

---

### Task 3: Persist Movies Before Marking Detail Tasks Saved

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Write failing worker persistence tests**

Modify `backend/tests/test_crawler_worker_service.py`:

1. Add these imports:

```python
from sqlalchemy import select

from shared.database.models.content import Movie, MovieMagnet
```

2. Add these stub classes after `MovieServiceStub`:

```python
class PersistingMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-002", "url": "https://javdb.com/v/aaa002", "name": "AAA 002"}
        ])
        kwargs["on_item_saved"](
            {"code": "AAA-002", "url": "https://javdb.com/v/aaa002", "name": "AAA 002"},
            {
                "code": "AAA-002",
                "source_url": "https://javdb.com/v/aaa002",
                "source_name": "AAA 002",
                "source_task_name": [task.name],
                "title": "AAA 002",
                "magnets": [
                    {
                        "magnet": "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "name": "AAA 002",
                        "size_text": "1.2GB",
                    }
                ],
            },
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


class FailingPersistenceMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-003", "url": "https://javdb.com/v/aaa003", "name": "AAA 003"}
        ])
        kwargs["on_item_saved"](
            {"code": "AAA-003", "url": "https://javdb.com/v/aaa003", "name": "AAA 003"},
            {
                "code": "AAA-003",
                "source_url": "https://javdb.com/v/aaa003",
                "source_name": "AAA 003",
                "source_task_name": [task.name],
            },
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}
```

3. Add this helper after the stubs:

```python
def create_run_with_task(code: str = "task-code") -> tuple[CrawlRun, Runtime]:
    session = TestingSessionLocal()
    user = User(username=f"worker-{code}", hashed_password=get_password_hash("pw"), role="admin")
    session.add(user)
    session.flush()
    task = CrawlTask(name=f"任务-{code}", owner_id=user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(
            position=0,
            url="https://javdb.com/actors/a",
            url_type="actors",
            final_url="https://javdb.com/actors/a?page=1",
            source="javdb",
        )
    ]
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="queued", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.commit()
    runtime = Runtime(str(run.id))
    return run, runtime
```

4. Add these tests at the end of the file:

```python
def test_execute_run_persists_movie_before_marking_detail_saved(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: PersistingMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("persist")

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    movie = session.scalar(select(Movie).where(Movie.code == "AAA-002"))
    assert movie is not None
    assert movie.source_url == "https://javdb.com/v/aaa002"
    assert movie.source_task_names == [run.task_name]
    magnets = session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie.id)).all()
    assert len(magnets) == 1

    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-002").one()
    assert detail.status == "saved"
    assert detail.saved_at is not None
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["saved"] == 1
    assert refreshed.result["save_failed"] == 0


def test_execute_run_marks_detail_save_failed_when_movie_persistence_fails(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run
    from scraper.database.repositories.movie_repository import MovieRepository

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: FailingPersistenceMovieServiceStub())
    monkeypatch.setattr(MovieRepository, "upsert_movie", lambda self, item: None)
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("save-failed")

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    assert session.scalar(select(Movie).where(Movie.code == "AAA-003")) is None
    detail = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.code == "AAA-003").one()
    assert detail.status == "save_failed"
    assert "movie repository returned no id" in detail.error
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.result["saved"] == 0
    assert refreshed.result["save_failed"] == 1
```

- [ ] **Step 2: Run the new worker tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_persists_movie_before_marking_detail_saved backend/tests/test_crawler_worker_service.py::test_execute_run_marks_detail_save_failed_when_movie_persistence_fails -v
```

Expected: FAIL because no movie is persisted and persistence failure does not produce `save_failed`.

- [ ] **Step 3: Add persistence and logging helpers to runtime service**

Modify `backend/app/modules/crawler/runtime/service.py`.

1. Add this import near the SQLAlchemy imports:

```python
from sqlalchemy import func
```

2. Add these helper functions above `_execute_run`:

```python
def _append_run_log(run_id: str, message: str, level: str = "INFO", **context: Any) -> None:
    from backend.app.modules.crawler.runs.logs import append_run_log, build_run_log

    try:
        append_run_log(run_id, build_run_log(level, message, **context))
    except Exception as exc:
        logger.warning("Failed to append crawler run log for %s: %s", run_id, exc)


def _persist_crawled_item(db: Session, item_data: dict[str, Any]) -> uuid.UUID:
    from scraper.database.repositories.movie_magnet_repository import MovieMagnetRepository
    from scraper.database.repositories.movie_repository import MovieRepository

    movie_doc = dict(item_data)
    magnets = movie_doc.pop("magnets", []) or []
    repository = MovieRepository(session=db)
    magnet_repository = MovieMagnetRepository(session=db)
    movie_id = repository.upsert_movie(movie_doc)
    if movie_id is None:
        raise RuntimeError("movie repository returned no id")

    if magnets:
        magnet_repository.upsert_many(movie_id, movie_doc, magnets)
        magnet_repository.auto_select_best_magnet(str(movie_id))

    return movie_id


def _count_run_detail_tasks(db: Session, run_id: uuid.UUID, status: str | None = None) -> int:
    query = db.query(func.count(CrawlRunDetailTask.id)).filter(CrawlRunDetailTask.run_id == run_id)
    if status is not None:
        query = query.filter(CrawlRunDetailTask.status == status)
    return int(query.scalar() or 0)
```

- [ ] **Step 4: Replace `_execute_run` callback internals**

In `_execute_run`, replace the progress/detail callback block with this implementation pattern:

```python
    progress = {"total": 0, "saved": 0, "failed": 0, "skipped": 0, "save_failed": 0}
    detail_tasks_by_code: dict[str, CrawlRunDetailTask] = {}
    detail_tasks_by_source_url: dict[str, CrawlRunDetailTask] = {}

    def remember_detail(detail: CrawlRunDetailTask) -> None:
        if detail.code:
            detail_tasks_by_code[detail.code] = detail
        if detail.source_url:
            detail_tasks_by_source_url[detail.source_url] = detail

    def find_detail(task_info: dict[str, Any], item_data: dict[str, Any] | None = None) -> CrawlRunDetailTask | None:
        item_data = item_data or {}
        code = item_data.get("code") or task_info.get("code")
        source_url = task_info.get("url") or task_info.get("source_url") or item_data.get("source_url")
        if code and code in detail_tasks_by_code:
            return detail_tasks_by_code[code]
        if source_url and source_url in detail_tasks_by_source_url:
            return detail_tasks_by_source_url[source_url]
        return None

    def on_tasks_batch_created(items: list[dict[str, Any]]) -> None:
        for item in items:
            detail = CrawlRunDetailTask(
                run_id=run.id,
                task_name=task.name,
                code=item.get("code"),
                source_url=item.get("url", ""),
                source_name=item.get("name", ""),
                status="pending_crawl",
                created_at=datetime.now(),
            )
            db.add(detail)
            db.flush()
            remember_detail(detail)
        progress["total"] += len(items)
        runtime.write_progress(str(run.id), progress)
        db.commit()
        if items:
            _append_run_log(str(run.id), f"创建子任务 {len(items)} 条")

    def on_item_saved(task_info: dict[str, Any], item_data: dict[str, Any]) -> None:
        detail = find_detail(task_info, item_data)
        code = item_data.get("code") or task_info.get("code") or "-"
        try:
            movie_id = _persist_crawled_item(db, item_data)
            if detail:
                detail.status = "saved"
                detail.item_data = item_data
                detail.error = None
                detail.crawled_at = datetime.now()
                detail.saved_at = datetime.now()
            progress["saved"] += 1
            _append_run_log(str(run.id), f"入库成功: {code}", "INFO", code=code, movie_id=str(movie_id))
        except Exception as exc:
            if detail:
                detail.status = "save_failed"
                detail.item_data = item_data
                detail.error = str(exc)[:500]
                detail.crawled_at = datetime.now()
                detail.saved_at = None
            progress["save_failed"] += 1
            _append_run_log(str(run.id), f"入库失败: {code}: {exc}", "ERROR", code=code)
        runtime.write_progress(str(run.id), progress)
        db.commit()

    def on_detail_failed(task_info: dict[str, Any], error: str) -> None:
        detail = find_detail(task_info)
        if detail:
            detail.status = "crawl_failed"
            detail.error = error[:500]
            detail.crawled_at = datetime.now()
        progress["failed"] += 1
        runtime.write_progress(str(run.id), progress)
        db.commit()
        _append_run_log(str(run.id), f"爬取失败: {task_info.get('code') or task_info.get('url')}: {error}", "ERROR")

    def log_callback(message: str, level: str = "INFO") -> None:
        _append_run_log(str(run.id), message, level)
```

Then pass `log_callback=log_callback` into `movie_service.crawl_javdb_task(...)`.

- [ ] **Step 5: Compute final result from database detail statuses**

Near the end of `_execute_run`, after `result = movie_service.crawl_javdb_task(...)`, replace `run.result = result` with:

```python
        total_count = _count_run_detail_tasks(db, run.id)
        saved_count = _count_run_detail_tasks(db, run.id, "saved")
        save_failed_count = _count_run_detail_tasks(db, run.id, "save_failed")
        crawl_failed_count = _count_run_detail_tasks(db, run.id, "crawl_failed")
        run.result = {
            **(result or {}),
            "total_tasks": total_count,
            "saved": saved_count,
            "save_failed": save_failed_count,
            "crawl_failed": crawl_failed_count,
        }
        run.status = "completed"
        _append_run_log(
            str(run.id),
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}",
            "INFO",
        )
```

In the `except ImportError` branch, also call:

```python
        _append_run_log(str(run.id), "MovieService 不可用，使用空结果完成运行", "WARNING")
```

- [ ] **Step 6: Run the worker tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS for all worker service tests.

- [ ] **Step 7: Run backend crawler tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_run_logs.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: persist crawler items before saved status"
```

---

### Task 4: Frontend API Types And Virtual Log Component

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/api/crawlerRun/types.ts`
- Create: `frontend/src/pages/crawler/runs/components/RunLogsTimeline.tsx`
- Create: `frontend/tests/crawler-run-detail.ui.test.tsx`

- [ ] **Step 1: Add the virtualization dependency**

Run:

```bash
cd frontend
npm install @tanstack/react-virtual
```

Expected: `frontend/package.json` and `frontend/package-lock.json` include `@tanstack/react-virtual`.

- [ ] **Step 2: Add run log types**

Modify `frontend/src/api/crawlerRun/types.ts`:

1. Add this interface above `CrawlRun`:

```ts
export interface RunLogEntry {
  timestamp: string
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | string
  component?: string | null
  event?: string | null
  message: string
  context?: Record<string, unknown>
}
```

2. Add this field to `CrawlRun`:

```ts
  logs: RunLogEntry[]
```

- [ ] **Step 3: Create the virtualized log component**

Create `frontend/src/pages/crawler/runs/components/RunLogsTimeline.tsx`:

```tsx
import { useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Empty, Tag, Typography } from 'antd'
import type { RunLogEntry } from '@/api/crawlerRun/types'

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'processing',
  WARNING: 'warning',
  ERROR: 'error',
}

interface RunLogsTimelineProps {
  logs: RunLogEntry[]
  isActive: boolean
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}

function RunLogsTimeline({ logs, isActive }: RunLogsTimelineProps) {
  const parentRef = useRef<HTMLDivElement | null>(null)
  const orderedLogs = useMemo(() => logs.slice().reverse(), [logs])
  const virtualizer = useVirtualizer({
    count: orderedLogs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 10,
  })

  if (orderedLogs.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={isActive ? '等待日志...' : '无日志'}
      />
    )
  }

  return (
    <div
      ref={parentRef}
      role="list"
      aria-label="运行日志"
      style={{ height: 500, overflow: 'auto', paddingRight: 8 }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const entry = orderedLogs[virtualRow.index]
          return (
            <div
              key={`${entry.timestamp}-${virtualRow.index}`}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
              role="listitem"
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                display: 'grid',
                gridTemplateColumns: '88px 88px minmax(0, 1fr)',
                gap: 8,
                alignItems: 'start',
                minHeight: 40,
                padding: '6px 0',
                borderBottom: '1px solid rgba(5, 5, 5, 0.06)',
              }}
            >
              <Typography.Text type="secondary" style={{ fontSize: 12, lineHeight: '24px' }}>
                {formatTime(entry.timestamp)}
              </Typography.Text>
              <Tag color={levelColors[entry.level] || 'default'} style={{ width: 78, textAlign: 'center', marginInlineEnd: 0 }}>
                {entry.level}
              </Tag>
              <Typography.Text
                type={entry.level === 'ERROR' ? 'danger' : undefined}
                style={{ wordBreak: 'break-word' }}
              >
                {entry.message}
              </Typography.Text>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default RunLogsTimeline
```

- [ ] **Step 4: Write the frontend detail test**

Create `frontend/tests/crawler-run-detail.ui.test.tsx`:

```tsx
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunDetailPage from '../src/pages/crawler/runs/RunDetailPage'
import { getCrawlerRun, getCrawlerRunTasks } from '../src/api/crawlerRun'

vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))

function renderDetailPage() {
  const rootRoute = createRootRoute({ component: () => <RunDetailPage /> })
  const detailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs/$id',
    component: RunDetailPage,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([detailRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/runs/run-1'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('RunDetailPage logs', () => {
  beforeEach(() => {
    vi.mocked(getCrawlerRun).mockResolvedValue({
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: '2026-07-02T00:00:00Z',
      started_at: '2026-07-02T00:00:01Z',
      finished_at: '2026-07-02T00:00:02Z',
      result: { saved: 1 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: null,
      logs: [
        { timestamp: '2026-07-02T00:00:01Z', level: 'INFO', message: '任务开始执行' },
        { timestamp: '2026-07-02T00:00:02Z', level: 'ERROR', message: '入库失败: AAA-001' },
      ],
    })
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({ rows: [], total: 0 })
  })

  it('renders run logs on the detail page', async () => {
    renderDetailPage()

    expect(await screen.findByText('运行日志')).toBeInTheDocument()
    expect(await screen.findByText('入库失败: AAA-001')).toBeInTheDocument()
    expect(screen.getByText('任务开始执行')).toBeInTheDocument()
  })

  it('passes the route id to run detail APIs', async () => {
    renderDetailPage()

    await screen.findByText('运行日志')
    expect(getCrawlerRun).toHaveBeenCalledWith('run-1')
    expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
      limit: 200,
      status: undefined,
      keyword: undefined,
    })
  })
})
```

- [ ] **Step 5: Run the new frontend test and verify it fails before page integration**

Run:

```bash
cd frontend
npm test -- crawler-run-detail.ui.test.tsx
```

Expected: FAIL because `RunDetailPage` does not render `运行日志` yet.

- [ ] **Step 6: Commit dependency, types, component, and failing test**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/api/crawlerRun/types.ts frontend/src/pages/crawler/runs/components/RunLogsTimeline.tsx frontend/tests/crawler-run-detail.ui.test.tsx
git commit -m "feat: add virtualized crawler run logs component"
```

---

### Task 5: Integrate Logs Into Run Detail Page

**Files:**
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Modify: `frontend/tests/crawler-run-detail.ui.test.tsx`

- [ ] **Step 1: Import the logs component**

Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`:

```tsx
import { Card, Descriptions, Input, Select, Space, Table, Tag } from 'antd'
import RunLogsTimeline from './components/RunLogsTimeline'
```

Keep the existing Ant Design import as a single import line, adding no duplicate `Card` import.

- [ ] **Step 2: Render the logs card below the subtask table**

In `RunDetailPage.tsx`, after the closing `</Card>` for `子任务列表`, add:

```tsx
      {run && (
        <Card title="运行日志" style={{ marginTop: 16 }}>
          <RunLogsTimeline
            logs={run.logs ?? []}
            isActive={run.status === 'queued' || run.status === 'running'}
          />
        </Card>
      )}
```

- [ ] **Step 3: Poll run detail while the run is active**

In `RunDetailPage.tsx`, add this effect after the existing effect that fetches the run:

```tsx
  useEffect(() => {
    if (!id || !run || (run.status !== 'queued' && run.status !== 'running')) return

    const timer = window.setInterval(() => {
      void getCrawlerRun(id).then(setRun)
    }, 3000)

    return () => window.clearInterval(timer)
  }, [id, run])
```

- [ ] **Step 4: Ensure run logs always have a default array in tests**

In `frontend/tests/crawler-runs.ui.test.tsx`, add `logs: []` to the mocked run object:

```tsx
        logs: [],
```

- [ ] **Step 5: Run the detail test and verify it passes**

Run:

```bash
cd frontend
npm test -- crawler-run-detail.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Run crawler frontend tests**

Run:

```bash
cd frontend
npm test -- crawler-runs.ui.test.tsx crawler-run-controls.ui.test.tsx crawler-run-detail.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/tests/crawler-runs.ui.test.tsx frontend/tests/crawler-run-detail.ui.test.tsx
git commit -m "feat: show virtualized run logs in detail"
```

---

### Task 6: Full Verification

**Files:**
- No code changes unless verification exposes a defect.

- [ ] **Step 1: Run backend verification**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_run_logs.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
npm test -- crawler-runs.ui.test.tsx crawler-run-controls.ui.test.tsx crawler-run-detail.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS with TypeScript and Vite build completing successfully.

- [ ] **Step 4: Manual runtime check**

Run backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Run frontend in a second terminal:

```bash
cd frontend
npm run dev
```

Expected:

- Open a crawler run detail page.
- Run detail displays `运行日志`.
- Running/queued runs update logs every 3 seconds.
- A detail task is marked `saved` only when a corresponding row exists in the `movies` table.
- If movie persistence returns no id or raises, the detail task is `save_failed` and the run logs contain an `ERROR` entry.

- [ ] **Step 5: Handle verification fixes if any were needed**

If verification exposes a defect, return to the task that introduced the defect, update that task's exact file list, rerun the failing command, then rerun this full verification task. If no fixes were needed, do not create an empty commit.

---

## Self-Review

- Spec coverage:
  - Fixes false `saved` display by persisting movies before updating detail status in Task 3.
  - Restores crawler run logs from the original project through JSONL helpers and API response in Tasks 1 and 2.
  - Replaces the old max-display-count log rendering pattern with a virtualized log component in Task 4.
  - Keeps scope anchored to `jav-scrapling` behavior and does not add unrelated crawler features.
- Placeholder scan:
  - No forbidden placeholder terms, no open-ended error handling instructions, and all code-changing steps include concrete code.
- Type consistency:
  - Backend `RunLogEntry` and frontend `RunLogEntry` both use `timestamp`, `level`, `message`, optional `component`, optional `event`, and `context`.
  - Frontend `CrawlRun.logs` is used by `RunDetailPage` and `RunLogsTimeline`.
  - Backend `save_failed` status already exists in `DetailTaskStatus` and is reused consistently.
