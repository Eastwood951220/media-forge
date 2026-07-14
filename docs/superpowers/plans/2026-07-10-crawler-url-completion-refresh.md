# Crawler URL Completion Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish an EventSource refresh signal after each crawler URL list phase completes so the crawler run detail page reloads the subtask list.

**Architecture:** Reuse the existing `crawler.run.detail.updated` event with `refresh_tasks: true` and `reason: "url_completed"`. The frontend already handles this signal in `useRunDetailRealtime` by calling `fetchTasks()`, so implementation is backend-focused: the threaded crawler list phase must publish the same refresh signal after each completed URL batch is committed.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, pytest, React 19, TypeScript 6, Vitest 3.

## Global Constraints

- Project scope remains the Media Forge refactor and optimization of `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.
- Do not replace EventSource with WebSocket.
- Do not change crawler scheduling, scraping behavior, database schema, or frontend routes.
- Existing event names stay unchanged: `crawler.run.detail.updated` and `system.resync_required`.
- Use the existing frontend behavior: `refresh_tasks: true` on `crawler.run.detail.updated` triggers `fetchTasks()`.
- Keep this change scoped to each URL completion in crawler list phase; do not add polling.

---

## File Structure

- Modify `backend/app/modules/crawler/runtime/threaded.py`
  - Import and call `publish_run_detail_updated`.
  - Publish `crawler.run.detail.updated` with empty `tasks`, `refresh_tasks=True`, and `reason="url_completed"` after each URL future result is persisted and committed.
- Modify `backend/tests/test_crawler_threaded_url_completion_refresh.py`
  - New focused unit test for `_run_list_phase` verifying one refresh event per completed URL.
- Verify `frontend/tests/run-detail-realtime.ui.test.tsx`
  - Existing test already asserts `refresh_tasks: true` with `reason="url_completed"` causes `getCrawlerRunTasks()` to be called again.

### Task 1: Publish URL Completion Refresh From Threaded List Phase

**Files:**
- Create: `backend/tests/test_crawler_threaded_url_completion_refresh.py`
- Modify: `backend/app/modules/crawler/runtime/threaded.py`

**Interfaces:**
- Consumes:
  - `publish_run_detail_updated(db: Session, run: CrawlRun, details: list[CrawlRunDetailTask], *, refresh_tasks: bool = False, reason: str | None = None) -> None`
  - `_run_list_phase(db: Session, run: CrawlRun, task: CrawlTask, runtime: Any, config: Any) -> None`
- Produces:
  - After each completed URL future is committed, one `crawler.run.detail.updated` event with payload:
    ```python
    {"run_id": str(run.id), "tasks": [], "refresh_tasks": True, "reason": "url_completed"}
    ```

- [ ] **Step 1: Write the failing backend test**

Create `backend/tests/test_crawler_threaded_url_completion_refresh.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.runtime import threaded
from backend.app.modules.realtime.bus import event_bus
from backend.tests.conftest import TestingSessionLocal


@dataclass
class FakeConfig:
    LIST_MAX_WORKERS: int = 1
    INCREMENTAL_EXIST_THRESHOLD: int = 5


class FakeRuntime:
    def is_stop_requested(self, _run_id: str) -> bool:
        return False


class FakeSpider:
    def collect_detail_tasks_for_url(self, *, url_entry, task_name, crawl_mode, incremental_threshold, stop_check, log_callback, db_check_callback, on_item_already_exists):
        log_callback(f"URL完成: {url_entry.url}", "INFO")
        return [
            {
                "code": f"AAA-{url_entry.position:03d}",
                "url": url_entry.url,
                "name": f"影片{url_entry.position}",
                "_task_url_name": url_entry.url_name,
                "_task_url": url_entry.url,
                "_task_final_url": url_entry.final_url,
                "_task_url_type": url_entry.url_type,
            }
        ]


def drain(queue):
    rows = []
    while not queue.empty():
        rows.append(queue.get_nowait())
    return rows


def test_threaded_list_phase_publishes_refresh_after_each_url_completion(admin_user, monkeypatch) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    session.add_all([
        CrawlTaskUrl(
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
        ),
        CrawlTaskUrl(
            task_id=task.id,
            position=2,
            url="https://example.test/list-2",
            url_type="list",
            has_magnet=True,
            has_chinese_sub=False,
            sort_type=0,
            source="javdb",
            final_url="https://example.test/list-2?page=1",
            url_name="入口2",
        ),
    ])
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

    monkeypatch.setattr(threaded, "build_spider", lambda: FakeSpider())
    monkeypatch.setattr(
        threaded,
        "_find_existing_movie_codes_in_worker_session",
        lambda session_factory, codes, task_id, db_lock: set(),
    )

    queue = event_bus.subscribe(str(admin_user.id))
    try:
        threaded._run_list_phase(session, run, task, FakeRuntime(), FakeConfig())

        events = drain(queue)
    finally:
        event_bus.unsubscribe(str(admin_user.id), queue)
        session.close()

    refresh_events = [
        event for event in events
        if event.event == "crawler.run.detail.updated"
        and event.payload.get("refresh_tasks") is True
        and event.payload.get("reason") == "url_completed"
    ]
    assert len(refresh_events) == 2
    assert all(event.resource_id == str(run.id) for event in refresh_events)
    assert all(event.payload["tasks"] == [] for event in refresh_events)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py -v
```

Expected: FAIL because `_run_list_phase` currently commits each URL batch and writes a log but does not publish a `refresh_tasks` EventSource signal.

- [ ] **Step 3: Implement the URL completion refresh event**

In `backend/app/modules/crawler/runtime/threaded.py`, change the event import from:

```python
from backend.app.modules.crawler.runtime.events import append_run_log_for_run
```

to:

```python
from backend.app.modules.crawler.runtime.events import append_run_log_for_run, publish_run_detail_updated
```

In `_run_list_phase`, after the existing `db.commit()` inside the `for future in as_completed(futures)` loop, add:

```python
                publish_run_detail_updated(
                    db,
                    run,
                    [],
                    refresh_tasks=True,
                    reason="url_completed",
                )
```

The block should read:

```python
        for future in as_completed(futures):
            with list_db_lock:
                for item in future.result():
                    upsert_detail_task(db, run=run, task_name=task_name, item=item)
                db.commit()
                publish_run_detail_updated(
                    db,
                    run,
                    [],
                    refresh_tasks=True,
                    reason="url_completed",
                )
                append_run_log_for_run(db, run, "列表批次已持久化，刷新详情子任务", "INFO")
```

- [ ] **Step 4: Run backend test to verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py -v
```

Expected: PASS.

- [ ] **Step 5: Run crawler realtime regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py backend/tests/test_crawler_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_threaded_url_completion_refresh.py
git commit -m "feat: refresh crawler subtasks after each url"
```

### Task 2: Verify Frontend EventSource Refresh Behavior

**Files:**
- Verify: `frontend/tests/run-detail-realtime.ui.test.tsx`
- Modify only if needed: `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`

**Interfaces:**
- Consumes existing event payload:
  ```ts
  {
    run_id: string
    tasks: []
    refresh_tasks: true
    reason: 'url_completed'
  }
  ```
- Produces: `fetchTasks()` is called once for each received URL completion refresh event whose `resource_id` and `payload.run_id` match the current run.

- [ ] **Step 1: Strengthen the frontend test**

In `frontend/tests/run-detail-realtime.ui.test.tsx`, replace the existing `refetches tasks when a url completion refresh event arrives` test with:

```tsx
  it('refetches tasks for each url completion refresh event', async () => {
    renderPage()
    await screen.findByText('运行详情 - 任务A')

    const initialTasksCalls = vi.mocked(getCrawlerRunTasks).mock.calls.length

    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
      refresh_tasks: true,
      reason: 'url_completed',
    })
    emit('crawler.run.detail.updated', {
      run_id: 'run-1',
      tasks: [],
      refresh_tasks: true,
      reason: 'url_completed',
    })

    await waitFor(() => {
      expect(vi.mocked(getCrawlerRunTasks).mock.calls.length).toBeGreaterThanOrEqual(initialTasksCalls + 2)
    })
  })
```

- [ ] **Step 2: Run frontend test**

Run:

```bash
cd frontend && npm test -- tests/run-detail-realtime.ui.test.tsx -t "refetches tasks for each url completion refresh event"
```

Expected: PASS if the current hook handles every `refresh_tasks` event. If it fails because events are coalesced or ignored, update `useRunDetailRealtime.ts` so the `refresh_tasks` branch directly calls `void fetchTasks()` for every matching event:

```ts
        if (event.payload.refresh_tasks) {
          void fetchTasks()
          return
        }
```

- [ ] **Step 3: Run frontend realtime regression tests**

Run:

```bash
cd frontend && npm test -- tests/run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Commit**

If only the test changed:

```bash
git add frontend/tests/run-detail-realtime.ui.test.tsx
git commit -m "test: cover repeated crawler url refresh events"
```

If production code also changed:

```bash
git add frontend/tests/run-detail-realtime.ui.test.tsx frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts
git commit -m "fix: refresh crawler subtasks for each url event"
```

### Task 3: Final Verification

**Files:**
- Verify all files changed by Tasks 1-2.

**Interfaces:**
- Consumes completed backend EventSource publishing and frontend refresh handling.
- Produces verified end-to-end behavior at the unit/integration-test level.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_url_completion_refresh.py backend/tests/test_crawler_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd frontend && npm test -- tests/run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit verification fixes if needed**

If verification required fixes:

```bash
git add backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_threaded_url_completion_refresh.py frontend/tests/run-detail-realtime.ui.test.tsx frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts
git commit -m "fix: stabilize crawler url refresh verification"
```

If no files changed during verification, do not create an empty commit.

## Self-Review

- Spec coverage: Task 1 publishes an EventSource refresh event after every completed URL batch; Task 2 verifies the frontend calls the subtask list refresh once per received event; Task 3 verifies backend and frontend behavior.
- Placeholder scan: no forbidden placeholder wording remains.
- Type consistency: `publish_run_detail_updated(..., refresh_tasks=True, reason="url_completed")` matches the existing frontend `CrawlerRunDetailUpdatedPayload` and `useRunDetailRealtime` refresh branch.
