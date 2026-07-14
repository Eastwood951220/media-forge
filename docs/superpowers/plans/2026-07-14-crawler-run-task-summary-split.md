# Crawler Run Task Summary Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split crawler run detail task list data from run-wide task summary statistics, and make active-run summary tiles update from EventSource payloads.

**Architecture:** The backend exposes a dedicated `tasks/summary` endpoint and removes `summary` from the paginated task list response. The realtime detail event publisher attaches a complete `RunTaskSummary` payload so the frontend can replace summary state directly during active runs, while database fetches remain the source for initial load, terminal states, reconnects, and incomplete events.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React 19, TypeScript, Vitest, React Testing Library, Ant Design.

## Global Constraints

- Preserve existing crawler run lifecycle behavior.
- Preserve existing run detail table pagination, status filter, keyword search, retry actions, and logs.
- Summary statistics cover all visible detail tasks for the run, not current table filters or keywords.
- Keep the incremental hidden skip rule: incremental runs hide `skipped` detail rows whose `error` is `already_exists`.
- Do not add unrelated features or restructure modules outside the files listed in this plan.
- Do not overwrite unrelated uncommitted changes in the working tree.

---

## File Structure

- Modify `backend/app/modules/crawler/runs/router.py`: keep the visible detail task query helper, make the task list response list-only, and add `GET /{run_id}/tasks/summary`.
- Modify `backend/app/modules/crawler/runtime/events.py`: compute and attach `summary` to `crawler.run.detail.updated` events.
- Modify `backend/tests/test_crawler_runs_api.py`: update list endpoint assertions and add dedicated summary endpoint coverage.
- Modify `backend/tests/test_crawler_realtime_events.py`: assert realtime detail events carry complete summary payloads.
- Modify `frontend/src/api/crawlerRun/index.ts`: remove `summary` from task list response typing and add `getCrawlerRunTaskSummary`.
- Modify `frontend/src/realtime/types.ts`: add optional `summary` to `CrawlerRunDetailUpdatedPayload`.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`: split `fetchTasks` and `fetchTaskSummary`.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`: use event `summary` directly and database fallback for incomplete events.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`: pass `fetchTaskSummary` into the realtime hook.
- Modify `frontend/tests/run-detail-realtime.ui.test.tsx`: mock and assert separate summary loading and realtime summary behavior.

---

### Task 1: Backend Summary Endpoint And List Response Split

**Files:**
- Modify: `backend/app/modules/crawler/runs/router.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Consumes: existing `_visible_run_detail_task_query(db: Session, run: CrawlRun)`.
- Produces: `GET /api/crawler/runs/{run_id}/tasks` returning `paginated(rows, total)` without `summary`.
- Produces: `GET /api/crawler/runs/{run_id}/tasks/summary` returning `success(data=RunTaskSummary)`.

- [ ] **Step 1: Write failing backend API tests**

In `backend/tests/test_crawler_runs_api.py`, update `test_run_tasks_endpoint_returns_full_run_summary` into two focused assertions. Keep the setup data, then make the list endpoint prove `summary` is absent and make the new summary endpoint prove the full run summary is returned:

```python
def test_run_tasks_endpoint_returns_paginated_rows_without_summary(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="P", source_url="https://p", source_name="P", status="pending_crawl", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="S", source_url="https://s", source_name="S", status="saved", created_at=datetime.now()),
    ])
    session.commit()

    response = client.get(
        f"/api/crawler/runs/{run.id}/tasks",
        params={"status": "saved", "page": 1, "size": 1},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert [row["code"] for row in body["rows"]] == ["S"]
    assert "summary" not in body


def test_run_task_summary_endpoint_returns_full_run_summary(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="P", source_url="https://p", source_name="P", status="pending_crawl", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="R", source_url="https://r", source_name="R", status="crawling", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="S", source_url="https://s", source_name="S", status="saved", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="K", source_url="https://k", source_name="K", status="skipped", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="C", source_url="https://c", source_name="C", status="crawl_failed", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="F", source_url="https://f", source_name="F", status="save_failed", created_at=datetime.now()),
    ])
    session.commit()

    response = client.get(f"/api/crawler/runs/{run.id}/tasks/summary", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"] == {
        "total": 6,
        "pending_crawl": 1,
        "crawling": 1,
        "saved": 1,
        "skipped": 1,
        "crawl_failed": 1,
        "save_failed": 1,
        "completed": 2,
        "waiting": 2,
        "failed": 2,
    }
```

Add this missing-run test near the existing 404 tests:

```python
def test_run_task_summary_endpoint_returns_404_for_missing_run(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)

    response = client.get("/api/crawler/runs/00000000-0000-0000-0000-000000000001/tasks/summary", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
```

Update `test_incremental_run_tasks_hide_legacy_already_exists_skips` so the list response no longer checks `payload["summary"]`; add a separate summary call:

```python
    response = client.get(f"/api/crawler/runs/{run.id}/tasks", headers=auth_headers(client, admin_user))

    assert response.status_code == 200
    payload = response.json()
    assert [row["code"] for row in payload["rows"]] == ["NEW-001"]
    assert payload["total"] == 1
    assert "summary" not in payload

    summary_response = client.get(f"/api/crawler/runs/{run.id}/tasks/summary", headers=auth_headers(client, admin_user))
    assert summary_response.status_code == 200
    assert summary_response.json()["data"]["total"] == 1
    assert summary_response.json()["data"]["skipped"] == 0
    assert summary_response.json()["data"]["waiting"] == 1
```

- [ ] **Step 2: Run backend API tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -k "summary or run_tasks_endpoint or incremental_run_tasks_hide" -v
```

Expected: fails because `/tasks/summary` does not exist yet and `/tasks` still includes `summary`.

- [ ] **Step 3: Implement the endpoint split**

In `backend/app/modules/crawler/runs/router.py`, replace the end of `list_run_tasks` with a pure paginated return and add the new route after it:

```python
    rows = query.order_by(CrawlRunDetailTask.created_at.asc()).offset(offset).limit(size).all()
    return paginated(
        rows=[CrawlRunDetailTaskRead.model_validate(r).model_dump(mode="json") for r in rows],
        total=total,
    )


@router.get("/{run_id}/tasks/summary")
def get_run_task_summary(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return success(data=_run_task_summary(db, run))
```

Keep `_run_task_summary` and `_visible_run_detail_task_query` unchanged so the existing hidden incremental skip behavior is reused.

- [ ] **Step 4: Run backend API tests and verify pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -k "summary or run_tasks_endpoint or incremental_run_tasks_hide" -v
```

Expected: selected tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: split crawler run task summary endpoint"
```

---

### Task 2: Backend Realtime Summary Payload

**Files:**
- Modify: `backend/app/modules/crawler/runtime/events.py`
- Test: `backend/tests/test_crawler_realtime_events.py`

**Interfaces:**
- Consumes: `_run_task_summary(db: Session, run: CrawlRun) -> dict` from `backend.app.modules.crawler.runs.router`.
- Produces: `crawler.run.detail.updated` payload with `summary: dict`.

- [ ] **Step 1: Write failing realtime payload tests**

In `backend/tests/test_crawler_realtime_events.py`, update `test_publish_detail_updated_event_for_owner`:

```python
    assert events[0].payload["run_id"] == str(run.id)
    assert events[0].payload["tasks"][0]["status"] == "saved"
    assert events[0].payload["summary"] == {
        "total": 1,
        "pending_crawl": 0,
        "crawling": 0,
        "saved": 1,
        "skipped": 0,
        "crawl_failed": 0,
        "save_failed": 0,
        "completed": 1,
        "waiting": 0,
        "failed": 0,
    }
```

Update `test_publish_detail_updated_can_request_task_refresh`:

```python
    assert events[0].payload["tasks"] == []
    assert events[0].payload["refresh_tasks"] is True
    assert events[0].payload["reason"] == "url_completed"
    assert events[0].payload["summary"]["total"] == 0
    assert events[0].payload["summary"]["completed"] == 0
    assert events[0].payload["summary"]["failed"] == 0
```

Update `test_crawler_realtime_events_keep_frontend_contract` after the existing `detail_event.payload["tasks"][0]` assertion:

```python
    assert detail_event.payload["summary"] == {
        "total": 1,
        "pending_crawl": 0,
        "crawling": 0,
        "saved": 1,
        "skipped": 0,
        "crawl_failed": 0,
        "save_failed": 0,
        "completed": 1,
        "waiting": 0,
        "failed": 0,
    }
```

- [ ] **Step 2: Run realtime tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py -v
```

Expected: tests fail with missing `summary` in event payload.

- [ ] **Step 3: Attach summary in event publisher**

In `backend/app/modules/crawler/runtime/events.py`, import the summary helper inside `publish_run_detail_updated` to avoid broad module import side effects:

```python
    from backend.app.modules.crawler.runs.router import _run_task_summary
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event
```

Then include `summary` when building `payload`:

```python
    payload: dict[str, Any] = {
        "run_id": str(run.id),
        "tasks": detail_payloads,
        "summary": _run_task_summary(db, run),
    }
```

Keep the existing `refresh_tasks` and `reason` conditional fields unchanged.

- [ ] **Step 4: Run realtime tests and verify pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_realtime_events.py -v
```

Expected: all tests in `test_crawler_realtime_events.py` pass.

- [ ] **Step 5: Run combined backend crawler run coverage**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_realtime_events.py -v
```

Expected: both files pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/modules/crawler/runtime/events.py backend/tests/test_crawler_realtime_events.py
git commit -m "feat: include crawler run task summary in realtime events"
```

---

### Task 3: Frontend API And Detail State Split

**Files:**
- Modify: `frontend/src/api/crawlerRun/index.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- Test: `frontend/tests/run-detail-realtime.ui.test.tsx`

**Interfaces:**
- Consumes: `GET /api/crawler/runs/{run_id}/tasks` returns `PaginatedResponse<CrawlRunDetailTask>`.
- Consumes: `GET /api/crawler/runs/{run_id}/tasks/summary` returns `RunTaskSummary`.
- Produces: `useRunDetail` return value includes `fetchTaskSummary: () => Promise<void>`.

- [ ] **Step 1: Write failing frontend tests for separate summary fetch**

In `frontend/tests/run-detail-realtime.ui.test.tsx`, update the API mock import:

```ts
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTaskSummary, getCrawlerRunTasks } from '../src/api/crawlerRun'
```

Update the `vi.mock('../src/api/crawlerRun'...)` block:

```ts
vi.mock('../src/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn(),
  getCrawlerRunTaskSummary: vi.fn(),
  getCrawlerRunTasks: vi.fn(),
}))
```

In `beforeEach`, change the task mock to list-only and add a summary mock:

```ts
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 0,
    })
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({
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
    })
```

Update the first test so it asserts the summary endpoint is called:

```ts
    expect(getCrawlerRunTaskSummary).toHaveBeenCalledWith('run-1')
```

Add this test:

```ts
  it('does not expect summary from the paginated tasks response', async () => {
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({
      total: 2,
      pending_crawl: 1,
      crawling: 0,
      saved: 1,
      skipped: 0,
      crawl_failed: 0,
      save_failed: 0,
      completed: 1,
      waiting: 1,
      failed: 0,
    })
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 2,
    })

    renderPage()

    expect(await screen.findByText('运行详情 - 任务A')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('总数').parentElement?.textContent).toContain('2')
      expect(screen.getByText('完成').parentElement?.textContent).toContain('1')
      expect(screen.getByText('等待').parentElement?.textContent).toContain('1')
    })
  })
```

- [ ] **Step 2: Run frontend test and verify failure**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: fails because `getCrawlerRunTaskSummary` does not exist and `getCrawlerRunTasks` still expects `summary`.

- [ ] **Step 3: Update frontend API module**

In `frontend/src/api/crawlerRun/index.ts`, remove the custom response type that intersects summary:

```ts
import type { PaginatedResponse } from '../crawlTask/types'
```

Update `getCrawlerRunTasks`:

```ts
export function getCrawlerRunTasks(
  runId: string,
  params?: {
    page?: number
    size?: number
    status?: string
    keyword?: string
  },
): Promise<PaginatedResponse<CrawlRunDetailTask>> {
  return request.get<PaginatedResponse<CrawlRunDetailTask>>(`${BASE_URL}/${runId}/tasks`, params)
}
```

Add the summary call:

```ts
export function getCrawlerRunTaskSummary(runId: string): Promise<RunTaskSummary> {
  return request.get<RunTaskSummary>(`${BASE_URL}/${runId}/tasks/summary`)
}
```

- [ ] **Step 4: Split `useRunDetail` task and summary loading**

In `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`, update the import:

```ts
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTaskSummary, getCrawlerRunTasks, restartCrawlerRun, retryCrawlerRunTasks, stopCrawlerRun } from '@/api/crawlerRun'
```

Update `fetchTasks` so it does not touch summary:

```ts
  const fetchTasks = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await getCrawlerRunTasks(id, {
        page: taskPage,
        size: pageSize,
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

Add `fetchTaskSummary`:

```ts
  const fetchTaskSummary = useCallback(async () => {
    if (!id) return
    const data = await getCrawlerRunTaskSummary(id)
    setTaskSummary(data)
  }, [id])
```

Update `resyncSnapshot`:

```ts
  const resyncSnapshot = useCallback(() => {
    void fetchRun()
    void fetchLogs()
    void fetchTasks()
    void fetchTaskSummary()
  }, [fetchLogs, fetchRun, fetchTaskSummary, fetchTasks])
```

Add initial summary effect:

```ts
  useEffect(() => {
    void fetchTaskSummary()
  }, [fetchTaskSummary])
```

Return `fetchTaskSummary`:

```ts
    fetchTaskSummary,
```

- [ ] **Step 5: Run frontend test and verify partial pass**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: tests related to initial separate summary fetching pass; realtime tests may still fail until Task 4 updates event handling.

- [ ] **Step 6: Commit Task 3**

```bash
git add frontend/src/api/crawlerRun/index.ts frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "feat: load crawler run task summary separately"
```

---

### Task 4: Frontend Realtime Summary Handling

**Files:**
- Modify: `frontend/src/realtime/types.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Test: `frontend/tests/run-detail-realtime.ui.test.tsx`

**Interfaces:**
- Consumes: `CrawlerRunDetailUpdatedPayload.summary?: RunTaskSummary`.
- Consumes: `fetchTaskSummary: () => Promise<void>` from `useRunDetail`.
- Produces: summary state replaced by realtime `payload.summary` when available.
- Produces: summary endpoint fallback for old-style detail events without summary.

- [ ] **Step 1: Write failing realtime summary tests**

In `frontend/tests/run-detail-realtime.ui.test.tsx`, replace the existing `"updates summary metrics when realtime detail task status changes inline"` test with summary-payload behavior:

```ts
  it('updates summary metrics from realtime detail event summary payload', async () => {
    vi.mocked(getCrawlerRunTaskSummary).mockResolvedValue({
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
    })
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({
      rows: [],
      total: 1,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('等待').parentElement?.textContent).toContain('1')
    })

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
      summary: {
        total: 1,
        pending_crawl: 0,
        crawling: 0,
        saved: 1,
        skipped: 0,
        crawl_failed: 0,
        save_failed: 0,
        completed: 1,
        waiting: 0,
        failed: 0,
      },
    })

    await waitFor(() => {
      expect(screen.getByText('完成').parentElement?.textContent).toContain('1')
      expect(screen.getByText('等待').parentElement?.textContent).toContain('0')
    })
  })
```

Add fallback coverage:

```ts
  it('refetches summary for old detail events without summary payload', async () => {
    vi.mocked(getCrawlerRunTaskSummary)
      .mockResolvedValueOnce({
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
      })
      .mockResolvedValueOnce({
        total: 1,
        pending_crawl: 0,
        crawling: 0,
        saved: 1,
        skipped: 0,
        crawl_failed: 0,
        save_failed: 0,
        completed: 1,
        waiting: 0,
        failed: 0,
      })

    renderPage()
    await screen.findByText('运行详情 - 任务A')

    const initialSummaryCalls = vi.mocked(getCrawlerRunTaskSummary).mock.calls.length

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
    })

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRunTaskSummary).mock.calls.length).toBeGreaterThan(initialSummaryCalls)
      expect(screen.getByText('完成').parentElement?.textContent).toContain('1')
    })
  })
```

Update terminal and resync tests to also assert `getCrawlerRunTaskSummary` call counts increase:

```ts
    const initialSummaryCalls = vi.mocked(getCrawlerRunTaskSummary).mock.calls.length as number
```

and inside each `waitFor`:

```ts
      expect(vi.mocked(getCrawlerRunTaskSummary).mock.calls.length).toBeGreaterThan(initialSummaryCalls)
```

- [ ] **Step 2: Run frontend test and verify failure**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: fails because realtime payload typing and hook behavior do not use `summary` yet.

- [ ] **Step 3: Update realtime payload type**

In `frontend/src/realtime/types.ts`, import `RunTaskSummary`:

```ts
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry, RunTaskSummary } from '@/api/crawlerRun/types'
```

Update `CrawlerRunDetailUpdatedPayload`:

```ts
export type CrawlerRunDetailUpdatedPayload = {
  run_id: string
  tasks: CrawlRunDetailTask[]
  refresh_tasks?: boolean
  reason?: string
  summary?: RunTaskSummary
}
```

- [ ] **Step 4: Update realtime hook signature and behavior**

In `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`, remove `isSummaryStatus` and `applyStatusTransition`. Add `fetchTaskSummary` to the args type:

```ts
  fetchTaskSummary: () => Promise<void>
```

Destructure it:

```ts
    fetchTaskSummary,
```

In the `crawler.run.updated` terminal branch, refresh summary with the other snapshots:

```ts
        if (['completed', 'failed', 'stopped'].includes(event.payload.status)) {
          void fetchRun()
          void fetchLogs()
          void fetchTasks()
          void fetchTaskSummary()
        }
```

Replace the detail-event handler summary logic with:

```ts
        if (event.payload.summary) {
          setTaskSummary(event.payload.summary)
        } else {
          void fetchTaskSummary()
        }
        if (event.payload.refresh_tasks) {
          void fetchTasks()
          return
        }
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
          const nextTasks = Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
          setTaskTotal((currentTotal) => Math.max(currentTotal, nextTasks.length))
          return nextTasks
        })
        if (needsRefresh) {
          void fetchTasks()
        }
```

Update the hook dependency array to include `fetchTaskSummary`.

- [ ] **Step 5: Pass summary fetcher from page**

In `frontend/src/pages/crawler/runs/RunDetailPage.tsx`, add the prop:

```tsx
    fetchTaskSummary: detail.fetchTaskSummary,
```

- [ ] **Step 6: Run frontend realtime test and verify pass**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: `run-detail-realtime.ui.test.tsx` passes.

- [ ] **Step 7: Commit Task 4**

```bash
git add frontend/src/realtime/types.ts frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "feat: update crawler run summary from realtime events"
```

---

### Task 5: Final Verification

**Files:**
- Verify only; no planned source edits.

**Interfaces:**
- Consumes: all interfaces produced by Tasks 1-4.
- Produces: verified implementation ready for review or PR.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_realtime_events.py -v
```

Expected: both backend test files pass.

- [ ] **Step 2: Run targeted frontend test**

Run:

```bash
cd frontend
npm test -- run-detail-realtime.ui.test.tsx
```

Expected: frontend realtime detail test file passes.

- [ ] **Step 3: Run frontend typecheck/build**

Run:

```bash
cd frontend
npm run build
```

Expected: TypeScript check and Vite production build pass.

- [ ] **Step 4: Inspect diff for scope**

Run:

```bash
git status --short
git diff --stat HEAD~4..HEAD
```

Expected: committed changes are limited to the backend crawler run API, realtime event publisher, frontend crawler run API/hooks/page, and related tests. Existing unrelated dirty files from before this plan may still appear in `git status --short`; do not revert them.

- [ ] **Step 5: Commit any verification-only test fixture updates**

If Task 5 required no edits, skip this step. If a small test expectation needed adjustment because of exact existing file context, commit only those touched files:

```bash
git add backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_realtime_events.py frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "test: verify crawler run task summary split"
```

Expected: either no commit is needed, or the commit contains only test expectation alignment for the implemented split.

---

## Self-Review

- Spec coverage: Task 1 covers split interfaces and DB summary endpoint; Task 2 covers EventSource summary payload; Tasks 3-4 cover frontend state ownership and realtime/database fallback; Task 5 covers verification.
- Placeholder scan: the plan contains no deferred-work markers or undefined handoff steps.
- Type consistency: `RunTaskSummary`, `getCrawlerRunTaskSummary(runId)`, `fetchTaskSummary()`, and `CrawlerRunDetailUpdatedPayload.summary` are named consistently across tasks.
