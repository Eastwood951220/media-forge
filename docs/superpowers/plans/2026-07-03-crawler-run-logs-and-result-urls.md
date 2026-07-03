# Crawler Run Logs And Result URLs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split crawler run logs into a dedicated reusable endpoint, keep run-detail logs stable after completion/realtime updates, and make crawler run results report each configured task URL through `result.items`.

**Architecture:** The run detail endpoint remains the source for run metadata and detail task state, but it stops loading JSONL logs. A new `GET /api/crawler/runs/{run_id}/logs` endpoint becomes the unified read path for run logs; the frontend keeps logs in separate state so `crawler.run.updated` payloads cannot overwrite them with an empty array. During active runs, realtime log events append to the page; when a run reaches `completed`, `failed`, or `stopped`, the page calls the logs endpoint once more to load the final JSONL contents and catch any missed tail logs. Result metadata removes top-level `url` and `final_url`; `result.items` becomes a list of per-task-URL summaries, and each detail task is tagged with its originating task URL while being collected so the summaries can report accurate per-URL counts.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, JSONL log helpers, Pytest, React 19, TypeScript 6, Vitest, React Testing Library.

---

## Current Situation

- `backend/app/modules/crawler/runs/router.py:get_run()` currently does `payload["logs"] = load_run_logs(str(run_id))`.
- `frontend/src/pages/crawler/runs/RunDetailPage.tsx` stores logs inside `run.logs`.
- Realtime `crawler.run.updated` payloads are designed to carry run metadata and currently use `logs: []`; when a completion update arrives it can replace the whole `run` state and wipe logs from the UI.
- Reloading the page calls `GET /api/crawler/runs/{run_id}` again, which rereads the JSONL file, so logs reappear.
- The desired behavior is: logs appear during the run from realtime events, and when the run finishes the page immediately calls the new logs endpoint to refresh the final log list.
- `scraper/services/movie_result.py:first_url_metadata()` only uses `task.urls[0]`, so `result.url` and `result.final_url` show only the first URL even when a task has multiple URLs.
- The desired result shape now removes `result.url` and `result.final_url` completely. `result.items` should contain one object per configured task URL, including that URL's metadata and its own `total_tasks`, `completed_tasks`, `failed_tasks`, and `skipped_tasks`.

## Result URL Decision

For multi-URL crawler tasks, `result.url` and `result.final_url` as single strings are not sufficient and should not be converted to arrays. The implementation should:

- Remove top-level `result.url`.
- Remove top-level `result.final_url`.
- Keep aggregate result counters at the top level: `total_tasks`, `completed_tasks`, `failed_tasks`, `skipped_tasks`, `saved`, `stopped`.
- Store configured task URL results in `result.items`.
- Each `result.items[]` object should include `url`, `final_url`, `url_type`, `source`, `url_name`, `has_magnet`, `has_chinese_sub`, `sort_type`, `total_tasks`, `completed_tasks`, `failed_tasks`, and `skipped_tasks`.
- Saved movie payloads are not returned in `result.items`; `items` is reserved for task URL run summaries.

## File Structure

- Modify `backend/app/modules/crawler/runs/router.py`: add `GET /api/crawler/runs/{run_id}/logs`, stop loading JSONL logs in `GET /api/crawler/runs/{run_id}`.
- Modify `backend/tests/test_crawler_runs_api.py`: replace the old detail-includes-logs expectation with tests for the dedicated logs endpoint and metadata-only detail endpoint.
- Modify `frontend/src/api/crawlerRun/index.ts`: add `getCrawlerRunLogs(runId)`.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: keep `logs` in its own state, load logs separately, append realtime log events to logs state, and include logs in resync.
- Modify `frontend/tests/crawler-run-detail.ui.test.tsx`: assert log loading goes through `getCrawlerRunLogs`.
- Modify `frontend/tests/run-detail-realtime.ui.test.tsx`: assert completion updates do not clear existing logs and resync reloads logs.
- Modify `scraper/spiders/javdb/javdb_spider.py`: tag each collected detail task with the configured task URL it came from.
- Modify `scraper/services/movie_result.py`: remove top-level URL fields and build per-task-URL result items.
- Modify `scraper/services/movie_service.py`: rename the `build_task_result()` saved payload argument at the call site so `result.items` is no longer populated with saved movie payloads.
- Create `scraper/tests/test_movie_result.py`: cover single-URL, multi-URL, and skipped-task result metadata.

---

### Task 1: Backend Dedicated Run Logs Endpoint

**Files:**
- Modify: `backend/app/modules/crawler/runs/router.py`
- Modify: `backend/tests/test_crawler_runs_api.py`

- [ ] **Step 1: Replace the old log-in-detail backend test**

In `backend/tests/test_crawler_runs_api.py`, replace `test_run_detail_includes_jsonl_logs` with:

```python
def test_run_detail_excludes_jsonl_logs_and_logs_endpoint_returns_them(client: TestClient, admin_user, monkeypatch, tmp_path) -> None:
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

    detail_response = client.get(f"/api/crawler/runs/{run_id}", headers=headers)
    logs_response = client.get(f"/api/crawler/runs/{run_id}/logs", headers=headers)

    assert detail_response.status_code == HTTPStatus.OK
    detail_body = detail_response.json()["data"]
    assert detail_body["id"] == run_id
    assert detail_body["logs"] == []

    assert logs_response.status_code == HTTPStatus.OK
    logs_body = logs_response.json()["data"]
    assert [entry["message"] for entry in logs_body] == ["任务开始执行", "入库失败"]
    assert logs_body[1]["context"] == {"code": "AAA-001"}
```

Append this not-found test after it:

```python
def test_run_logs_endpoint_returns_404_for_missing_run(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)

    response = client.get("/api/crawler/runs/00000000-0000-0000-0000-000000000001/logs", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
```

- [ ] **Step 2: Run the backend log endpoint tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_run_detail_excludes_jsonl_logs_and_logs_endpoint_returns_them backend/tests/test_crawler_runs_api.py::test_run_logs_endpoint_returns_404_for_missing_run -v
```

Expected: FAIL because `/api/crawler/runs/{run_id}` still includes logs and `/api/crawler/runs/{run_id}/logs` does not exist yet.

- [ ] **Step 3: Add the logs endpoint and stop loading logs in run detail**

Modify `backend/app/modules/crawler/runs/router.py`.

Replace `get_run()` with:

```python
@router.get("/{run_id}")
def get_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    payload = CrawlRunRead.model_validate(run).model_dump(mode="json")
    payload["logs"] = []
    return success(data=payload)
```

Add this endpoint immediately after `get_run()` and before `list_run_tasks()`:

```python
@router.get("/{run_id}/logs")
def get_run_logs(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return success(data=load_run_logs(str(run_id)))
```

- [ ] **Step 4: Run the backend log endpoint tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py::test_run_detail_excludes_jsonl_logs_and_logs_endpoint_returns_them backend/tests/test_crawler_runs_api.py::test_run_logs_endpoint_returns_404_for_missing_run -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_runs_api.py
git commit -m "fix: split crawler run logs endpoint"
```

---

### Task 2: Frontend Loads Logs Through The Unified Logs API

**Files:**
- Modify: `frontend/src/api/crawlerRun/index.ts`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Modify: `frontend/tests/crawler-run-detail.ui.test.tsx`
- Modify: `frontend/tests/run-detail-realtime.ui.test.tsx`

- [ ] **Step 1: Update the API mock tests to include `getCrawlerRunLogs`**

In `frontend/tests/crawler-run-detail.ui.test.tsx`, change the import:

```ts
import { getCrawlerRun, getCrawlerRunTasks } from '../src/api/crawlerRun'
```

to:

```ts
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks } from '../src/api/crawlerRun'
```

Change the mock:

```ts
vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))
```

to:

```ts
vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))
```

In the `beforeEach`, change the mocked run so `logs: []`, and add a separate logs mock:

```ts
      logs: [],
    })
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([
      { timestamp: '2026-07-02T00:00:01Z', level: 'INFO', message: '任务开始执行' },
      { timestamp: '2026-07-02T00:00:02Z', level: 'ERROR', message: '入库失败: AAA-001' },
    ])
```

In `passes the route id to run detail APIs`, add:

```ts
    expect(getCrawlerRunLogs).toHaveBeenCalledWith('run-1')
```

- [ ] **Step 2: Update realtime tests to include logs API and preserve logs on completion**

In `frontend/tests/run-detail-realtime.ui.test.tsx`, change the import:

```ts
import { getCrawlerRun, getCrawlerRunTasks } from '../src/api/crawlerRun'
```

to:

```ts
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks } from '../src/api/crawlerRun'
```

Change the mock:

```ts
vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))
```

to:

```ts
vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))
```

In `beforeEach`, add:

```ts
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([])
```

Append this test before `resyncs snapshots when system resync is required`:

```ts
  it('keeps existing logs when completion run updates contain empty logs', async () => {
    renderPage()
    await vi.runAllTimersAsync()

    emit('crawler.run.log.appended', {
      run_id: 'run-1',
      log: {
        timestamp: '2026-07-03T00:03:00Z',
        level: 'INFO',
        component: 'crawler.run',
        event: 'run_log',
        message: '详情 53/53 跳过',
        context: { reason: 'already_exists' },
      },
    })

    expect(await screen.findByText('详情 53/53 跳过')).toBeInTheDocument()

    emit('crawler.run.updated', {
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: '2026-07-03T00:10:00Z',
      result: { skipped_tasks: 54 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })

    expect(await screen.findByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('详情 53/53 跳过')).toBeInTheDocument()
  })
```

Append this test after it:

```ts
  it('reloads final logs from the logs endpoint when a run completes', async () => {
    vi.mocked(getCrawlerRunLogs)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          timestamp: '2026-07-03T00:10:00Z',
          level: 'INFO',
          component: 'crawler.run',
          event: 'run_log',
          message: '详情处理完成: 总计=54 已完成=0 失败=0 跳过=54',
          context: {},
        },
      ])

    renderPage()
    await vi.runAllTimersAsync()
    await screen.findByText('运行详情 - 任务A')

    emit('crawler.run.updated', {
      id: 'run-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'completed',
      crawl_mode: 'incremental',
      queued_at: null,
      started_at: null,
      finished_at: '2026-07-03T00:10:00Z',
      result: { skipped_tasks: 54 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-03T00:00:00Z',
      updated_at: null,
      logs: [],
    })

    await waitFor(() => {
      expect(getCrawlerRunLogs).toHaveBeenCalledTimes(2)
    })
    expect(await screen.findByText('详情处理完成: 总计=54 已完成=0 失败=0 跳过=54')).toBeInTheDocument()
  })
```

In `resyncs snapshots when system resync is required`, change the wait assertion to:

```ts
    await waitFor(() => {
      expect(getCrawlerRun).toHaveBeenCalledTimes(2)
      expect(getCrawlerRunLogs).toHaveBeenCalledTimes(2)
      expect(getCrawlerRunTasks).toHaveBeenCalledTimes(2)
    })
```

- [ ] **Step 3: Run frontend tests and verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-run-detail.ui.test.tsx run-detail-realtime.ui.test.tsx
```

Expected: FAIL because `getCrawlerRunLogs` is not exported and `RunDetailPage` still reads/writes logs through `run.logs`.

- [ ] **Step 4: Add `getCrawlerRunLogs` API**

Modify `frontend/src/api/crawlerRun/index.ts`.

Add `RunLogEntry` to the type import:

```ts
import type {
  CrawlRun,
  CrawlRunDetailTask,
  CrawlMode,
  QueueStatus,
  RunLogEntry,
} from './types'
```

Add this function after `getCrawlerRun()`:

```ts
export function getCrawlerRunLogs(runId: string): Promise<RunLogEntry[]> {
  return request.get<RunLogEntry[]>(`${BASE_URL}/${runId}/logs`)
}
```

- [ ] **Step 5: Split logs state from run state in `RunDetailPage`**

Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`.

Change the API import:

```ts
import { getCrawlerRun, getCrawlerRunTasks } from '@/api/crawlerRun'
```

to:

```ts
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks } from '@/api/crawlerRun'
```

Change the type import:

```ts
import type { CrawlRun, CrawlRunDetailTask } from '@/api/crawlerRun/types'
```

to:

```ts
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'
```

Add logs state after the `run` state:

```ts
  const [logs, setLogs] = useState<RunLogEntry[]>([])
```

In the run ID reset effect, add:

```ts
    setLogs([])
```

Add this fetch helper after `fetchRun`:

```ts
  const fetchLogs = useCallback(async () => {
    if (!id) return
    const data = await getCrawlerRunLogs(id)
    setLogs(data)
  }, [id])
```

Update `resyncSnapshot()`:

```ts
  const resyncSnapshot = useCallback(() => {
    void fetchRun()
    void fetchLogs()
    void fetchTasks()
  }, [fetchLogs, fetchRun, fetchTasks])
```

Add an initial logs effect after the run effect:

```ts
  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])
```

In the `crawler.run.updated` handler, replace:

```ts
        setRun(event.payload)
```

with:

```ts
        setRun((currentRun) => ({
          ...(event.payload as CrawlRun),
          logs: currentRun?.logs ?? [],
        }))
        if (['completed', 'failed', 'stopped'].includes(event.payload.status)) {
          void fetchLogs()
        }
```

In the `crawler.run.log.appended` handler, replace the `setRun(...)` block with:

```ts
        setLogs((currentLogs) => [...currentLogs, event.payload.log])
```

At render time, replace:

```tsx
            logs={run.logs ?? []}
```

with:

```tsx
            logs={logs}
```

- [ ] **Step 6: Run frontend tests and verify they pass**

Run:

```bash
cd frontend && npm test -- crawler-run-detail.ui.test.tsx run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add frontend/src/api/crawlerRun/index.ts frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/tests/crawler-run-detail.ui.test.tsx frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "fix: load crawler run logs separately"
```

---

### Task 3: Move Task URL Results Into `result.items`

**Files:**
- Create: `scraper/tests/test_movie_result.py`
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Modify: `scraper/services/movie_result.py`
- Modify: `scraper/services/movie_service.py`

- [ ] **Step 1: Write failing result-item tests**

Create `scraper/tests/test_movie_result.py`:

```python
from scraper.services.movie_result import build_skipped_task_result, build_task_result
from scraper.spiders.javdb.javdb_constants import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_SKIPPED,
)
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def make_multi_url_task(is_skip: bool = False) -> CrawlTask:
    return CrawlTask(
        name="多 URL 任务",
        is_skip=is_skip,
        urls=[
            CrawlTaskUrlEntry(
                url="https://javdb.com/actors/QV49G",
                url_type="actors",
                source="javdb",
                final_url="https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
                url_name="演员A",
                has_magnet=True,
                has_chinese_sub=False,
                sort_type=0,
            ),
            CrawlTaskUrlEntry(
                url="https://javdb.com/actors/8VGXO",
                url_type="actors",
                source="javdb",
                final_url="https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
                url_name="演员B",
                has_magnet=False,
                has_chinese_sub=True,
                sort_type=1,
            ),
        ],
    )


def test_build_task_result_removes_top_level_urls_and_items_are_task_url_results() -> None:
    detail_tasks = [
        {
            "status": TASK_STATUS_COMPLETED,
            "_task_url": "https://javdb.com/actors/QV49G",
            "_task_final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
        },
        {
            "status": TASK_STATUS_SKIPPED,
            "_task_url": "https://javdb.com/actors/QV49G",
            "_task_final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
        },
        {
            "status": TASK_STATUS_FAILED,
            "_task_url": "https://javdb.com/actors/8VGXO",
            "_task_final_url": "https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
        },
    ]

    result = build_task_result(
        task=make_multi_url_task(),
        detail_tasks=detail_tasks,
        saved_items=[{"code": "AAA-001"}],
        stopped=False,
    )

    assert "url" not in result
    assert "final_url" not in result
    assert "urls" not in result
    assert "final_urls" not in result
    assert "url_entries" not in result
    assert result["total_tasks"] == 3
    assert result["completed_tasks"] == 1
    assert result["failed_tasks"] == 1
    assert result["skipped_tasks"] == 1
    assert result["saved"] == 0
    assert result["items"] == [
        {
            "url": "https://javdb.com/actors/QV49G",
            "final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员A",
            "has_magnet": True,
            "has_chinese_sub": False,
            "sort_type": 0,
            "total_tasks": 2,
            "completed_tasks": 1,
            "failed_tasks": 0,
            "skipped_tasks": 1,
        },
        {
            "url": "https://javdb.com/actors/8VGXO",
            "final_url": "https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员B",
            "has_magnet": False,
            "has_chinese_sub": True,
            "sort_type": 1,
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 1,
            "skipped_tasks": 0,
        },
    ]


def test_build_skipped_task_result_items_include_each_task_url_with_zero_counts() -> None:
    result = build_skipped_task_result(make_multi_url_task(is_skip=True))

    assert result["is_skip"] is True
    assert "url" not in result
    assert "final_url" not in result
    assert result["items"] == [
        {
            "url": "https://javdb.com/actors/QV49G",
            "final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员A",
            "has_magnet": True,
            "has_chinese_sub": False,
            "sort_type": 0,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 0,
        },
        {
            "url": "https://javdb.com/actors/8VGXO",
            "final_url": "https://javdb.com/actors/8VGXO?page=1&t=d&sort_type=0",
            "url_type": "actors",
            "source": "javdb",
            "url_name": "演员B",
            "has_magnet": False,
            "has_chinese_sub": True,
            "sort_type": 1,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "skipped_tasks": 0,
        },
    ]
```

- [ ] **Step 2: Run result metadata tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_movie_result.py -v
```

Expected: FAIL because `build_task_result()` still accepts `items`, still returns top-level `url` and `final_url`, and does not build per-task-URL result items.

- [ ] **Step 3: Tag collected detail tasks with source task URL metadata**

Modify `scraper/spiders/javdb/javdb_spider.py`.

In `collect_detail_tasks_for_url()`, replace:

```python
                fresh_tasks.append(t)
```

with:

```python
                t["_task_url"] = url_entry.url
                t["_task_final_url"] = url_entry.final_url or url_entry.url
                t["_task_url_type"] = url_entry.url_type
                t["_task_source"] = url_entry.source
                t["_task_url_name"] = url_entry.url_name
                t["_task_has_magnet"] = url_entry.has_magnet
                t["_task_has_chinese_sub"] = url_entry.has_chinese_sub
                t["_task_sort_type"] = url_entry.sort_type
                fresh_tasks.append(t)
```

- [ ] **Step 4: Implement per-task-URL result summaries**

Modify `scraper/services/movie_result.py`.

Replace:

```python
from scraper.tasks.task_schema import CrawlTask
```

with:

```python
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry
```

Replace `first_url_metadata()` with:

```python
def _matching_url_tasks(entry: CrawlTaskUrlEntry, detail_tasks: list[dict]) -> list[dict]:
    final_url = entry.final_url or entry.url
    return [
        item
        for item in detail_tasks
        if item.get("_task_url") == entry.url
        and item.get("_task_final_url") == final_url
    ]


def _url_result_item(entry: CrawlTaskUrlEntry, detail_tasks: list[dict]) -> dict:
    matching_tasks = _matching_url_tasks(entry, detail_tasks)
    summary = summarize_detail_tasks(matching_tasks)
    return {
        "url": entry.url,
        "final_url": entry.final_url or entry.url,
        "url_type": entry.url_type,
        "source": entry.source,
        "url_name": entry.url_name,
        "has_magnet": entry.has_magnet,
        "has_chinese_sub": entry.has_chinese_sub,
        "sort_type": entry.sort_type,
        **summary,
    }


def url_result_items(task: CrawlTask, detail_tasks: list[dict]) -> list[dict]:
    return [_url_result_item(entry, detail_tasks) for entry in task.urls]
```

In `build_skipped_task_result()`, replace:

```python
        **first_url_metadata(task),
        "is_skip": True,
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "skipped_tasks": 0,
        "saved": 0,
        "items": [],
        "reason": "skipped_by_config",
```

with:

```python
        "is_skip": True,
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "skipped_tasks": 0,
        "saved": 0,
        "items": url_result_items(task, []),
        "reason": "skipped_by_config",
```

Replace the `build_task_result()` signature:

```python
def build_task_result(
    task: CrawlTask,
    detail_tasks: list[dict],
    items: list[dict],
    stopped: bool,
) -> dict:
```

with:

```python
def build_task_result(
    task: CrawlTask,
    detail_tasks: list[dict],
    saved_items: list[dict],
    stopped: bool,
) -> dict:
```

Inside `build_task_result()`, replace the return value with:

```python
    return {
        "task_name": task.name,
        "is_skip": task.is_skip,
        **summarize_detail_tasks(detail_tasks),
        "saved": 0,
        "items": url_result_items(task, detail_tasks),
        "stopped": stopped,
    }
```

- [ ] **Step 5: Update the movie service call site**

Modify `scraper/services/movie_service.py`.

Replace:

```python
        return build_task_result(
            task=task,
            detail_tasks=detail_tasks,
            items=collected_items,
            stopped=stopped,
        )
```

with:

```python
        return build_task_result(
            task=task,
            detail_tasks=detail_tasks,
            saved_items=collected_items,
            stopped=stopped,
        )
```

- [ ] **Step 6: Run result metadata tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest scraper/tests/test_movie_result.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add scraper/spiders/javdb/javdb_spider.py scraper/services/movie_result.py scraper/services/movie_service.py scraper/tests/test_movie_result.py
git commit -m "fix: summarize crawler result items by task url"
```

---

### Task 4: Regression Verification

**Files:**
- Verify: `backend/app/modules/crawler/runs/router.py`
- Verify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Verify: `scraper/spiders/javdb/javdb_spider.py`
- Verify: `scraper/services/movie_result.py`
- Verify: `scraper/services/movie_service.py`

- [ ] **Step 1: Run focused backend/API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py scraper/tests/test_movie_result.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- crawler-run-detail.ui.test.tsx run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run backend test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ scraper/tests/ -v
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. Existing Vite warnings about chunk size, dynamic imports, or plugin timings are acceptable if the command exits with status 0.

- [ ] **Step 5: Manual API sanity checks**

With the backend running and an authenticated token available, call:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/684db16c-daee-4553-b9c4-9f565ea6b617
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/crawler/runs/684db16c-daee-4553-b9c4-9f565ea6b617/logs
```

Expected:

```json
{
  "data": {
    "logs": [],
    "result": {
      "task_name": "3333",
      "is_skip": false,
      "total_tasks": 54,
      "completed_tasks": 0,
      "failed_tasks": 0,
      "skipped_tasks": 54,
      "saved": 0,
      "stopped": false,
      "items": [
        {
          "url": "https://javdb.com/actors/QV49G",
          "final_url": "https://javdb.com/actors/QV49G?page=1&t=d&sort_type=0",
          "url_type": "actors",
          "source": "javdb",
          "url_name": "演员A",
          "has_magnet": true,
          "has_chinese_sub": false,
          "sort_type": 0,
          "total_tasks": 54,
          "completed_tasks": 0,
          "failed_tasks": 0,
          "skipped_tasks": 54
        }
      ]
    }
  }
}
```

The `/logs` endpoint should return the JSONL log array. `result.url`, `result.final_url`, `result.urls`, `result.final_urls`, and `result.url_entries` should be absent. For tasks with multiple URLs, `result.items` should contain one summary object per configured task URL.

---

## Self-Review Result

- Spec coverage: The plan covers the empty-log-after-completion symptom, the new unified logs endpoint, frontend state separation, realtime log preservation, final log reload after terminal run status, removing top-level result URL fields, and moving per-task-URL run results into `result.items`.
- Placeholder scan: No placeholder implementation steps remain; every code-changing step includes concrete snippets and exact commands.
- Type consistency: `RunLogEntry` is reused by `getCrawlerRunLogs`, `RunDetailPage`, realtime payloads, and `RunLogsTimeline`; `build_task_result()` accepts `saved_items` only to keep saved movie payloads out of `result.items`, while `result.items` is reserved for task URL run summaries.
