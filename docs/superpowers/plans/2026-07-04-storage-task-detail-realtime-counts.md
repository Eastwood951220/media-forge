# Storage Task Detail Realtime Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the storage task detail page so the header status/counts and subtask table update immediately from EventSource events while storage subtasks run.

**Architecture:** The backend must publish `storage.main.updated` only after recomputing main-task counts each time a subtask reaches a visible state change. The frontend detail page must consume `storage.sub.updated` as a single subtask update object, merge it into the existing table rows, and merge partial `storage.main.updated` payloads into the header.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, pytest, React 19, TypeScript, Ant Design, Vitest, React Testing Library, EventSource.

---

## File Structure

- Modify `backend/app/modules/storage/worker/runner.py`
  - Recompute `StorageMainTask` counts before every `storage.main.updated` publish inside worker processing.
  - Publish main-task updates after provider creation failures, normal subtask completion, skipped subtasks, and failed subtasks.

- Modify `backend/tests/test_storage_worker_service.py`
  - Add regression tests proving running main-task events contain updated counts immediately after a subtask completes or fails.

- Modify `frontend/src/realtime/types.ts`
  - Make `StorageMainUpdatedPayload` match the backend partial payload.
  - Reuse the existing `StorageSubUpdatedPayload` for detail-page subtask updates.

- Modify `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`
  - Treat `storage.sub.updated` payload as one subtask object, not an array.
  - Merge single subtask updates into the table rows.
  - Merge partial main-task updates into the header without replacing the full task object with a partial payload.

- Create `frontend/src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx`
  - Test header status/count updates from `storage.main.updated`.
  - Test table-row status/step updates from single-object `storage.sub.updated`.
  - Test events for other task ids are ignored.

---

### Task 1: Publish Recomputed Main Counts From the Worker

**Files:**
- Modify: `backend/app/modules/storage/worker/runner.py`
- Test: `backend/tests/test_storage_worker_service.py`

- [ ] **Step 1: Write the failing test for completed subtask count events**

Append this test to `backend/tests/test_storage_worker_service.py`:

```python
def test_process_main_task_publishes_recomputed_counts_after_subtask_completion(db_session, test_user, monkeypatch):
    import uuid

    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.realtime.bus import event_bus
    from backend.app.modules.storage.worker.runner import process_main_task
    from backend.tests.conftest import TestingSessionLocal
    from shared.database.models.content import Movie

    monkeypatch.setattr(
        "shared.database.session.get_session_factory",
        lambda: TestingSessionLocal,
    )

    movie = Movie(code="ABC-COUNT", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="count-task",
        display_name="count-task",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        created_by=test_user.id,
        config_snapshot={"download_root_folder": "/Downloads", "target_folder": "/Movies"},
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-COUNT",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    def fake_execute_subtask_pipeline(context):
        context.subtask.status = "completed"
        context.subtask.step = "done"

    class FakeRuntime:
        def should_stop(self, task_id: str) -> bool:
            return False

    class FakeProviderFactory:
        def create(self, config):
            return object()

    queue = event_bus.subscribe(str(test_user.id))
    try:
        monkeypatch.setattr(
            "backend.app.modules.storage.worker.steps.execute_subtask_pipeline",
            fake_execute_subtask_pipeline,
        )

        process_main_task(FakeRuntime(), FakeProviderFactory(), None, str(main.id))

        main_events = []
        while not queue.empty():
            event = queue.get_nowait()
            if event.event == "storage.main.updated" and event.resource_id == str(main.id):
                main_events.append(event.payload)
    finally:
        event_bus.unsubscribe(str(test_user.id), queue)

    running_events = [payload for payload in main_events if payload["status"] == "running"]
    assert running_events
    assert running_events[-1]["success_count"] == 1
    assert running_events[-1]["failed_count"] == 0
    assert running_events[-1]["skipped_count"] == 0
```

- [ ] **Step 2: Run the failing completed-count test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py::test_process_main_task_publishes_recomputed_counts_after_subtask_completion -q
```

Expected: FAIL because the running `storage.main.updated` event is published before `repository.recompute_counts(main_task)`.

- [ ] **Step 3: Write the failing test for provider creation failure count events**

Append this test to `backend/tests/test_storage_worker_service.py`:

```python
def test_process_main_task_publishes_recomputed_counts_after_provider_creation_failure(db_session, test_user, monkeypatch):
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.realtime.bus import event_bus
    from backend.app.modules.storage.worker.runner import process_main_task
    from backend.tests.conftest import TestingSessionLocal
    from shared.database.models.content import Movie

    monkeypatch.setattr(
        "shared.database.session.get_session_factory",
        lambda: TestingSessionLocal,
    )

    movie = Movie(code="ABC-FAIL", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="fail-task",
        display_name="fail-task",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        created_by=test_user.id,
        config_snapshot={"download_root_folder": "/Downloads", "target_folder": "/Movies"},
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-FAIL",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    class FakeRuntime:
        def should_stop(self, task_id: str) -> bool:
            return False

    class FailingProviderFactory:
        def create(self, config):
            raise RuntimeError("boom-provider")

    queue = event_bus.subscribe(str(test_user.id))
    try:
        process_main_task(FakeRuntime(), FailingProviderFactory(), None, str(main.id))

        main_events = []
        while not queue.empty():
            event = queue.get_nowait()
            if event.event == "storage.main.updated" and event.resource_id == str(main.id):
                main_events.append(event.payload)
    finally:
        event_bus.unsubscribe(str(test_user.id), queue)

    running_events = [payload for payload in main_events if payload["status"] == "running"]
    assert running_events
    assert running_events[-1]["success_count"] == 0
    assert running_events[-1]["failed_count"] == 1
    assert running_events[-1]["skipped_count"] == 0
```

- [ ] **Step 4: Run the failing provider-failure count test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py::test_process_main_task_publishes_recomputed_counts_after_provider_creation_failure -q
```

Expected: FAIL because the provider-creation failure branch commits and continues without publishing a running main-task event with recomputed counts.

- [ ] **Step 5: Add a helper that recomputes counts before publishing**

In `backend/app/modules/storage/worker/runner.py`, add this function after `_worker_loop()`:

```python
def _publish_main_with_recomputed_counts(db: Session, repository, main_task: StorageMainTask) -> None:
    from backend.app.modules.storage.tasks.events import publish_storage_main_updated

    repository.recompute_counts(main_task)
    db.flush()
    db.commit()
    publish_storage_main_updated(main_task)
```

- [ ] **Step 6: Use the helper in provider creation failure branch**

In `process_main_task()`, replace the provider-creation failure branch commit:

```python
                db.commit()
                continue
```

with:

```python
                _publish_main_with_recomputed_counts(db, repository, main_task)
                continue
```

- [ ] **Step 7: Use the helper after each processed subtask**

In `process_main_task()`, replace this block after subtask processing:

```python
            db.commit()
            publish_storage_main_updated(main_task)
```

with:

```python
            _publish_main_with_recomputed_counts(db, repository, main_task)
```

- [ ] **Step 8: Keep final main-task publish recomputed**

At the end of `process_main_task()`, replace:

```python
        repository.recompute_counts(main_task)

        if runtime.should_stop(task_id):
            main_task.status = "stopped"
        elif has_failure:
            main_task.status = "failed"
        else:
            main_task.status = "completed"

        main_task.finished_at = datetime.now(timezone.utc)
        db.commit()
        publish_storage_main_updated(main_task)
```

with:

```python
        repository.recompute_counts(main_task)

        if runtime.should_stop(task_id):
            main_task.status = "stopped"
        elif has_failure:
            main_task.status = "failed"
        else:
            main_task.status = "completed"

        main_task.finished_at = datetime.now(timezone.utc)
        _publish_main_with_recomputed_counts(db, repository, main_task)
```

- [ ] **Step 9: Run backend worker tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit Task 1**

Run:

```bash
git add backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_service.py
git commit -m "fix: publish realtime storage counts"
```

---

### Task 2: Fix Frontend Realtime Payload Types

**Files:**
- Modify: `frontend/src/realtime/types.ts`

- [ ] **Step 1: Update realtime payload types**

In `frontend/src/realtime/types.ts`, replace:

```ts
export type StorageMainUpdatedPayload = StorageMainTask
```

with:

```ts
export type StorageMainUpdatedPayload = Pick<
  StorageMainTask,
  'id' | 'status' | 'total_count' | 'success_count' | 'failed_count' | 'skipped_count'
> & Partial<StorageMainTask>
```

The existing `StorageSubUpdatedPayload` type already matches the backend event payload and should remain:

```ts
export type StorageSubUpdatedPayload = {
  id: string
  main_task_id: string
  movie_id: string
  status: string
  step: string
  error_message?: string | null
}
```

- [ ] **Step 2: Run frontend typecheck to confirm the current detail page type mismatch**

Run:

```bash
cd frontend
npm run build
```

Expected before Task 3 implementation: TypeScript may report that `StorageMainUpdatedPayload` is not assignable to `StorageMainTask` in detail/list page handlers. Keep the type change and fix usage in Task 3.

---

### Task 3: Merge Single Subtask Events in Storage Task Detail Page

**Files:**
- Modify: `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`
- Test: `frontend/src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx`

- [ ] **Step 1: Create the failing detail-page realtime test**

Create `frontend/src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx` with:

```tsx
import { render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageTaskDetailPage from '../StorageTaskDetailPage'
import type { RealtimeEventName, RealtimeHandler } from '@/realtime/types'

const realtimeHandlers = new Map<string, Set<RealtimeHandler>>()

vi.mock('@/api/storage/storageTasks', () => ({
  getStorageMainTask: vi.fn().mockResolvedValue({
    id: 'main-1',
    alias: 'task-alias',
    display_name: 'task-alias',
    source: 'single',
    storage_mode: 'single',
    status: 'queued',
    total_count: 2,
    success_count: 0,
    failed_count: 0,
    skipped_count: 0,
    created_at: '2026-07-04T00:00:00Z',
    started_at: null,
    finished_at: null,
    error_message: null,
  }),
  listStorageSubTasks: vi.fn().mockResolvedValue({
    rows: [
      {
        id: 'sub-1',
        main_task_id: 'main-1',
        movie_id: 'movie-1',
        movie_code: 'ABC-001',
        movie_title: 'Movie 1',
        status: 'queued',
        step: 'prepare',
        storage_mode: 'single',
        selected_storage_location: null,
        target_locations: ['A'],
        download_path: '',
        target_paths: [],
        magnet_attempts: [],
        current_magnet_id: null,
        current_magnet_url: '',
        renamed_files: [],
        moved_files: [],
        skipped_files: [],
        result: {},
      },
      {
        id: 'sub-2',
        main_task_id: 'main-1',
        movie_id: 'movie-2',
        movie_code: 'ABC-002',
        movie_title: 'Movie 2',
        status: 'queued',
        step: 'prepare',
        storage_mode: 'single',
        selected_storage_location: null,
        target_locations: ['A'],
        download_path: '',
        target_paths: [],
        magnet_attempts: [],
        current_magnet_id: null,
        current_magnet_url: '',
        renamed_files: [],
        moved_files: [],
        skipped_files: [],
        result: {},
      },
    ],
    total: 2,
  }),
  stopStorageMainTask: vi.fn(),
  restartStorageMainTask: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(() => null),
  subscribeRealtime: vi.fn((eventName: RealtimeEventName, handler: RealtimeHandler) => {
    const handlers = realtimeHandlers.get(eventName) ?? new Set()
    handlers.add(handler)
    realtimeHandlers.set(eventName, handlers)
    return () => handlers.delete(handler)
  }),
}))

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ id: 'main-1' }),
  useNavigate: vi.fn().mockReturnValue(vi.fn()),
}))

function emit(eventName: RealtimeEventName, payload: Record<string, unknown>, resourceId: string | null = 'main-1') {
  for (const handler of realtimeHandlers.get(eventName) ?? []) {
    handler({
      id: `event-${Date.now()}`,
      event: eventName,
      scope: eventName.startsWith('storage.sub') ? 'storage.sub' : 'storage.main',
      resource_id: resourceId,
      owner_id: 'user-1',
      payload,
      created_at: '2026-07-04T00:00:00Z',
    })
  }
}

function descriptionValue(label: string) {
  const labelNode = screen.getByText(label)
  const item = labelNode.closest('.ant-descriptions-item')
  if (!item) throw new Error(`Missing description item for ${label}`)
  return item
}

describe('StorageTaskDetailPage realtime updates', () => {
  beforeEach(() => {
    realtimeHandlers.clear()
  })

  it('updates header counts and subtask row from realtime events', async () => {
    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('存储任务详情 - task-alias')).toBeInTheDocument()
    expect(screen.getByText('ABC-001')).toBeInTheDocument()

    emit('storage.main.updated', {
      id: 'main-1',
      status: 'running',
      total_count: 2,
      success_count: 1,
      failed_count: 0,
      skipped_count: 1,
    })

    emit('storage.sub.updated', {
      id: 'sub-1',
      main_task_id: 'main-1',
      movie_id: 'movie-1',
      status: 'completed',
      step: 'done',
      error_message: null,
    }, 'sub-1')

    await waitFor(() => {
      expect(within(descriptionValue('状态')).getByText('运行中')).toBeInTheDocument()
      expect(within(descriptionValue('成功')).getByText('1')).toBeInTheDocument()
      expect(within(descriptionValue('跳过')).getByText('1')).toBeInTheDocument()
      const row = screen.getByText('ABC-001').closest('tr')
      if (!row) throw new Error('Missing ABC-001 row')
      expect(within(row).getByText('已完成')).toBeInTheDocument()
      expect(within(row).getByText('done')).toBeInTheDocument()
    })
  })

  it('ignores subtask events for other main tasks', async () => {
    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('ABC-002')).toBeInTheDocument()

    emit('storage.sub.updated', {
      id: 'sub-other',
      main_task_id: 'other-main',
      movie_id: 'movie-other',
      status: 'completed',
      step: 'done',
      error_message: null,
    }, 'sub-other')

    await waitFor(() => {
      expect(screen.queryByText('sub-other')).not.toBeInTheDocument()
      const row = screen.getByText('ABC-002').closest('tr')
      if (!row) throw new Error('Missing ABC-002 row')
      expect(within(row).getByText('排队中')).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run the failing frontend test**

Run:

```bash
cd frontend
npm test -- storage-task-detail-realtime.test.tsx
```

Expected: FAIL because `StorageTaskDetailPage` currently ignores single-object `storage.sub.updated` payloads by checking `Array.isArray(event.payload)`.

- [ ] **Step 3: Update imports in `StorageTaskDetailPage.tsx`**

In `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`, replace:

```ts
import type { RealtimeEvent } from '@/realtime/types'
```

with:

```ts
import type { RealtimeEvent, StorageMainUpdatedPayload, StorageSubUpdatedPayload } from '@/realtime/types'
```

- [ ] **Step 4: Add a subtask merge helper inside `StorageTaskDetailPage.tsx`**

Add this helper above `function StorageTaskDetailPage()`:

```ts
function mergeSubtaskUpdate(current: StorageSubTask[], update: StorageSubUpdatedPayload): StorageSubTask[] {
  let matched = false
  const next = current.map((subtask) => {
    if (subtask.id !== update.id) return subtask
    matched = true
    return { ...subtask, ...update }
  })
  return matched ? next : current
}
```

This helper updates existing table rows only. It does not append partial rows because the backend `storage.sub.updated` payload intentionally does not include `movie_code`, `movie_title`, or target fields needed for a full table row.

- [ ] **Step 5: Merge partial main-task payloads safely**

Replace the `storage.main.updated` subscription block:

```ts
    const unsubscribeTask = subscribeRealtime<StorageMainTask>(
      'storage.main.updated',
      (event: RealtimeEvent<StorageMainTask>) => {
        if (event.payload.id !== id) return
        setTask((current) => (current ? { ...current, ...event.payload } : event.payload))
      },
    )
```

with:

```ts
    const unsubscribeTask = subscribeRealtime<StorageMainUpdatedPayload>(
      'storage.main.updated',
      (event: RealtimeEvent<StorageMainUpdatedPayload>) => {
        if (event.payload.id !== id) return
        setTask((current) => (current ? { ...current, ...event.payload } : current))
      },
    )
```

- [ ] **Step 6: Consume single-object subtask updates**

Replace the `storage.sub.updated` subscription block:

```ts
    const unsubscribeSubtask = subscribeRealtime<StorageSubTask[]>(
      'storage.sub.updated',
      (event: RealtimeEvent<StorageSubTask[]>) => {
        if (!Array.isArray(event.payload)) return
        setSubtasks((current) => {
          const byId = new Map(current.map((st) => [st.id, st]))
          for (const subtask of event.payload) {
            if (subtask.main_task_id === id) {
              byId.set(subtask.id, subtask)
            }
          }
          return Array.from(byId.values())
        })
      },
    )
```

with:

```ts
    const unsubscribeSubtask = subscribeRealtime<StorageSubUpdatedPayload>(
      'storage.sub.updated',
      (event: RealtimeEvent<StorageSubUpdatedPayload>) => {
        if (event.payload.main_task_id !== id) return
        setSubtasks((current) => mergeSubtaskUpdate(current, event.payload))
      },
    )
```

- [ ] **Step 7: Run the frontend detail realtime test**

Run:

```bash
cd frontend
npm test -- storage-task-detail-realtime.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx frontend/src/pages/storage/tasks/__tests__/storage-task-detail-realtime.test.tsx frontend/src/realtime/types.ts
git commit -m "fix: update storage detail from realtime events"
```

---

### Task 4: Verify Frontend and Backend Realtime Behavior

**Files:**
- Verify only; no source edits expected unless a test exposes an implementation mismatch.

- [ ] **Step 1: Run backend storage worker tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend realtime and detail tests**

Run:

```bash
cd frontend
npm test -- storage-realtime-events.test.ts storage-task-detail-realtime.test.tsx storage-subtask-detail-timeline.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS. If TypeScript reports `StorageMainUpdatedPayload` or `StorageSubUpdatedPayload` mismatches in another page, update that page to use the correct payload type and rerun this command.

- [ ] **Step 4: Inspect event payload shape references**

Run:

```bash
rg -n "subscribeRealtime<StorageMainTask>|subscribeRealtime<StorageSubTask\\[]|StorageMainUpdatedPayload|StorageSubUpdatedPayload" frontend/src frontend/tests
```

Expected:

- `StorageTaskDetailPage.tsx` subscribes with `StorageMainUpdatedPayload` for `storage.main.updated`.
- `StorageTaskDetailPage.tsx` subscribes with `StorageSubUpdatedPayload` for `storage.sub.updated`.
- No storage detail code expects `storage.sub.updated` to be an array.

- [ ] **Step 5: Commit verification-only fixes if needed**

If Step 3 or Step 4 required additional source edits, run:

```bash
git add frontend/src frontend/tests backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_service.py
git commit -m "test: verify storage detail realtime updates"
```

If Step 3 and Step 4 required no edits, do not create a commit for Task 4.

---

## Self-Review

Spec coverage:

- Storage task detail header status and counts update in realtime: Task 1 publishes recomputed counts; Task 3 merges `storage.main.updated` into the header.
- Storage task detail subtask list updates in realtime: Task 3 changes the detail page to consume a single `StorageSubUpdatedPayload` and merge it into existing rows.
- Success, failure, skipped counts update as subtasks finish: Task 1 recomputes and publishes after each processed subtask and provider creation failure; skipped subtasks are covered by the same post-subtask path.
- EventSource interface remains the realtime source: Task 3 keeps `connectRealtime()` and `subscribeRealtime()`.
- Tests cover backend count event timing and frontend detail-page event handling: Task 1 and Task 3.

No incomplete markers remain. Type names are consistent across tasks: `StorageMainUpdatedPayload`, `StorageSubUpdatedPayload`, and `mergeSubtaskUpdate`.
