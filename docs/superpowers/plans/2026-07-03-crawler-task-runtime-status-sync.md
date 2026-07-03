# Crawler Task Runtime Status Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the crawler task list display and react to each task's current runtime state, derived from the latest crawler run.

**Architecture:** Keep `crawl_runs` as the source of truth and add a backend snapshot helper that derives task runtime status without adding task-table state. Publish `crawler.task.status.updated` through the existing `/api/events/stream` realtime bus whenever a run status changes. The frontend loads task cards and runtime snapshots separately, then keeps them synchronized through EventSource events and explicit refreshes after actions.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest, React 19, TypeScript 6, Ant Design 6, Vitest, React Testing Library.

## Global Constraints

- Do not add a persisted task runtime status column.
- Derive task status from each task's latest `crawl_runs` row.
- Map `queued` to `queued`, `running` to `running`, `stopped` to `stopped`, and `completed` / `failed` / no run to `idle`.
- Label task runtime states as 空闲中, 运行中, 排队中, 停止中.
- Only `idle` tasks can run or delete.
- `queued` and `running` tasks show stop and no other task-list operation.
- `stopped` tasks show restart and no other task-list operation.
- Reuse the existing user-scoped realtime stream at `GET /api/events/stream`.
- Stay within the crawler refactor scope; do not add scheduling, batch run-all, per-detail-task retry, or unrelated media operations.

---

## File Structure

- Create `backend/app/modules/crawler/tasks/runtime_status.py`: derives task runtime snapshots, aggregate stats, and delete eligibility.
- Modify `backend/app/schemas/crawl_task.py`: add Pydantic schemas for runtime status snapshots and stats.
- Modify `backend/app/modules/crawler/tasks/router.py`: add `GET /api/crawler/tasks/statuses` and enforce non-idle delete rejection.
- Modify `backend/app/modules/crawler/runtime/service.py`: publish `crawler.task.status.updated` beside run status updates.
- Modify `frontend/src/api/crawlTask/types.ts`: add `TaskRuntimeStatus`, `CrawlTaskRuntimeSnapshot`, and `CrawlTaskRuntimeStatusResponse`.
- Modify `frontend/src/api/crawlTask/index.ts`: add `getCrawlTaskRuntimeStatuses()`.
- Modify `frontend/src/realtime/types.ts`: add `CrawlerTaskStatusUpdatedPayload` and the new event name.
- Modify `frontend/src/realtime/eventSourceClient.ts`: subscribe to `crawler.task.status.updated`.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`: load snapshots, render runtime stats, wire stop/restart/realtime refresh.
- Modify `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`: render runtime status tags and enforce action availability.
- Test `backend/tests/test_crawl_tasks_api.py`: status endpoint and delete guard.
- Test `backend/tests/test_crawler_realtime_events.py`: task status realtime payload.
- Test `frontend/tests/realtime-event-source-client.test.ts`: new event delivery.
- Test `frontend/tests/crawler-run-controls.ui.test.tsx`: task list runtime controls.

---

### Task 1: Backend Runtime Status Snapshot Endpoint

**Files:**
- Create: `backend/app/modules/crawler/tasks/runtime_status.py`
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Test: `backend/tests/test_crawl_tasks_api.py`

**Interfaces:**
- Produces: `derive_runtime_status(latest_run_status: str | None) -> Literal["idle", "queued", "running", "stopped"]`
- Produces: `build_task_runtime_status_response(db: Session, owner_id: uuid.UUID) -> CrawlTaskRuntimeStatusResponse`
- Produces: `get_task_runtime_status(db: Session, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlTaskRuntimeSnapshot | None`
- Produces: `GET /api/crawler/tasks/statuses`

- [ ] **Step 1: Write failing backend tests for derived snapshots**

Append these tests to `backend/tests/test_crawl_tasks_api.py`:

```python
    def test_task_runtime_statuses_derive_from_latest_runs(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        idle_task = CrawlTask(name="从未运行", storage_location="IDLE", owner_id=admin_user.id)
        completed_task = CrawlTask(name="已完成任务", storage_location="DONE", owner_id=admin_user.id)
        failed_task = CrawlTask(name="失败任务", storage_location="FAIL", owner_id=admin_user.id)
        queued_task = CrawlTask(name="排队任务", storage_location="QUEUE", owner_id=admin_user.id)
        running_task = CrawlTask(name="运行任务", storage_location="RUN", owner_id=admin_user.id)
        stopped_task = CrawlTask(name="停止任务", storage_location="STOP", owner_id=admin_user.id)
        session.add_all([idle_task, completed_task, failed_task, queued_task, running_task, stopped_task])
        session.flush()
        session.add_all([
            CrawlRun(task_id=completed_task.id, task_name=completed_task.name, status="completed", crawl_mode="incremental", created_at=datetime(2026, 7, 3, 1, 0, 0)),
            CrawlRun(task_id=failed_task.id, task_name=failed_task.name, status="failed", crawl_mode="incremental", created_at=datetime(2026, 7, 3, 2, 0, 0)),
            CrawlRun(task_id=queued_task.id, task_name=queued_task.name, status="queued", crawl_mode="incremental", created_at=datetime(2026, 7, 3, 3, 0, 0)),
            CrawlRun(task_id=running_task.id, task_name=running_task.name, status="running", crawl_mode="incremental", created_at=datetime(2026, 7, 3, 4, 0, 0)),
            CrawlRun(task_id=stopped_task.id, task_name=stopped_task.name, status="stopped", crawl_mode="incremental", created_at=datetime(2026, 7, 3, 5, 0, 0)),
        ])
        task_ids = {
            "idle": str(idle_task.id),
            "completed": str(completed_task.id),
            "failed": str(failed_task.id),
            "queued": str(queued_task.id),
            "running": str(running_task.id),
            "stopped": str(stopped_task.id),
        }
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks/statuses", headers=headers)

        assert response.status_code == HTTPStatus.OK
        payload = response.json()["data"]
        by_task = {row["task_id"]: row for row in payload["tasks"]}
        assert by_task[task_ids["idle"]]["runtime_status"] == "idle"
        assert by_task[task_ids["completed"]]["runtime_status"] == "idle"
        assert by_task[task_ids["failed"]]["runtime_status"] == "idle"
        assert by_task[task_ids["queued"]]["runtime_status"] == "queued"
        assert by_task[task_ids["running"]]["runtime_status"] == "running"
        assert by_task[task_ids["stopped"]]["runtime_status"] == "stopped"
        assert payload["stats"] == {
            "total": 6,
            "idle": 3,
            "running": 1,
            "queued": 1,
            "stopped": 1,
        }

    def test_task_runtime_statuses_use_newest_run_per_task(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        task = CrawlTask(name="多次运行", storage_location="MULTI", owner_id=admin_user.id)
        session.add(task)
        session.flush()
        session.add_all([
            CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="incremental", created_at=datetime(2026, 7, 2, 8, 0, 0)),
            CrawlRun(task_id=task.id, task_name=task.name, status="completed", crawl_mode="full", created_at=datetime(2026, 7, 3, 8, 0, 0)),
        ])
        task_id = str(task.id)
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks/statuses", headers=headers)

        assert response.status_code == HTTPStatus.OK
        row = response.json()["data"]["tasks"][0]
        assert row["task_id"] == task_id
        assert row["runtime_status"] == "idle"
        assert row["latest_run_status"] == "completed"
        assert row["last_run_at"].startswith("2026-07-03T08:00:00")
    ```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_task_runtime_statuses_derive_from_latest_runs backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_task_runtime_statuses_use_newest_run_per_task -v
```

Expected: both tests fail with `404 Not Found` for `/api/crawler/tasks/statuses`.

- [ ] **Step 3: Add runtime status schemas**

In `backend/app/schemas/crawl_task.py`, add these imports and models:

```python
from typing import Literal
```

```python
TaskRuntimeStatus = Literal["idle", "queued", "running", "stopped"]


class CrawlTaskRuntimeSnapshot(BaseModel):
    task_id: uuid.UUID
    runtime_status: TaskRuntimeStatus
    latest_run_id: uuid.UUID | None = None
    latest_run_status: str | None = None
    last_run_at: datetime | None = None


class CrawlTaskRuntimeStats(BaseModel):
    total: int
    idle: int
    running: int
    queued: int
    stopped: int


class CrawlTaskRuntimeStatusResponse(BaseModel):
    tasks: list[CrawlTaskRuntimeSnapshot]
    stats: CrawlTaskRuntimeStats
```

- [ ] **Step 4: Add runtime status helper**

Create `backend/app/modules/crawler/tasks/runtime_status.py`:

```python
import uuid
from typing import Literal

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.schemas.crawl_task import (
    CrawlTaskRuntimeSnapshot,
    CrawlTaskRuntimeStats,
    CrawlTaskRuntimeStatusResponse,
)

TaskRuntimeStatus = Literal["idle", "queued", "running", "stopped"]

ACTIVE_RUN_STATUSES = {"queued", "running", "stopped"}


def derive_runtime_status(latest_run_status: str | None) -> TaskRuntimeStatus:
    if latest_run_status == "queued":
        return "queued"
    if latest_run_status == "running":
        return "running"
    if latest_run_status == "stopped":
        return "stopped"
    return "idle"


def _latest_runs_by_task(db: Session, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, CrawlRun]:
    if not task_ids:
        return {}
    rows = (
        db.query(CrawlRun)
        .filter(CrawlRun.task_id.in_(task_ids))
        .order_by(CrawlRun.task_id.asc(), CrawlRun.created_at.desc())
        .all()
    )
    latest: dict[uuid.UUID, CrawlRun] = {}
    for row in rows:
        if row.task_id is not None and row.task_id not in latest:
            latest[row.task_id] = row
    return latest


def build_task_runtime_snapshot(task: CrawlTask, latest_run: CrawlRun | None) -> CrawlTaskRuntimeSnapshot:
    return CrawlTaskRuntimeSnapshot(
        task_id=task.id,
        runtime_status=derive_runtime_status(latest_run.status if latest_run else None),
        latest_run_id=latest_run.id if latest_run else None,
        latest_run_status=latest_run.status if latest_run else None,
        last_run_at=latest_run.created_at if latest_run else None,
    )


def build_task_runtime_status_response(db: Session, owner_id: uuid.UUID) -> CrawlTaskRuntimeStatusResponse:
    tasks = (
        db.query(CrawlTask)
        .filter(CrawlTask.owner_id == owner_id)
        .order_by(CrawlTask.created_at.desc())
        .all()
    )
    latest_runs = _latest_runs_by_task(db, [task.id for task in tasks])
    snapshots = [build_task_runtime_snapshot(task, latest_runs.get(task.id)) for task in tasks]
    counts = {"idle": 0, "running": 0, "queued": 0, "stopped": 0}
    for snapshot in snapshots:
        counts[snapshot.runtime_status] += 1
    return CrawlTaskRuntimeStatusResponse(
        tasks=snapshots,
        stats=CrawlTaskRuntimeStats(
            total=len(snapshots),
            idle=counts["idle"],
            running=counts["running"],
            queued=counts["queued"],
            stopped=counts["stopped"],
        ),
    )


def get_task_runtime_status(
    db: Session,
    task_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> CrawlTaskRuntimeSnapshot | None:
    task = db.query(CrawlTask).filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id).first()
    if task is None:
        return None
    latest_run = (
        db.query(CrawlRun)
        .filter(CrawlRun.task_id == task_id)
        .order_by(CrawlRun.created_at.desc())
        .first()
    )
    return build_task_runtime_snapshot(task, latest_run)
```

- [ ] **Step 5: Add the API route**

In `backend/app/modules/crawler/tasks/router.py`, import the helper:

```python
from backend.app.modules.crawler.tasks.runtime_status import build_task_runtime_status_response
```

Add this route above `@router.get("/{task_id}")`:

```python
@router.get("/statuses")
def list_task_runtime_statuses(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    payload = build_task_runtime_status_response(db, current_user.id)
    return success(data=payload.model_dump(mode="json"))
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_task_runtime_statuses_derive_from_latest_runs backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_task_runtime_statuses_use_newest_run_per_task -v
```

Expected: both tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/tasks/runtime_status.py backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat: add crawler task runtime status snapshots"
```

---

### Task 2: Backend Delete Guard and Task Status Realtime Event

**Files:**
- Modify: `backend/app/modules/crawler/tasks/runtime_status.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Test: `backend/tests/test_crawl_tasks_api.py`
- Test: `backend/tests/test_crawler_realtime_events.py`

**Interfaces:**
- Consumes: `get_task_runtime_status(db, task_id, owner_id)`
- Produces: `can_delete_task_runtime_status(runtime_status: str) -> bool`
- Produces: `publish_task_status_updated(db: Session, run: CrawlRun) -> None`
- Publishes: realtime event `crawler.task.status.updated` with payload matching `CrawlTaskRuntimeSnapshot`

- [ ] **Step 1: Write failing delete guard test**

Append this test to `backend/tests/test_crawl_tasks_api.py`:

```python
    def test_delete_rejects_non_idle_runtime_task(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        task = CrawlTask(name="运行中任务", storage_location="RUNNING", owner_id=admin_user.id)
        session.add(task)
        session.flush()
        session.add(CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="running",
            crawl_mode="incremental",
            created_at=datetime(2026, 7, 3, 8, 0, 0),
        ))
        session.commit()
        task_id = task.id
        session.close()

        response = client.delete(f"/api/crawler/tasks/{task_id}", headers=headers)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["msg"] == "只有空闲中的任务才能删除"
    ```

- [ ] **Step 2: Write failing realtime event test**

Append this test to `backend/tests/test_crawler_realtime_events.py`:

```python
def test_publish_run_updated_also_publishes_task_status_event(admin_user) -> None:
    session = TestingSessionLocal()
    task = CrawlTask(name="任务A", storage_location="A", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        created_at=datetime(2026, 7, 3, 8, 0, 0),
    )
    session.add(run)
    task_id = str(task.id)
    session.commit()
    session.refresh(run)
    run_id = str(run.id)
    queue = event_bus.subscribe(str(admin_user.id))

    service.publish_run_updated(session, run)

    events = drain(queue)
    event_bus.unsubscribe(str(admin_user.id), queue)
    session.close()

    assert [event.event for event in events] == [
        "crawler.run.updated",
        "crawler.task.status.updated",
    ]
    task_event = events[1]
    assert task_event.scope == "crawler.task"
    assert task_event.resource_id == task_id
    assert task_event.payload["task_id"] == task_id
    assert task_event.payload["runtime_status"] == "running"
    assert task_event.payload["latest_run_id"] == run_id
    assert task_event.payload["latest_run_status"] == "running"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_delete_rejects_non_idle_runtime_task backend/tests/test_crawler_realtime_events.py::test_publish_run_updated_also_publishes_task_status_event -v
```

Expected: delete test fails because deletion succeeds; realtime test fails because only `crawler.run.updated` is published.

- [ ] **Step 4: Add delete eligibility helper**

In `backend/app/modules/crawler/tasks/runtime_status.py`, add:

```python
def can_delete_task_runtime_status(runtime_status: str) -> bool:
    return runtime_status == "idle"
```

- [ ] **Step 5: Enforce delete guard in the task router**

In `backend/app/modules/crawler/tasks/router.py`, extend the import:

```python
from backend.app.modules.crawler.tasks.runtime_status import (
    build_task_runtime_status_response,
    can_delete_task_runtime_status,
    get_task_runtime_status,
)
```

In `delete_task_endpoint`, after the delete mode validation and before `delete_task(db, task_id, mode=mode)`, insert:

```python
    runtime_snapshot = get_task_runtime_status(db, task_id, current_user.id)
    if runtime_snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if not can_delete_task_runtime_status(runtime_snapshot.runtime_status):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有空闲中的任务才能删除")
```

- [ ] **Step 6: Publish task status events beside run updates**

In `backend/app/modules/crawler/runtime/service.py`, add a helper after `publish_run_updated`:

```python
def publish_task_status_updated(db: Session, run: CrawlRun) -> None:
    from backend.app.modules.crawler.tasks.runtime_status import build_task_runtime_snapshot
    from backend.app.modules.realtime.bus import event_bus as realtime_bus
    from backend.app.modules.realtime.schemas import make_realtime_event

    if run.task_id is None:
        return
    task = db.get(CrawlTask, run.task_id)
    if task is None:
        return
    owner_id = str(task.owner_id)
    snapshot = build_task_runtime_snapshot(task, run)
    realtime_bus.publish(
        make_realtime_event(
            event="crawler.task.status.updated",
            scope="crawler.task",
            owner_id=owner_id,
            resource_id=str(task.id),
            payload=snapshot.model_dump(mode="json"),
        )
    )
```

Then add this call at the end of `publish_run_updated`, after the existing `crawler.run.updated` publish:

```python
    publish_task_status_updated(db, run)
```

- [ ] **Step 7: Run targeted tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_delete_rejects_non_idle_runtime_task backend/tests/test_crawler_realtime_events.py::test_publish_run_updated_also_publishes_task_status_event backend/tests/test_crawler_worker_service.py::test_execute_run_publishes_run_detail_events_to_realtime_bus -v
```

Expected: all selected tests pass. The worker event test should still pass because it checks event membership, not exact event count.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/tasks/runtime_status.py backend/app/modules/crawler/tasks/router.py backend/app/modules/crawler/runtime/service.py backend/tests/test_crawl_tasks_api.py backend/tests/test_crawler_realtime_events.py
git commit -m "feat: publish crawler task runtime status events"
```

---

### Task 3: Frontend API Types and Realtime Event Registration

**Files:**
- Modify: `frontend/src/api/crawlTask/types.ts`
- Modify: `frontend/src/api/crawlTask/index.ts`
- Modify: `frontend/src/realtime/types.ts`
- Modify: `frontend/src/realtime/eventSourceClient.ts`
- Test: `frontend/tests/realtime-event-source-client.test.ts`

**Interfaces:**
- Produces: `TaskRuntimeStatus = 'idle' | 'queued' | 'running' | 'stopped'`
- Produces: `getCrawlTaskRuntimeStatuses(): Promise<CrawlTaskRuntimeStatusResponse>`
- Produces: realtime event name `crawler.task.status.updated`

- [ ] **Step 1: Write failing realtime client test**

Append this test to `frontend/tests/realtime-event-source-client.test.ts`:

```ts
  it('delivers crawler task status updated events to subscribers', () => {
    const handler = vi.fn()
    subscribeRealtime('crawler.task.status.updated', handler)
    connectRealtime()

    FakeEventSource.instances[0].emit('crawler.task.status.updated', {
      id: 'event-task-1',
      event: 'crawler.task.status.updated',
      scope: 'crawler.task',
      resource_id: 'task-1',
      owner_id: 'user-1',
      payload: {
        task_id: 'task-1',
        runtime_status: 'running',
        latest_run_id: 'run-1',
        latest_run_status: 'running',
        last_run_at: '2026-07-03T08:00:00',
      },
      created_at: '2026-07-03T08:00:00Z',
    })

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({
      event: 'crawler.task.status.updated',
      resource_id: 'task-1',
      payload: expect.objectContaining({
        task_id: 'task-1',
        runtime_status: 'running',
      }),
    }))
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm test -- realtime-event-source-client.test.ts
```

Expected: TypeScript or runtime failure because `crawler.task.status.updated` is not registered as a valid event.

- [ ] **Step 3: Add frontend task runtime types**

In `frontend/src/api/crawlTask/types.ts`, add:

```ts
export type TaskRuntimeStatus = 'idle' | 'queued' | 'running' | 'stopped'

export interface CrawlTaskRuntimeSnapshot {
  task_id: string
  runtime_status: TaskRuntimeStatus
  latest_run_id: string | null
  latest_run_status: string | null
  last_run_at: string | null
}

export interface CrawlTaskRuntimeStats {
  total: number
  idle: number
  running: number
  queued: number
  stopped: number
}

export interface CrawlTaskRuntimeStatusResponse {
  tasks: CrawlTaskRuntimeSnapshot[]
  stats: CrawlTaskRuntimeStats
}
```

- [ ] **Step 4: Add frontend API function**

In `frontend/src/api/crawlTask/index.ts`, import `CrawlTaskRuntimeStatusResponse` and add:

```ts
export function getCrawlTaskRuntimeStatuses(): Promise<CrawlTaskRuntimeStatusResponse> {
  return request.get<CrawlTaskRuntimeStatusResponse>(`${BASE_URL}/statuses`)
}
```

- [ ] **Step 5: Add realtime event type**

In `frontend/src/realtime/types.ts`, import `CrawlTaskRuntimeSnapshot`:

```ts
import type { CrawlTaskRuntimeSnapshot } from '@/api/crawlTask/types'
```

Add:

```ts
export type CrawlerTaskStatusUpdatedPayload = CrawlTaskRuntimeSnapshot
```

Extend `RealtimeEventName`:

```ts
  | 'crawler.task.status.updated'
```

- [ ] **Step 6: Register the event in EventSource client**

In `frontend/src/realtime/eventSourceClient.ts`, add the event name to `EVENT_NAMES`:

```ts
  'crawler.task.status.updated',
```

- [ ] **Step 7: Run frontend realtime test**

Run:

```bash
cd frontend
npm test -- realtime-event-source-client.test.ts
```

Expected: all tests in the file pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/crawlTask/types.ts frontend/src/api/crawlTask/index.ts frontend/src/realtime/types.ts frontend/src/realtime/eventSourceClient.ts frontend/tests/realtime-event-source-client.test.ts
git commit -m "feat: add crawler task runtime status client types"
```

---

### Task 4: Frontend Task List Runtime Controls

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Test: `frontend/tests/crawler-run-controls.ui.test.tsx`

**Interfaces:**
- Consumes: `getCrawlTaskRuntimeStatuses()`
- Consumes: `stopCrawlerRun(runId: string)`
- Consumes: `restartCrawlerRun(runId: string)`
- Produces: `TaskListCards` props `runtimeByTaskId`, `onStop`, and `onRestart`

- [ ] **Step 1: Replace the existing task list run-control test with runtime-state coverage**

In `frontend/tests/crawler-run-controls.ui.test.tsx`, update mocks and add these tests. Keep the existing render helper if it still works; replace the mocked API setup with this shape:

```ts
import {
  getCrawlTaskRuntimeStatuses,
  getCrawlTasks,
} from '../src/api/crawlTask'
import {
  restartCrawlerRun,
  runCrawlTask,
  stopCrawlerRun,
} from '../src/api/crawlerRun'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getCrawlTaskRuntimeStatuses: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('../src/api/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
  stopCrawlerRun: vi.fn(),
  restartCrawlerRun: vi.fn(),
}))
```

Use this helper inside the test file:

```ts
function task(id: string, name: string, isSkip = false) {
  return {
    id,
    name,
    storage_location: name,
    urls: [],
    is_skip: isSkip,
    status: 'pending',
    task_id: null,
    error_message: null,
    total_found: 0,
    total_qualified: 0,
    owner_id: 'user-1',
    created_at: '2026-07-02T00:00:00',
    updated_at: null,
    last_run_at: null,
    last_run_status: null,
  }
}
```

Add tests:

```ts
  it('renders runtime stats and allows run only for idle enabled tasks', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [task('task-1', '任务A')],
      total: 1,
    })
    vi.mocked(getCrawlTaskRuntimeStatuses).mockResolvedValue({
      tasks: [{
        task_id: 'task-1',
        runtime_status: 'idle',
        latest_run_id: null,
        latest_run_status: null,
        last_run_at: null,
      }],
      stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
    })
    vi.mocked(runCrawlTask).mockResolvedValue({ id: 'run-1' } as never)

    renderPage()

    expect(await screen.findByText('空闲中')).toBeInTheDocument()
    expect(screen.getByText('总数')).toBeInTheDocument()
    expect(screen.getByText('运行中')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '爬取' }))
    await userEvent.click(await screen.findByText('增量爬取'))

    await waitFor(() => {
      expect(runCrawlTask).toHaveBeenCalledWith('task-1', 'incremental')
    })
  })

  it('shows stop for running tasks and blocks edit and delete actions', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [task('task-1', '任务A')],
      total: 1,
    })
    vi.mocked(getCrawlTaskRuntimeStatuses).mockResolvedValue({
      tasks: [{
        task_id: 'task-1',
        runtime_status: 'running',
        latest_run_id: 'run-1',
        latest_run_status: 'running',
        last_run_at: '2026-07-03T08:00:00',
      }],
      stats: { total: 1, idle: 0, running: 1, queued: 0, stopped: 0 },
    })
    vi.mocked(stopCrawlerRun).mockResolvedValue({ id: 'run-1' } as never)

    renderPage()

    expect(await screen.findByText('运行中')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '爬取' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('编辑 任务A')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('删除 任务A')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '停止' }))

    await waitFor(() => {
      expect(stopCrawlerRun).toHaveBeenCalledWith('run-1')
    })
  })

  it('shows restart for stopped tasks', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [task('task-1', '任务A')],
      total: 1,
    })
    vi.mocked(getCrawlTaskRuntimeStatuses).mockResolvedValue({
      tasks: [{
        task_id: 'task-1',
        runtime_status: 'stopped',
        latest_run_id: 'run-1',
        latest_run_status: 'stopped',
        last_run_at: '2026-07-03T08:00:00',
      }],
      stats: { total: 1, idle: 0, running: 0, queued: 0, stopped: 1 },
    })
    vi.mocked(restartCrawlerRun).mockResolvedValue({ id: 'run-1' } as never)

    renderPage()

    expect(await screen.findByText('停止中')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '重启' }))

    await waitFor(() => {
      expect(restartCrawlerRun).toHaveBeenCalledWith('run-1')
    })
  })
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx
```

Expected: tests fail because the page still calls `getCrawlTaskStats`, does not fetch runtime statuses, and task cards do not render stop/restart controls.

- [ ] **Step 3: Update TaskListPage state and actions**

In `frontend/src/pages/crawler/tasks/TaskListPage.tsx`, replace the stats import and add run control imports:

```ts
import {
  deleteCrawlTask,
  getCrawlTaskRuntimeStatuses,
  getCrawlTasks,
  updateCrawlTask,
} from '@/api/crawlTask'
import type {
  CrawlTask,
  CrawlTaskRuntimeSnapshot,
  CrawlTaskRuntimeStats,
  DeleteMode,
} from '@/api/crawlTask/types'
import { restartCrawlerRun, runCrawlTask, stopCrawlerRun } from '@/api/crawlerRun'
```

Use this initial stats shape:

```ts
const initialStats: CrawlTaskRuntimeStats = {
  total: 0,
  idle: 0,
  running: 0,
  queued: 0,
  stopped: 0,
}
```

Add status state:

```ts
  const [runtimeByTaskId, setRuntimeByTaskId] = useState<Record<string, CrawlTaskRuntimeSnapshot>>({})
```

Replace `fetchStats` with:

```ts
  const fetchRuntimeStatuses = useCallback(async () => {
    const data = await getCrawlTaskRuntimeStatuses()
    setRuntimeByTaskId(Object.fromEntries(data.tasks.map((item) => [item.task_id, item])))
    setStats(data.stats)
  }, [])
```

Update `refreshList`:

```ts
  const refreshList = useCallback(() => {
    void fetchTasks()
    void fetchRuntimeStatuses()
  }, [fetchRuntimeStatuses, fetchTasks])
```

Add handlers:

```ts
  const handleStop = useCallback(
    async (task: CrawlTask) => {
      const runtime = runtimeByTaskId[task.id]
      if (!runtime?.latest_run_id) return
      try {
        await stopCrawlerRun(runtime.latest_run_id)
        message.success('已停止运行')
        refreshList()
      } catch (error) {
        const msg = error instanceof Error ? error.message : '停止失败'
        message.error(msg)
        void fetchRuntimeStatuses()
      }
    },
    [fetchRuntimeStatuses, refreshList, runtimeByTaskId],
  )

  const handleRestart = useCallback(
    async (task: CrawlTask) => {
      const runtime = runtimeByTaskId[task.id]
      if (!runtime?.latest_run_id) return
      try {
        await restartCrawlerRun(runtime.latest_run_id)
        message.success('已重启运行')
        refreshList()
      } catch (error) {
        const msg = error instanceof Error ? error.message : '重启失败'
        message.error(msg)
        void fetchRuntimeStatuses()
      }
    },
    [fetchRuntimeStatuses, refreshList, runtimeByTaskId],
  )
```

Replace the stats JSX labels:

```tsx
        <div className={styles.statCard}>
          <span className={styles.statLabel}>总数</span>
          <span className={styles.statValue}>{stats.total}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>空闲中</span>
          <span className={styles.statValue}>{stats.idle}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>运行中</span>
          <span className={styles.statValue}>{stats.running}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>排队中</span>
          <span className={styles.statValue}>{stats.queued}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>停止中</span>
          <span className={styles.statValue}>{stats.stopped}</span>
        </div>
```

Pass new props to `TaskListCards`:

```tsx
          runtimeByTaskId={runtimeByTaskId}
          onStop={handleStop}
          onRestart={handleRestart}
```

- [ ] **Step 4: Update TaskListCards props and rendering**

In `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`, add icons:

```ts
  ReloadOutlined,
  StopOutlined,
```

Import runtime types:

```ts
import type { CrawlTask, CrawlTaskRuntimeSnapshot, TaskRuntimeStatus } from '@/api/crawlTask/types'
```

Extend props:

```ts
  runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>
  onStop: (task: CrawlTask) => void
  onRestart: (task: CrawlTask) => void
```

Replace status labels with:

```ts
const runtimeStatusLabels: Record<TaskRuntimeStatus, { text: string; color: string }> = {
  idle: { text: '空闲中', color: 'success' },
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  stopped: { text: '停止中', color: 'warning' },
}

function runtimeStatusTag(runtime?: CrawlTaskRuntimeSnapshot) {
  const status = runtime?.runtime_status ?? 'idle'
  const statusConfig = runtimeStatusLabels[status]
  return <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
}
```

Inside `TaskCard`, compute action state:

```ts
  const runtimeStatus = runtime?.runtime_status ?? 'idle'
  const isIdle = runtimeStatus === 'idle'
  const canRun = isIdle && !task.is_skip
  const canEditOrDelete = isIdle
  const canToggle = isIdle
  const canStop = (runtimeStatus === 'queued' || runtimeStatus === 'running') && Boolean(runtime?.latest_run_id)
  const canRestart = runtimeStatus === 'stopped' && Boolean(runtime?.latest_run_id)
```

Render the header tag:

```tsx
          {runtimeStatusTag(runtime)}
```

Set the switch disabled state:

```tsx
              disabled={!canToggle}
```

Replace the footer controls with:

```tsx
        {canRun && (
          <Dropdown
            menu={{
              items: runItems,
              onClick: ({ key }) => onRun(task, key as CrawlMode),
            }}
            trigger={['click']}
          >
            <Button type="primary" size="small" icon={<PlayCircleOutlined />}>
              爬取
            </Button>
          </Dropdown>
        )}
        {canStop && (
          <Button size="small" danger icon={<StopOutlined />} onClick={() => onStop(task)}>
            停止
          </Button>
        )}
        {canRestart && (
          <Button size="small" type="primary" icon={<ReloadOutlined />} onClick={() => onRestart(task)}>
            重启
          </Button>
        )}
        {canEditOrDelete && (
          <Space size={4}>
            <Tooltip title="编辑">
              <Button
                aria-label={`编辑 ${task.name}`}
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => onEdit(task)}
              />
            </Tooltip>
            <Tooltip title="删除">
              <Button
                aria-label={`删除 ${task.name}`}
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => onDelete(task)}
              />
            </Tooltip>
            <Dropdown
              menu={{
                items: [
                  { key: 'edit', label: '编辑', icon: <EditOutlined /> },
                  { key: 'delete', label: '删除', icon: <DeleteOutlined />, danger: true },
                ],
                onClick: ({ key }) => {
                  if (key === 'edit') onEdit(task)
                  if (key === 'delete') onDelete(task)
                },
              }}
              trigger={['click']}
            >
              <Button aria-label={`更多 ${task.name}`} type="text" size="small" icon={<MoreOutlined />} />
            </Dropdown>
          </Space>
        )}
```

Pass `runtime={runtimeByTaskId[task.id]}` into each `TaskCard`.

- [ ] **Step 5: Run frontend task-list tests**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx
```

Expected: tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/tests/crawler-run-controls.ui.test.tsx
git commit -m "feat: show crawler task runtime controls"
```

---

### Task 5: Frontend Realtime Synchronization and Final Verification

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Test: `frontend/tests/crawler-run-controls.ui.test.tsx`

**Interfaces:**
- Consumes: `connectRealtime()`
- Consumes: `subscribeRealtime<CrawlerTaskStatusUpdatedPayload>('crawler.task.status.updated', handler)`
- Consumes: `subscribeRealtime('system.resync_required', handler)`

- [ ] **Step 1: Add failing realtime UI tests**

In `frontend/tests/crawler-run-controls.ui.test.tsx`, mock the realtime client:

```ts
import type { RealtimeEventName, RealtimeHandler } from '../src/realtime/types'

const realtimeHandlers = new Map<string, Set<RealtimeHandler>>()

vi.mock('../src/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(() => null),
  subscribeRealtime: vi.fn((eventName: RealtimeEventName, handler: RealtimeHandler) => {
    const handlers = realtimeHandlers.get(eventName) ?? new Set()
    handlers.add(handler)
    realtimeHandlers.set(eventName, handlers)
    return () => handlers.delete(handler)
  }),
}))

function emit(eventName: RealtimeEventName, payload: Record<string, unknown>, resourceId: string | null = 'task-1') {
  for (const handler of realtimeHandlers.get(eventName) ?? []) {
    handler({
      id: `event-${Date.now()}`,
      event: eventName,
      scope: eventName.startsWith('crawler.task') ? 'crawler.task' : 'system',
      resource_id: resourceId,
      owner_id: 'user-1',
      payload,
      created_at: '2026-07-03T00:00:00Z',
    })
  }
}
```

Clear the map in `beforeEach`:

```ts
    realtimeHandlers.clear()
```

Add tests:

```ts
  it('updates a task card from realtime task status events', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [task('task-1', '任务A')],
      total: 1,
    })
    vi.mocked(getCrawlTaskRuntimeStatuses).mockResolvedValue({
      tasks: [{
        task_id: 'task-1',
        runtime_status: 'idle',
        latest_run_id: null,
        latest_run_status: null,
        last_run_at: null,
      }],
      stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
    })

    renderPage()
    expect(await screen.findByText('空闲中')).toBeInTheDocument()

    emit('crawler.task.status.updated', {
      task_id: 'task-1',
      runtime_status: 'running',
      latest_run_id: 'run-1',
      latest_run_status: 'running',
      last_run_at: '2026-07-03T08:00:00',
    })

    expect(await screen.findByText('运行中')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
  })

  it('refetches task statuses after system resync events', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [task('task-1', '任务A')],
      total: 1,
    })
    vi.mocked(getCrawlTaskRuntimeStatuses)
      .mockResolvedValueOnce({
        tasks: [{
          task_id: 'task-1',
          runtime_status: 'idle',
          latest_run_id: null,
          latest_run_status: null,
          last_run_at: null,
        }],
        stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 },
      })
      .mockResolvedValueOnce({
        tasks: [{
          task_id: 'task-1',
          runtime_status: 'stopped',
          latest_run_id: 'run-1',
          latest_run_status: 'stopped',
          last_run_at: '2026-07-03T08:00:00',
        }],
        stats: { total: 1, idle: 0, running: 0, queued: 0, stopped: 1 },
      })

    renderPage()
    expect(await screen.findByText('空闲中')).toBeInTheDocument()

    emit('system.resync_required', { reason: 'connection_error' }, null)

    await waitFor(() => {
      expect(getCrawlTaskRuntimeStatuses).toHaveBeenCalledTimes(2)
    })
    expect(await screen.findByText('停止中')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx
```

Expected: realtime tests fail because the task list does not subscribe to realtime events yet.

- [ ] **Step 3: Add realtime subscriptions to TaskListPage**

In `frontend/src/pages/crawler/tasks/TaskListPage.tsx`, add imports:

```ts
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { CrawlerTaskStatusUpdatedPayload } from '@/realtime/types'
```

Add a stats recompute helper near the component:

```ts
function recomputeStats(runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>): CrawlTaskRuntimeStats {
  const rows = Object.values(runtimeByTaskId)
  return rows.reduce<CrawlTaskRuntimeStats>(
    (acc, row) => {
      acc.total += 1
      acc[row.runtime_status] += 1
      return acc
    },
    { total: 0, idle: 0, running: 0, queued: 0, stopped: 0 },
  )
}
```

Add the subscription effect inside `TaskListPage`:

```ts
  useEffect(() => {
    connectRealtime()

    const unsubscribeTaskStatus = subscribeRealtime<CrawlerTaskStatusUpdatedPayload>(
      'crawler.task.status.updated',
      (event) => {
        const payload = event.payload
        setRuntimeByTaskId((current) => {
          const next = { ...current, [payload.task_id]: payload }
          setStats(recomputeStats(next))
          return next
        })
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        refreshList()
      },
    )

    return () => {
      unsubscribeTaskStatus()
      unsubscribeResync()
    }
  }, [refreshList])
```

- [ ] **Step 4: Run frontend targeted tests**

Run:

```bash
cd frontend
npm test -- realtime-event-source-client.test.ts crawler-run-controls.ui.test.tsx
```

Expected: both files pass.

- [ ] **Step 5: Run backend targeted tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py backend/tests/test_crawler_realtime_events.py backend/tests/test_crawler_worker_service.py -v
```

Expected: all selected backend tests pass.

- [ ] **Step 6: Run full verification suites**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
cd frontend
npm test
npm run build
```

Expected:

- Backend pytest passes.
- Frontend Vitest passes.
- Frontend build completes without TypeScript or Vite errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/tests/crawler-run-controls.ui.test.tsx
git commit -m "feat: sync crawler task list runtime status"
```

---

## Self-Review

- Spec coverage: the plan covers derived status mapping, status snapshot endpoint, realtime task event, task-list action gating, stop/restart through latest run id, runtime stats, delete guard, EventSource resync, and backend/frontend tests.
- Scope check: the plan does not add scheduling, batch run-all, a persisted task runtime field, or per-detail retry.
- Type consistency: backend snapshot fields are `task_id`, `runtime_status`, `latest_run_id`, `latest_run_status`, and `last_run_at`; frontend uses the same names.
- Event consistency: the only new realtime event is `crawler.task.status.updated`; it uses the existing `/api/events/stream` client.
