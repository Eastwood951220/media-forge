# Crawler Run Detail Logs and Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show detail-stage logs, full-run child task counts, and URL-completion list refreshes on the crawler run detail page.

**Architecture:** Keep the existing run JSONL log stream and run detail page structure. Extend the run tasks API with a full-run summary, extend the existing `crawler.run.detail.updated` realtime event with optional refresh metadata, and render backend-provided summary counts above the child task table.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, pytest, React 19, TypeScript, Ant Design, Vitest.

## Global Constraints

- Detail logs should be written into the existing run-level log timeline.
- Do not add separate per-child-task logs for this change.
- Statistics must come from the backend and represent the whole run, not only the current table page.
- The child task list should refresh after each URL finishes creating its detail tasks.
- The existing response `total` remains the filtered total used by table pagination. The new `summary.total` is the full-run count.
- When a run reaches `completed`, `failed`, or `stopped`, the realtime handler should refresh both logs and tasks so the final table and summary converge.
- Include the threaded crawler coordination rule: each detail worker claims only one pending detail row at a time; after that row is crawled successfully and saved, the worker waits between `DETAIL_PAGE_DELAY_MIN` and `DETAIL_PAGE_DELAY_MAX` before claiming the next row.
- Do not add per-child-task log storage, change crawler execution order beyond the already planned threaded queue work, change movie persistence semantics, or replace the JSONL run log system.

---

## File Structure

- Modify `backend/app/modules/crawler/runs/schemas.py`: add `RunTaskSummary`.
- Modify `backend/app/modules/crawler/runs/router.py`: compute and return `summary` from `/api/crawler/runs/{run_id}/tasks`.
- Modify `backend/app/modules/crawler/runtime/events.py`: allow `crawler.run.detail.updated` to carry `refresh_tasks` and `reason`.
- Modify `backend/app/modules/crawler/runtime/callbacks.py`: add missing detail-stage log context and publish URL-completion refresh after batch creation.
- Coordinate with `backend/app/modules/crawler/runtime/threaded.py` from the threaded queue plan: detail workers must claim one row, process it, save it, sleep, then claim the next row.
- Modify `frontend/src/api/crawlerRun/types.ts`: add `RunTaskSummary` and `CrawlerRunTasksResponse`.
- Modify `frontend/src/api/crawlerRun/index.ts`: return the new task response type.
- Modify `frontend/src/realtime/types.ts`: add optional `refresh_tasks` and `reason` to `CrawlerRunDetailUpdatedPayload`.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`: store `taskSummary` from task fetches.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`: refetch tasks on refresh events and terminal run updates.
- Modify `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`: render a compact summary strip from backend summary.
- Test files: `backend/tests/test_crawler_runs_api.py`, `backend/tests/test_crawler_realtime_events.py`, `backend/tests/test_crawler_worker_service.py`, `frontend/tests/crawler-run-detail.ui.test.tsx`, `frontend/tests/run-detail-realtime.ui.test.tsx`.

---

### Task 1: Backend Task Summary API

**Files:**
- Modify: `backend/app/modules/crawler/runs/schemas.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Produces: `RunTaskSummary` with fields `total`, `pending_crawl`, `crawling`, `saved`, `skipped`, `crawl_failed`, `save_failed`, `completed`, `waiting`, `failed`.
- Produces: `/api/crawler/runs/{run_id}/tasks` response includes `summary`.

- [ ] **Step 1: Write failing API summary tests**

Add this test to `backend/tests/test_crawler_runs_api.py`:

```python
def test_run_tasks_endpoint_returns_full_run_summary(client: TestClient, admin_user) -> None:
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

    response = client.get(
        f"/api/crawler/runs/{run.id}/tasks",
        params={"status": "saved", "page": 1, "size": 1},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["summary"] == {
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

- [ ] **Step 2: Run test to verify failure**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_runs_api.py::test_run_tasks_endpoint_returns_full_run_summary -v`

Expected: FAIL because the response has no `summary`.

- [ ] **Step 3: Add backend schema**

Add to `backend/app/modules/crawler/runs/schemas.py`:

```python
class RunTaskSummary(BaseModel):
    total: int = 0
    pending_crawl: int = 0
    crawling: int = 0
    saved: int = 0
    skipped: int = 0
    crawl_failed: int = 0
    save_failed: int = 0
    completed: int = 0
    waiting: int = 0
    failed: int = 0
```

- [ ] **Step 4: Implement summary aggregation**

In `backend/app/modules/crawler/runs/router.py`, import:

```python
from sqlalchemy import func
from backend.app.modules.crawler.runs.schemas import CrawlRunDetailTaskRead, CrawlRunRead, RunDetailRetryRequest, RunTaskSummary
```

Add helper above `list_run_tasks`:

```python
def _run_task_summary(db: Session, run_id: uuid.UUID) -> dict:
    rows = (
        db.query(CrawlRunDetailTask.status, func.count(CrawlRunDetailTask.id))
        .filter(CrawlRunDetailTask.run_id == run_id)
        .group_by(CrawlRunDetailTask.status)
        .all()
    )
    counts = {status: int(count) for status, count in rows}
    summary = RunTaskSummary(
        total=sum(counts.values()),
        pending_crawl=counts.get("pending_crawl", 0),
        crawling=counts.get("crawling", 0),
        saved=counts.get("saved", 0),
        skipped=counts.get("skipped", 0),
        crawl_failed=counts.get("crawl_failed", 0),
        save_failed=counts.get("save_failed", 0),
    )
    summary.completed = summary.saved + summary.skipped
    summary.waiting = summary.pending_crawl + summary.crawling
    summary.failed = summary.crawl_failed + summary.save_failed
    return summary.model_dump()
```

Update the return in `list_run_tasks`:

```python
payload = paginated(
    rows=[CrawlRunDetailTaskRead.model_validate(r).model_dump(mode="json") for r in rows],
    total=total,
)
payload["summary"] = _run_task_summary(db, run_id)
return payload
```

- [ ] **Step 5: Run tests**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_runs_api.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runs/schemas.py backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: add crawler run task summary"
```

---

### Task 2: Realtime Refresh Signal

**Files:**
- Modify: `backend/app/modules/crawler/runtime/events.py`
- Modify: `backend/app/modules/crawler/runtime/callbacks.py`
- Test: `backend/tests/test_crawler_realtime_events.py`

**Interfaces:**
- Produces: `publish_run_detail_updated(db, run, details, refresh_tasks=False, reason=None) -> None`
- Produces: event payload may include `refresh_tasks: true` and `reason: "url_completed"`.

- [ ] **Step 1: Write failing realtime refresh test**

Add to `backend/tests/test_crawler_realtime_events.py`:

```python
def test_publish_detail_updated_can_request_task_refresh(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="incremental", created_at=datetime.now())
    session.add(run)
    session.commit()
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_detail_updated(session, run, [], refresh_tasks=True, reason="url_completed")

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == ["crawler.run.detail.updated"]
    assert events[0].payload["tasks"] == []
    assert events[0].payload["refresh_tasks"] is True
    assert events[0].payload["reason"] == "url_completed"
```

- [ ] **Step 2: Run test to verify failure**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_realtime_events.py::test_publish_detail_updated_can_request_task_refresh -v`

Expected: FAIL because `publish_run_detail_updated` does not accept refresh metadata.

- [ ] **Step 3: Extend event publisher**

Change `publish_run_detail_updated` signature in `events.py`:

```python
def publish_run_detail_updated(
    db: Session,
    run: CrawlRun,
    details: list[CrawlRunDetailTask],
    *,
    refresh_tasks: bool = False,
    reason: str | None = None,
) -> None:
```

Build payload like this before publishing:

```python
payload = {
    "run_id": str(run.id),
    "tasks": detail_payloads,
}
if refresh_tasks:
    payload["refresh_tasks"] = True
if reason is not None:
    payload["reason"] = reason
```

Use `payload=payload` in `make_realtime_event`.

- [ ] **Step 4: Publish URL-completion refresh after batch creation**

In `callbacks.py`, after the existing `publish_run_detail_updated(ctx.db, ctx.run, created_details)` in `on_tasks_batch_created`, add:

```python
publish_run_detail_updated(
    ctx.db,
    ctx.run,
    [],
    refresh_tasks=True,
    reason="url_completed",
)
```

This emits a page-level refresh signal after each batch of child tasks is persisted. In the threaded queue implementation, call this same publisher after a URL worker finishes persisting all child tasks for that URL.

- [ ] **Step 5: Run realtime tests**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_realtime_events.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/events.py backend/app/modules/crawler/runtime/callbacks.py backend/tests/test_crawler_realtime_events.py
git commit -m "feat: refresh run tasks after url completion"
```

---

### Task 3: Detail Logs With Context

**Files:**
- Modify: `backend/app/modules/crawler/runtime/callbacks.py`
- Test: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes: `append_run_log_for_run(db, run, message, level, **context)`
- Produces: detail-stage log messages in existing run log stream.

- [ ] **Step 1: Write failing detail log test**

Add to `backend/tests/test_crawler_worker_service.py`:

```python
def test_callbacks_write_detail_logs_with_context(db_session, admin_user, monkeypatch, tmp_path) -> None:
    from backend.app.modules.crawler.runs import logs as run_logs
    from backend.app.modules.crawler.runtime.callbacks import CrawlerCallbackContext, build_crawl_callbacks
    from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
    from backend.app.modules.crawler.runtime.progress import new_progress

    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))
    task = CrawlTask(name="任务-log-context", owner_id=admin_user.id, is_skip=False)
    db_session.add(task)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="incremental", queued_at=datetime.now())
    db_session.add(run)
    db_session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code="LOG-001",
        source_url="https://javdb.com/v/log001",
        source_name="LOG 001",
        source_url_name="演员A",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()

    index = DetailTaskIndex()
    index.remember(detail)

    class Runtime:
        def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
            return None

        def is_stop_requested(self, run_id: str) -> bool:
            return False

    callbacks = build_crawl_callbacks(CrawlerCallbackContext(
        db=db_session,
        run=run,
        task=task,
        runtime=Runtime(),
        detail_index=index,
        progress=new_progress(),
    ))

    callbacks.log_callback("[任务-log-context][URL: 演员A] 详情开始: code=LOG-001 name=LOG 001", "INFO")
    callbacks.on_item_saved(
        {"code": "LOG-001", "url": "https://javdb.com/v/log001", "name": "LOG 001"},
        {"code": "LOG-001", "source_url": "https://javdb.com/v/log001", "source_name": "LOG 001"},
    )

    loaded = run_logs.load_run_logs(str(run.id))
    assert any("详情开始" in entry["message"] for entry in loaded)
    saved_entry = next(entry for entry in loaded if "入库成功" in entry["message"])
    assert saved_entry["context"]["code"] == "LOG-001"
    assert saved_entry["context"]["detail_id"] == str(detail.id)
    assert saved_entry["context"]["source_url"] == "https://javdb.com/v/log001"
    assert saved_entry["context"]["source_url_name"] == "演员A"
    assert saved_entry["context"]["detail_status"] == "saved"
```

- [ ] **Step 2: Run test to verify failure**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_worker_service.py::test_callbacks_write_detail_logs_with_context -v`

Expected: FAIL because save log context lacks detail metadata.

- [ ] **Step 3: Add detail log context helper**

In `callbacks.py`, add inside `build_crawl_callbacks` after `active_indexed_detail`:

```python
def detail_log_context(
    task_info: dict[str, Any],
    detail: CrawlRunDetailTask | None,
    *,
    item_data: dict[str, Any] | None = None,
    detail_status: str | None = None,
) -> dict[str, Any]:
    item_data = item_data or {}
    context: dict[str, Any] = {
        "code": item_data.get("code") or task_info.get("code"),
        "source_url": task_info.get("url") or item_data.get("source_url"),
        "source_url_name": task_info.get("_task_url_name"),
        "detail_status": detail_status,
    }
    if detail is not None:
        context["detail_id"] = str(detail.id)
        context["source_url"] = detail.source_url or context.get("source_url")
        context["source_url_name"] = detail.source_url_name or context.get("source_url_name")
    return {key: value for key, value in context.items() if value is not None}
```

- [ ] **Step 4: Use context in save, fail, skip logs**

Update `on_item_saved` success log:

```python
append_run_log_for_run(
    ctx.db,
    ctx.run,
    f"入库成功: {code}",
    "INFO",
    **detail_log_context(task_info, detail, item_data=item_data, detail_status="saved"),
    movie_id=str(movie_id),
)
```

Update save failure log:

```python
append_run_log_for_run(
    ctx.db,
    ctx.run,
    f"入库失败: {code}: {exc}",
    "ERROR",
    **detail_log_context(task_info, detail, item_data=item_data, detail_status="save_failed"),
)
```

Update `on_detail_failed` log:

```python
append_run_log_for_run(
    ctx.db,
    ctx.run,
    f"详情失败: {task_info.get('code') or task_info.get('url')}: {error}",
    "ERROR",
    **detail_log_context(task_info, detail, detail_status="crawl_failed"),
)
```

Update `on_item_already_exists` log:

```python
append_run_log_for_run(
    ctx.db,
    ctx.run,
    f"跳过已存在影片并追加任务ID: {code}",
    "INFO",
    **detail_log_context(task_info, detail, detail_status="skipped"),
)
```

- [ ] **Step 5: Coordinate detail worker start and delay logs**

In the threaded queue plan implementation, when `backend/app/modules/crawler/runtime/threaded.py` is added, ensure each detail worker does:

```python
append_run_log_for_run(
    worker_db,
    run,
    f"[{task_name}][URL: {detail.source_url_name or detail.task_url_type or '-'}] 详情开始: code={detail.code} name={detail.source_name}",
    "INFO",
    detail_id=str(detail.id),
    code=detail.code,
    source_url=detail.source_url,
    source_url_name=detail.source_url_name,
    detail_status="crawling",
)
```

The same worker must claim exactly one pending row, crawl and save that row, commit it, then wait:

```python
random_sleep(config.DETAIL_PAGE_DELAY_MIN, config.DETAIL_PAGE_DELAY_MAX)
```

before claiming the next row. This delay applies after successful crawl and save; applying it after failures is allowed to preserve detail-page throttling.

- [ ] **Step 6: Run worker service tests**

Run: `source .venv/bin/activate && python -m pytest backend/tests/test_crawler_worker_service.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/callbacks.py backend/tests/test_crawler_worker_service.py
git commit -m "feat: add crawler detail log context"
```

---

### Task 4: Frontend Types and Summary State

**Files:**
- Modify: `frontend/src/api/crawlerRun/types.ts`
- Modify: `frontend/src/api/crawlerRun/index.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- Test: `frontend/tests/crawler-run-detail.ui.test.tsx`

**Interfaces:**
- Produces: `RunTaskSummary`
- Produces: `CrawlerRunTasksResponse = PaginatedResponse<CrawlRunDetailTask> & { summary: RunTaskSummary }`
- Produces: `useRunDetail(...).taskSummary`

- [ ] **Step 1: Update mocked API response in test**

In `frontend/tests/crawler-run-detail.ui.test.tsx`, change the task mock to include summary:

```ts
vi.mocked(getCrawlerRunTasks).mockResolvedValue({
  rows: [],
  total: 0,
  summary: {
    total: 6,
    pending_crawl: 1,
    crawling: 1,
    saved: 1,
    skipped: 1,
    crawl_failed: 1,
    save_failed: 1,
    completed: 2,
    waiting: 2,
    failed: 2,
  },
})
```

Add a rendering assertion:

```ts
it('renders full-run child task summary from API', async () => {
  renderDetailPage()

  expect(await screen.findByText('总数')).toBeInTheDocument()
  expect(screen.getByText('6')).toBeInTheDocument()
  expect(screen.getByText('完成')).toBeInTheDocument()
  expect(screen.getByText('等待')).toBeInTheDocument()
  expect(screen.getByText('失败')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend && npm test -- crawler-run-detail.ui.test.tsx`

Expected: FAIL because summary types/state/UI are missing.

- [ ] **Step 3: Add TypeScript response types**

In `frontend/src/api/crawlerRun/types.ts`, add:

```ts
export interface RunTaskSummary {
  total: number
  pending_crawl: number
  crawling: number
  saved: number
  skipped: number
  crawl_failed: number
  save_failed: number
  completed: number
  waiting: number
  failed: number
}
```

In `frontend/src/api/crawlerRun/index.ts`, import `RunTaskSummary` and add:

```ts
export type CrawlerRunTasksResponse = PaginatedResponse<CrawlRunDetailTask> & {
  summary: RunTaskSummary
}
```

Change `getCrawlerRunTasks` return type:

```ts
): Promise<CrawlerRunTasksResponse> {
```

- [ ] **Step 4: Store summary in hook**

In `useRunDetail.ts`, import `RunTaskSummary`, add default summary:

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
```

Add state:

```ts
const [taskSummary, setTaskSummary] = useState<RunTaskSummary>(emptyTaskSummary)
```

Reset on run id change:

```ts
setTaskSummary(emptyTaskSummary)
```

Update in `fetchTasks`:

```ts
setTasks(data.rows)
setTaskTotal(data.total)
setTaskSummary(data.summary)
```

Return `taskSummary`.

- [ ] **Step 5: Run frontend detail test**

Run: `cd frontend && npm test -- crawler-run-detail.ui.test.tsx`

Expected: still FAIL until UI renders summary in Task 5.

- [ ] **Step 6: Commit after Task 5 passes**

Do not commit this task alone if the test remains red. Commit with Task 5 once the UI is added.

---

### Task 5: Frontend Summary UI

**Files:**
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Modify: `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
- Test: `frontend/tests/crawler-run-detail.ui.test.tsx`

**Interfaces:**
- Consumes: `taskSummary: RunTaskSummary`
- Produces: compact summary strip above child task filters/table.

- [ ] **Step 1: Pass summary into table**

In `RunDetailPage.tsx`, add:

```tsx
summary={detail.taskSummary}
```

to `RunTaskTable`.

- [ ] **Step 2: Add prop and render summary strip**

In `RunTaskTable.tsx`, import:

```ts
import type { CrawlRunDetailTask, RunTaskSummary } from '@/api/crawlerRun/types'
```

Add prop:

```ts
summary: RunTaskSummary
```

Render before the filter `Space`:

```tsx
<Space size={12} wrap style={{ marginBottom: 16 }}>
  {[
    ['总数', summary.total],
    ['完成', summary.completed],
    ['等待', summary.waiting],
    ['跳过', summary.skipped],
    ['失败', summary.failed],
  ].map(([label, value]) => (
    <div
      key={label}
      style={{
        minWidth: 88,
        padding: '8px 12px',
        border: '1px solid rgba(5, 5, 5, 0.08)',
        borderRadius: 6,
      }}
    >
      <div style={{ fontSize: 12, color: 'rgba(0, 0, 0, 0.45)' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
    </div>
  ))}
</Space>
```

- [ ] **Step 3: Run frontend detail test**

Run: `cd frontend && npm test -- crawler-run-detail.ui.test.tsx`

Expected: PASS.

- [ ] **Step 4: Commit frontend summary changes**

```bash
git add frontend/src/api/crawlerRun/types.ts frontend/src/api/crawlerRun/index.ts frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/src/pages/crawler/runs/components/RunTaskTable.tsx frontend/tests/crawler-run-detail.ui.test.tsx
git commit -m "feat: show crawler run task summary"
```

---

### Task 6: Frontend Realtime Refetch Behavior

**Files:**
- Modify: `frontend/src/realtime/types.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
- Test: `frontend/tests/run-detail-realtime.ui.test.tsx`

**Interfaces:**
- Consumes: optional realtime payload fields `refresh_tasks?: boolean` and `reason?: string`.
- Produces: terminal run updates and URL completion refresh events call `fetchTasks()`.

- [ ] **Step 1: Write failing realtime tests**

In `frontend/tests/run-detail-realtime.ui.test.tsx`, update all mocked `getCrawlerRunTasks` responses to include:

```ts
summary: {
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
},
```

Add:

```ts
it('refetches tasks when a url completion refresh event arrives', async () => {
  renderPage()
  await screen.findByText('运行详情 - 任务A')

  const initialTasksCalls = vi.mocked(getCrawlerRunTasks).mock.calls.length

  emit('crawler.run.detail.updated', {
    run_id: 'run-1',
    tasks: [],
    refresh_tasks: true,
    reason: 'url_completed',
  })

  await waitFor(() => {
    expect(vi.mocked(getCrawlerRunTasks).mock.calls.length).toBeGreaterThan(initialTasksCalls)
  })
})
```

Update the terminal run test to also expect task calls increase:

```ts
const initialTasksCalls = vi.mocked(getCrawlerRunTasks).mock.calls.length
...
expect(vi.mocked(getCrawlerRunTasks).mock.calls.length).toBeGreaterThan(initialTasksCalls)
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend && npm test -- run-detail-realtime.ui.test.tsx`

Expected: FAIL because refresh payloads and terminal task refetch are not handled yet.

- [ ] **Step 3: Extend realtime type**

In `frontend/src/realtime/types.ts`, change:

```ts
export type CrawlerRunDetailUpdatedPayload = {
  run_id: string
  tasks: CrawlRunDetailTask[]
  refresh_tasks?: boolean
  reason?: string
}
```

- [ ] **Step 4: Refetch on refresh events**

In `useRunDetailRealtime.ts`, inside the detail update handler after run id checks:

```ts
if (event.payload.refresh_tasks) {
  void fetchTasks()
  return
}
```

Inside terminal run update handling, call both:

```ts
if (['completed', 'failed', 'stopped'].includes(event.payload.status)) {
  void fetchLogs()
  void fetchTasks()
}
```

- [ ] **Step 5: Run realtime tests**

Run: `cd frontend && npm test -- run-detail-realtime.ui.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/realtime/types.ts frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "feat: refetch crawler run tasks from realtime"
```

---

### Task 7: Regression Verification

**Files:**
- Modify only files already touched if tests expose small integration mismatches.

**Interfaces:**
- Consumes: all previous task deliverables.
- Produces: verified backend and frontend behavior.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_crawler_runs_api.py \
  backend/tests/test_crawler_realtime_events.py \
  backend/tests/test_crawler_worker_service.py \
  backend/tests/test_crawler_run_logs.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend
npm test -- crawler-run-detail.ui.test.tsx run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Inspect scope**

Run:

```bash
git status --short
git diff --stat
```

Expected: only run detail visibility files, tests, and planned crawler runtime coordination files are changed.

- [ ] **Step 5: Commit final cleanup if needed**

If Step 4 shows small integration fixes not already committed:

```bash
git add <specific-files>
git commit -m "test: verify crawler run detail visibility"
```

If there are no uncommitted implementation changes, do not create an empty commit.

---

## Self-Review

- Spec coverage: Tasks cover backend summary, detail logs, URL completion refresh event, frontend summary display, realtime refetch behavior, and final verification.
- User-added constraint coverage: Task 3 explicitly records the detail worker rule that each worker claims one row, saves it, waits between `DETAIL_PAGE_DELAY_MIN` and `DETAIL_PAGE_DELAY_MAX`, then claims the next row.
- Deferred work scan: The plan contains no unresolved placeholders or open-ended deferred steps.
- Type consistency: The plan consistently uses `RunTaskSummary`, `CrawlerRunTasksResponse`, `refresh_tasks`, `reason`, and `taskSummary`.
