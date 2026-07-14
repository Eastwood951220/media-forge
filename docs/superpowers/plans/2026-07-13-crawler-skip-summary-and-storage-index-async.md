# Crawler Skip Summary And Storage Index Async Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide incremental `already_exists` skipped crawler items from run child-task lists and visible counts, keep realtime summary totals fresh, and make movie-list storage index refresh start asynchronously with correct success/running/failure messages.

**Architecture:** Keep existing crawl detail rows and realtime events, but stop persisting incremental list-phase `already_exists` rows in the threaded list phase and hide legacy rows at the crawler-runs API boundary. Add a small frontend summary updater so inline realtime task patches refresh the metric tiles, not only row statuses. Convert storage-index refresh into a guarded background thread with metadata-based running detection and a start response that the movie list renders as “任务启动成功 / 任务正在进行中 / 启动失败”.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, Vitest 3, React Testing Library.

## Global Constraints

- Project scope remains the Media Forge refactor and optimization of `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.
- Do not introduce new crawler detail statuses.
- Do not show incremental `already_exists` skipped rows in the run child-task list, including rows left by older runs.
- Do not count hidden incremental `already_exists` skipped rows in the child-task table total or metric tiles.
- Do not turn movie-list storage index refresh into a blocking request.
- If storage index refresh starts successfully, the UI message is task-start success, not completion.
- If a storage index refresh is already running, the UI message says the task is still running.
- Other storage-index refresh errors show startup failure.

---

## File Structure

- Modify `backend/app/modules/crawler/runtime/threaded.py`
  - Filter incremental list-phase `already_exists` skipped items before `upsert_detail_task()`.
- Modify `backend/app/modules/crawler/runs/router.py`
  - Hide legacy incremental `already_exists` skipped rows from `/api/crawler/runs/{run_id}/tasks`.
  - Exclude those rows from `_run_task_summary()`.
- Modify `backend/tests/test_crawler_threaded_url_completion_refresh.py`
  - Add regression coverage that incremental skipped existing items are not persisted.
- Modify `backend/tests/test_crawler_runs_api.py`
  - Add API coverage that legacy hidden skipped rows do not appear or count.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
  - Expose `setTaskSummary` and `setTaskTotal`.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
  - Update summary and total after inline `crawler.run.detail.updated` task patches.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
  - Pass the new setters into the realtime hook.
- Modify `frontend/tests/run-detail-realtime.ui.test.tsx`
  - Add regression coverage for metric refresh on realtime task status updates.
- Modify `backend/app/modules/storage/index/router.py`
  - Start index refresh in a background thread and return a start envelope.
  - Reject concurrent refresh with HTTP 409.
- Create `backend/app/modules/storage/index/background.py`
  - Own the in-process refresh lock and background worker function.
- Modify `backend/tests/test_storage_index_api.py`
  - Add async-start, already-running, and startup-failure API tests.
- Modify `frontend/src/api/storage/storageIndex/types.ts`
  - Add `StorageIndexRefreshStartResult`.
- Modify `frontend/src/api/storage/storageIndex/index.ts`
  - Make `refreshStorageIndex()` return the start result.
- Modify `frontend/src/pages/content/movies/MovieListPage.tsx`
  - Show start/running/failure messages for storage index actions.
- Modify `frontend/tests/movie-list.ui.test.tsx`
  - Add UI coverage for the new messages.

---

### Task 1: Hide Incremental Existing-Skip Rows At Persistence And API Boundaries

**Files:**
- Modify: `backend/app/modules/crawler/runtime/threaded.py:175-193`
- Modify: `backend/app/modules/crawler/runs/router.py:15-106`
- Test: `backend/tests/test_crawler_threaded_url_completion_refresh.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Produces: `_hidden_incremental_existing_skip_filter(run: CrawlRun)`
- Produces: `_visible_run_detail_task_query(db: Session, run: CrawlRun)`
- Preserves: `GET /api/crawler/runs/{run_id}/tasks` response shape: `rows`, `total`, `summary`.

- [ ] **Step 1: Add threaded persistence regression test**

Append to `backend/tests/test_crawler_threaded_url_completion_refresh.py`:

```python
def test_threaded_incremental_list_phase_does_not_persist_already_exists_skips(admin_user, monkeypatch) -> None:
    from backend.app.models.crawl_run import CrawlRunDetailTask

    session = TestingSessionLocal()
    task = CrawlTask(name="任务-skip-hide", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    session.add(CrawlTaskUrl(
        task_id=task.id,
        position=1,
        url="https://example.test/list-1",
        url_type="list",
        has_magnet=True,
        has_chinese_sub=False,
        sort_type=0,
        source="javdb",
        final_url="https://example.test/list-1?page=1",
        url_name="入口1",
    ))
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(task)
    session.refresh(run)

    class SkipSpider:
        def collect_detail_tasks_for_url(self, **kwargs):
            return [
                {
                    "code": "OLD-001",
                    "url": "https://javdb.com/v/old001",
                    "name": "Old Movie",
                    "status": "skipped",
                    "reason": "already_exists",
                    "_task_url_name": "入口1",
                    "_task_url": "https://example.test/list-1",
                    "_task_final_url": "https://example.test/list-1?page=1",
                    "_task_url_type": "list",
                },
                {
                    "code": "NEW-001",
                    "url": "https://javdb.com/v/new001",
                    "name": "New Movie",
                    "_task_url_name": "入口1",
                    "_task_url": "https://example.test/list-1",
                    "_task_final_url": "https://example.test/list-1?page=1",
                    "_task_url_type": "list",
                },
            ]

    monkeypatch.setattr(threaded, "build_spider", lambda: SkipSpider())
    monkeypatch.setattr(threaded, "_find_existing_movie_codes_in_worker_session", lambda *args, **kwargs: {"OLD-001"})

    try:
        threaded._run_list_phase(session, run, task, FakeRuntime(), FakeConfig())
        rows = session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    finally:
        session.close()

    assert [row.code for row in rows] == ["NEW-001"]
```

- [ ] **Step 2: Run the threaded test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py::test_threaded_incremental_list_phase_does_not_persist_already_exists_skips -v
```

Expected: FAIL because `_run_list_phase()` currently upserts every returned item, including skipped `already_exists` rows.

- [ ] **Step 3: Filter skipped existing items before persistence**

In `backend/app/modules/crawler/runtime/threaded.py`, add this helper near `_run_list_phase()`:

```python
def _should_persist_list_item(run: CrawlRun, item: dict[str, Any]) -> bool:
    if run.crawl_mode != "incremental":
        return True
    return not (item.get("status") == "skipped" and item.get("reason") == "already_exists")
```

Then replace the persistence loop in `_run_list_phase()`:

```python
                for item in future.result():
                    upsert_detail_task(db, run=run, task_name=task_name, item=item)
```

with:

```python
                for item in future.result():
                    if not _should_persist_list_item(run, item):
                        continue
                    upsert_detail_task(db, run=run, task_name=task_name, item=item)
```

- [ ] **Step 4: Run the threaded regression test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py::test_threaded_incremental_list_phase_does_not_persist_already_exists_skips -v
```

Expected: PASS.

- [ ] **Step 5: Add API regression test for legacy hidden rows**

Append to `backend/tests/test_crawler_runs_api.py`:

```python
def test_incremental_run_tasks_hide_legacy_already_exists_skips(client, admin_user, db_session, monkeypatch) -> None:
    from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
    from backend.app.models.crawl_task import CrawlTask

    task = CrawlTask(name="任务-hide-legacy", owner_id=admin_user.id)
    db_session.add(task)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="incremental")
    db_session.add(run)
    db_session.flush()
    db_session.add_all([
        CrawlRunDetailTask(
            run_id=run.id,
            task_name=task.name,
            code="OLD-001",
            source_url="https://javdb.com/v/old001",
            source_name="Old Movie",
            status="skipped",
            error="already_exists",
            created_at=datetime.now(),
        ),
        CrawlRunDetailTask(
            run_id=run.id,
            task_name=task.name,
            code="NEW-001",
            source_url="https://javdb.com/v/new001",
            source_name="New Movie",
            status="pending_crawl",
            error=None,
            created_at=datetime.now(),
        ),
    ])
    db_session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=auth_headers(client, admin_user))

    assert response.status_code == 200
    payload = response.json()
    assert [row["code"] for row in payload["rows"]] == ["NEW-001"]
    assert payload["total"] == 1
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["skipped"] == 0
    assert payload["summary"]["waiting"] == 1
```

- [ ] **Step 6: Run the API regression test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_incremental_run_tasks_hide_legacy_already_exists_skips -v
```

Expected: FAIL because the API currently returns and counts the skipped row.

- [ ] **Step 7: Add visible-detail query helpers**

In `backend/app/modules/crawler/runs/router.py`, add below the router declaration:

```python
def _hidden_incremental_existing_skip_filter(run: CrawlRun):
    if run.crawl_mode != "incremental":
        return None
    return ~(
        (CrawlRunDetailTask.status == "skipped")
        & (CrawlRunDetailTask.error == "already_exists")
    )


def _visible_run_detail_task_query(db: Session, run: CrawlRun):
    query = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id)
    hidden_filter = _hidden_incremental_existing_skip_filter(run)
    if hidden_filter is not None:
        query = query.filter(hidden_filter)
    return query
```

Update `_run_task_summary()` signature:

```python
def _run_task_summary(db: Session, run: CrawlRun) -> dict:
```

Replace its query start with:

```python
    rows = (
        _visible_run_detail_task_query(db, run)
        .with_entities(CrawlRunDetailTask.status, func.count(CrawlRunDetailTask.id))
        .group_by(CrawlRunDetailTask.status)
        .all()
    )
```

In `list_run_tasks()`, replace:

```python
    query = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run_id)
```

with:

```python
    query = _visible_run_detail_task_query(db, run)
```

And replace:

```python
    payload["summary"] = _run_task_summary(db, run_id)
```

with:

```python
    payload["summary"] = _run_task_summary(db, run)
```

- [ ] **Step 8: Run backend crawler tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py backend/tests/test_crawler_runs_api.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/crawler/runtime/threaded.py backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_threaded_url_completion_refresh.py backend/tests/test_crawler_runs_api.py
git commit -m "fix: hide incremental existing crawler skips"
```

---

### Task 2: Refresh Run Detail Summary Metrics On Realtime Task Updates

**Files:**
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Test: `frontend/tests/run-detail-realtime.ui.test.tsx`

**Interfaces:**
- Consumes: `CrawlerRunDetailUpdatedPayload.tasks: CrawlRunDetailTask[]`
- Produces: realtime hook args:
  - `setTaskSummary: React.Dispatch<React.SetStateAction<RunTaskSummary>>`
  - `setTaskTotal: React.Dispatch<React.SetStateAction<number>>`

- [ ] **Step 1: Add frontend regression test**

Append to `frontend/tests/run-detail-realtime.ui.test.tsx`:

```tsx
  it('updates summary metrics when realtime detail task status changes inline', async () => {
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [{
        id: 'detail-1',
        run_id: 'run-1',
        task_name: '任务A',
        code: 'AAA-001',
        source_url: 'https://javdb.com/v/aaa001',
        source_name: 'AAA 001',
        source_url_name: '入口1',
        task_url: 'https://example.test/list',
        task_final_url: 'https://example.test/list?page=1',
        task_url_type: 'list',
        status: 'pending_crawl',
        error: null,
        item_data: null,
        created_at: '2026-07-03T00:00:00Z',
        crawled_at: null,
        saved_at: null,
      }],
      total: 1,
      summary: {
        total: 1,
        pending_crawl: 1,
        crawling: 0,
        saved: 0,
        skipped: 0,
        crawl_failed: 0,
        save_failed: 0,
        completed: 0,
        waiting: 1,
        failed: 0,
      },
    })

    renderPage()

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    expect(screen.getByText('等待').nextElementSibling?.textContent).toContain('1')

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [{
        id: 'detail-1',
        run_id: 'run-1',
        task_name: '任务A',
        code: 'AAA-001',
        source_url: 'https://javdb.com/v/aaa001',
        source_name: 'AAA 001',
        source_url_name: '入口1',
        task_url: 'https://example.test/list',
        task_final_url: 'https://example.test/list?page=1',
        task_url_type: 'list',
        status: 'saved',
        error: null,
        item_data: null,
        created_at: '2026-07-03T00:00:00Z',
        crawled_at: '2026-07-03T00:01:00Z',
        saved_at: '2026-07-03T00:01:00Z',
      }],
    })

    await waitFor(() => {
      expect(screen.getByText('完成').nextElementSibling?.textContent).toContain('1')
      expect(screen.getByText('等待').nextElementSibling?.textContent).toContain('0')
    })
  })
```

- [ ] **Step 2: Run the regression test to verify it fails**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: FAIL because inline realtime patches update table rows but do not update `taskSummary`.

- [ ] **Step 3: Expose summary setters from `useRunDetail()`**

In `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`, add these to the returned object:

```ts
    setTaskSummary,
    setTaskTotal,
```

- [ ] **Step 4: Add summary recomputation helper**

In `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`, update imports:

```ts
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry, RunTaskSummary } from '@/api/crawlerRun/types'
```

Add above `useRunDetailRealtime()`:

```ts
const emptyTaskSummary: RunTaskSummary = {
  total: 0,
  pending_crawl: 0,
  crawling: 0,
  saved: 0,
  skipped: 0,
  crawl_failed: 0,
  save_failed: 0,
  completed: 0,
  waiting: 0,
  failed: 0,
}

function buildSummary(tasks: CrawlRunDetailTask[], fallbackTotal: number): RunTaskSummary {
  const summary = { ...emptyTaskSummary, total: Math.max(fallbackTotal, tasks.length) }
  for (const task of tasks) {
    if (task.status in summary) {
      summary[task.status as keyof RunTaskSummary] += 1
    }
  }
  summary.completed = summary.saved + summary.skipped
  summary.waiting = summary.pending_crawl + summary.crawling
  summary.failed = summary.crawl_failed + summary.save_failed
  return summary
}
```

Update hook args type:

```ts
  setTaskSummary: React.Dispatch<React.SetStateAction<RunTaskSummary>>
  setTaskTotal: React.Dispatch<React.SetStateAction<number>>
```

Destructure them:

```ts
  const { id, fetchLogs, fetchRun, fetchTasks, keyword, resyncSnapshot, setLogs, setRun, setTaskSummary, setTaskTotal, setTasks, statusFilter } = args
```

Inside the `setTasks()` callback, before returning, assign the sorted tasks:

```ts
          const nextTasks = Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
          setTaskTotal((currentTotal) => Math.max(currentTotal, nextTasks.length))
          setTaskSummary((currentSummary) => buildSummary(nextTasks, currentSummary.total))
          return nextTasks
```

Replace the existing direct `return Array.from(...).sort(...)` with that block.

- [ ] **Step 5: Pass summary setters from page**

In `frontend/src/pages/crawler/runs/RunDetailPage.tsx`, add props to `useRunDetailRealtime()`:

```tsx
    setTaskSummary: detail.setTaskSummary,
    setTaskTotal: detail.setTaskTotal,
```

- [ ] **Step 6: Run frontend realtime tests**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "fix: refresh crawler detail metrics from realtime"
```

---

### Task 3: Make Movie-List Storage Index Refresh Asynchronous With Correct Messages

**Files:**
- Create: `backend/app/modules/storage/index/background.py`
- Modify: `backend/app/modules/storage/index/router.py`
- Modify: `backend/tests/test_storage_index_api.py`
- Modify: `frontend/src/api/storage/storageIndex/types.ts`
- Modify: `frontend/src/api/storage/storageIndex/index.ts`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Modify: `frontend/tests/movie-list.ui.test.tsx`

**Interfaces:**
- Produces backend response data:
  - `{"started": true, "mode": "full" | "incremental", "status": "running", "message": "存储索引任务启动成功"}`
- Produces HTTP 409 detail: `"存储索引任务正在进行中"`
- Produces frontend type: `StorageIndexRefreshStartResult`.

- [ ] **Step 1: Add backend API tests**

Append to `backend/tests/test_storage_index_api.py`:

```python
def test_storage_index_refresh_starts_background_task(client: TestClient, admin_user, monkeypatch):
    calls = {}

    def fake_start(mode, service_factory):
        calls["mode"] = mode
        calls["service_factory"] = service_factory
        return {"started": True, "mode": mode, "status": "running", "message": "存储索引任务启动成功"}

    monkeypatch.setattr("backend.app.modules.storage.index.router.start_storage_index_refresh", fake_start)

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "incremental"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "started": True,
        "mode": "incremental",
        "status": "running",
        "message": "存储索引任务启动成功",
    }
    assert calls["mode"] == "incremental"


def test_storage_index_refresh_rejects_when_already_running(client: TestClient, admin_user, monkeypatch):
    from backend.app.modules.storage.index.background import StorageIndexAlreadyRunningError

    def fake_start(mode, service_factory):
        raise StorageIndexAlreadyRunningError("存储索引任务正在进行中")

    monkeypatch.setattr("backend.app.modules.storage.index.router.start_storage_index_refresh", fake_start)

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "full"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["detail"] == "存储索引任务正在进行中"


def test_storage_index_refresh_reports_startup_failure(client: TestClient, admin_user, monkeypatch):
    def fake_start(mode, service_factory):
        raise RuntimeError("missing storage config")

    monkeypatch.setattr("backend.app.modules.storage.index.router.start_storage_index_refresh", fake_start)

    response = client.post(
        "/api/storage/index/refresh",
        json={"mode": "full"},
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["detail"] == "存储索引任务启动失败: missing storage config"
```

- [ ] **Step 2: Run backend API tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_api.py -v
```

Expected: FAIL because `background.py` and async start semantics do not exist yet.

- [ ] **Step 3: Create background refresh service**

Create `backend/app/modules/storage/index/background.py`:

```python
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.index.refresh import StorageIndexRefreshService
from backend.app.modules.storage.index.store import StorageIndexStore

logger = logging.getLogger(__name__)

_refresh_lock = threading.Lock()
_refresh_running = False


class StorageIndexAlreadyRunningError(RuntimeError):
    pass


def _set_running(value: bool) -> None:
    global _refresh_running
    with _refresh_lock:
        _refresh_running = value


def start_storage_index_refresh(
    mode: str,
    service_factory: Callable[[], StorageConfigService],
) -> dict:
    global _refresh_running
    with _refresh_lock:
        metadata = StorageIndexStore().read_metadata()
        if _refresh_running or metadata.status == "running":
            raise StorageIndexAlreadyRunningError("存储索引任务正在进行中")
        _refresh_running = True

    thread = threading.Thread(
        target=_run_refresh,
        args=(mode, service_factory),
        daemon=True,
        name=f"storage-index-refresh-{mode}",
    )
    thread.start()
    return {
        "started": True,
        "mode": mode,
        "status": "running",
        "message": "存储索引任务启动成功",
    }


def _run_refresh(mode: str, service_factory: Callable[[], StorageConfigService]) -> None:
    try:
        service = service_factory()
        with service.open_provider() as (config, provider):
            StorageIndexRefreshService().refresh(config, provider, mode=mode)
    except Exception:
        logger.exception("Storage index refresh failed")
    finally:
        _set_running(False)
```

- [ ] **Step 4: Update storage-index router**

In `backend/app/modules/storage/index/router.py`, update imports:

```python
from fastapi import APIRouter, Depends, HTTPException, status
```

Replace direct refresh imports with:

```python
from backend.app.modules.storage.index.background import (
    StorageIndexAlreadyRunningError,
    start_storage_index_refresh,
)
```

Remove `StorageIndexRefreshService` import.

Replace `refresh_storage_index()` body with:

```python
    try:
        result = start_storage_index_refresh(
            body.mode,
            service_factory=lambda: service,
        )
    except StorageIndexAlreadyRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"存储索引任务启动失败: {exc}",
        ) from exc
    return success(data=result)
```

- [ ] **Step 5: Run backend API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_api.py backend/tests/test_storage_index_refresh.py -v
```

Expected: PASS.

- [ ] **Step 6: Add frontend API type**

In `frontend/src/api/storage/storageIndex/types.ts`, append:

```ts
export interface StorageIndexRefreshStartResult {
  started: boolean
  mode: 'full' | 'incremental'
  status: 'running'
  message: string
}
```

In `frontend/src/api/storage/storageIndex/index.ts`, update imports and function:

```ts
import type { StorageIndexMetadata, StorageIndexRefreshStartResult } from './types.ts'
```

```ts
export function refreshStorageIndex(mode: StorageIndexRefreshMode): Promise<StorageIndexRefreshStartResult> {
  return request.post<StorageIndexRefreshStartResult>(`${BASE_URL}/refresh`, { mode })
}
```

- [ ] **Step 7: Update movie-list messages**

In `frontend/src/pages/content/movies/MovieListPage.tsx`, replace `handleRefreshStorageIndex()` with:

```tsx
  const handleRefreshStorageIndex = useCallback(async (mode: StorageIndexRefreshMode) => {
    setIndexRefreshing(mode)
    try {
      await refreshStorageIndex(mode)
      message.success(`${mode === 'full' ? '全量' : '增量'}索引任务启动成功`)
    } catch (error) {
      const text = error instanceof Error ? error.message : '存储索引任务启动失败'
      if (text.includes('正在进行中')) {
        message.warning('存储索引任务正在进行中')
      } else {
        message.error(text.includes('启动失败') ? text : `存储索引任务启动失败：${text}`)
      }
    } finally {
      setIndexRefreshing(null)
    }
  }, [message])
```

- [ ] **Step 8: Add frontend message tests**

In `frontend/tests/movie-list.ui.test.tsx`, update the storage index API mock if one exists; otherwise add:

```tsx
vi.mock('../src/api/storage/storageIndex', () => ({
  refreshStorageIndex: vi.fn(),
}))
```

Import it:

```tsx
import { refreshStorageIndex } from '../src/api/storage/storageIndex'
```

Append:

```tsx
  it('shows storage index task start success instead of completion', async () => {
    vi.mocked(refreshStorageIndex).mockResolvedValue({
      started: true,
      mode: 'incremental',
      status: 'running',
      message: '存储索引任务启动成功',
    })

    renderPage()
    await screen.findByText('AAA-001')
    await userEvent.click(screen.getByRole('button', { name: /存储索引/ }))
    await userEvent.click(await screen.findByText('增量索引'))

    expect(await screen.findByText('增量索引任务启动成功')).toBeInTheDocument()
  })

  it('shows storage index running warning for concurrent refresh', async () => {
    vi.mocked(refreshStorageIndex).mockRejectedValue(new Error('存储索引任务正在进行中'))

    renderPage()
    await screen.findByText('AAA-001')
    await userEvent.click(screen.getByRole('button', { name: /存储索引/ }))
    await userEvent.click(await screen.findByText('全量索引'))

    expect(await screen.findByText('存储索引任务正在进行中')).toBeInTheDocument()
  })
```

- [ ] **Step 9: Run frontend movie-list tests**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/modules/storage/index/background.py backend/app/modules/storage/index/router.py backend/tests/test_storage_index_api.py frontend/src/api/storage/storageIndex/types.ts frontend/src/api/storage/storageIndex/index.ts frontend/src/pages/content/movies/MovieListPage.tsx frontend/tests/movie-list.ui.test.tsx
git commit -m "fix: start storage index refresh asynchronously"
```

---

## Final Verification

- [ ] Run backend targeted tests:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py backend/tests/test_crawler_runs_api.py backend/tests/test_storage_index_api.py backend/tests/test_storage_index_refresh.py -v
```

Expected: PASS.

- [ ] Run frontend targeted tests:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] Run frontend static checks:

```bash
cd frontend
npm run lint
npm run build
```

Expected: PASS.

## Self-Review

- Spec coverage:
  - Incremental skipped existing rows hidden from child-task list: Task 1.
  - Top metric totals refreshed after realtime status changes: Task 2.
  - Storage index sync is asynchronous and returns start success: Task 3.
  - Concurrent storage index task reports running: Task 3.
  - Other storage index startup errors report failure: Task 3.
- Placeholder scan: no unfinished placeholder markers, deferred implementation notes, or undefined interfaces remain.
- Type consistency: `StorageIndexRefreshStartResult`, `RunTaskSummary`, `CrawlRunDetailTask`, and backend helper names are defined before use.
