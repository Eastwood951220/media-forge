# Storage Task Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a storage task delete action that removes one `storage_main_tasks` row, its `storage_sub_tasks` rows, and every related storage subtask JSONL log file.

**Architecture:** The backend owns deletion because it must enforce task ownership, reject active tasks, collect subtask ids before deleting the main task, delete JSONL log files, and publish a realtime delete event. The frontend adds a typed delete API, a guarded delete button on the storage task list, and realtime list removal for delete events.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, pytest, React 19, TypeScript, Ant Design 6, Vitest.

---

## File Structure

- Modify `backend/app/modules/storage/tasks/logs.py`
  - Add `delete_storage_subtask_log(subtask_id: str) -> bool`.
- Modify `backend/app/modules/storage/tasks/repository.py`
  - Add `list_subtask_ids(main_task_id: uuid.UUID) -> list[uuid.UUID]`.
  - Add `delete_main_task(main_task: StorageMainTask) -> None`.
- Modify `backend/app/modules/storage/tasks/events.py`
  - Add `publish_storage_main_deleted(owner_id: str, task_id: str) -> None`.
- Modify `backend/app/modules/storage/tasks/service.py`
  - Add `delete_main_task(task_id: uuid.UUID, user_id: uuid.UUID) -> dict`.
  - Reject `queued`, `running`, and `stopping` tasks.
  - Delete JSONL logs for every subtask id collected before the DB delete.
- Modify `backend/app/modules/storage/tasks/router.py`
  - Add `DELETE /api/storage/tasks/{main_task_id}`.
- Modify `backend/tests/test_storage_tasks_api.py`
  - Add API coverage for successful delete, ownership isolation, active-task rejection, and log deletion.
- Modify `frontend/src/api/storage/storageTasks/index.ts`
  - Add `deleteStorageMainTask(id: string): Promise<void>`.
- Modify `frontend/src/realtime/types.ts`
  - Add `storage.main.deleted` to realtime event types.
  - Add `StorageMainDeletedPayload`.
- Modify `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`
  - Add delete button with `Popconfirm`.
  - Hide delete for `queued`, `running`, and `stopping`.
  - Refresh after manual delete and remove tasks when realtime delete event arrives.
- Modify `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`
  - Update mocks for the new API.
  - Add one UI test that confirms delete is shown for terminal tasks and calls the API after confirmation.

## Behavior Rules

- Deleting a storage main task deletes the main task row and all child subtask rows through the existing SQLAlchemy relationship cascade and database `ON DELETE CASCADE`.
- JSONL files under `APP_DATA_DIR/logs/storage/tasks/{subtask_id}.jsonl` are deleted for every subtask belonging to the main task.
- Deleting an unknown task returns `404`.
- Deleting another user's task returns `404`.
- Deleting `queued`, `running`, or `stopping` returns `400` with `运行中的存储任务不能删除，请先停止任务`.
- Deleting `completed`, `failed`, or `stopped` returns `204 No Content`.
- If a subtask JSONL log file does not exist, deletion still succeeds. Missing local logs are normal because some subtasks may never have written logs, logs may have been cleaned previously, or `APP_DATA_DIR` may differ between environments.
- The delete action does not delete movies, magnets, crawler tasks, storage summaries, CloudDrive files, download folders, or target folders.

## Task 1: Storage Log Delete Helper

**Files:**
- Modify: `backend/app/modules/storage/tasks/logs.py`
- Test: `backend/tests/test_storage_realtime_events.py`

- [ ] **Step 1: Write the failing log deletion test**

Append this test to `backend/tests/test_storage_realtime_events.py`:

```python
def test_delete_storage_subtask_log_removes_jsonl_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    from backend.app.modules.storage.tasks.logs import (
        delete_storage_subtask_log,
        read_storage_subtask_logs,
        write_storage_subtask_log,
    )

    write_storage_subtask_log("sub-delete-1", "INFO", "存储子任务日志", {"value": 1})

    assert read_storage_subtask_logs("sub-delete-1")[0]["message"] == "存储子任务日志"
    assert delete_storage_subtask_log("sub-delete-1") is True
    assert read_storage_subtask_logs("sub-delete-1") == []
    assert delete_storage_subtask_log("sub-delete-1") is False
```

- [ ] **Step 2: Run the log deletion test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_realtime_events.py::test_delete_storage_subtask_log_removes_jsonl_file -q
```

Expected: FAIL with `ImportError: cannot import name 'delete_storage_subtask_log'`.

- [ ] **Step 3: Implement the log deletion helper**

In `backend/app/modules/storage/tasks/logs.py`, add this function after `read_storage_subtask_logs()`:

```python
def delete_storage_subtask_log(subtask_id: str) -> bool:
    path = _log_path(subtask_id)
    if not path.exists():
        return False
    path.unlink()
    return True
```

- [ ] **Step 4: Run the log deletion test and verify it passes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest backend/tests/test_storage_realtime_events.py::test_delete_storage_subtask_log_removes_jsonl_file -q
```

Expected: PASS.

- [ ] **Step 5: Commit log helper**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/tasks/logs.py backend/tests/test_storage_realtime_events.py
git commit -m "feat: delete storage subtask logs"
```

Expected: commit succeeds.

## Task 2: Backend Service And Repository Deletion

**Files:**
- Modify: `backend/app/modules/storage/tasks/repository.py`
- Modify: `backend/app/modules/storage/tasks/service.py`
- Test: `backend/tests/test_storage_tasks_api.py`

- [ ] **Step 1: Write the failing service-level deletion test**

Append this test to `backend/tests/test_storage_tasks_api.py`:

```python
def test_delete_storage_main_task_removes_rows_and_subtask_logs(db_session, test_user, monkeypatch, tmp_path):
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs, write_storage_subtask_log
    from backend.app.modules.storage.tasks.service import StorageTaskService

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="del-001")
    main = StorageMainTask(
        alias="delete-main",
        display_name="delete-main",
        source="single",
        storage_mode="single",
        status="completed",
        total_count=1,
        created_by=test_user.id,
        config_snapshot={},
    )
    db_session.add(main)
    db_session.flush()
    sub = StorageSubTask(
        main_task_id=main.id,
        movie_id=movie.id,
        movie_code="DEL-001",
        movie_title="delete movie",
        status="completed",
        step="done",
        storage_mode="single",
    )
    db_session.add(sub)
    db_session.flush()
    write_storage_subtask_log(str(sub.id), "INFO", "待删除日志", {"main_task_id": str(main.id)})
    db_session.commit()

    service = StorageTaskService(db_session, StorageConfigService())

    result = service.delete_main_task(main.id, test_user.id)

    assert result == {
        "id": str(main.id),
        "deleted_subtask_count": 1,
        "deleted_log_count": 1,
    }
    assert db_session.get(StorageMainTask, main.id) is None
    assert db_session.get(StorageSubTask, sub.id) is None
    assert read_storage_subtask_logs(str(sub.id)) == []
```

- [ ] **Step 2: Write the missing-log success test**

Append this test to `backend/tests/test_storage_tasks_api.py`:

```python
def test_delete_storage_main_task_succeeds_when_subtask_log_is_missing(db_session, test_user, monkeypatch, tmp_path):
    from backend.app.models.storage_task import StorageMainTask, StorageSubTask
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.service import StorageTaskService

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="del-missing-log")
    main = StorageMainTask(
        alias="delete-missing-log",
        display_name="delete-missing-log",
        source="single",
        storage_mode="single",
        status="completed",
        total_count=1,
        created_by=test_user.id,
        config_snapshot={},
    )
    db_session.add(main)
    db_session.flush()
    sub = StorageSubTask(
        main_task_id=main.id,
        movie_id=movie.id,
        movie_code="DEL-MISSING-LOG",
        movie_title="delete missing log movie",
        status="completed",
        step="done",
        storage_mode="single",
    )
    db_session.add(sub)
    db_session.commit()

    service = StorageTaskService(db_session, StorageConfigService())

    result = service.delete_main_task(main.id, test_user.id)

    assert result == {
        "id": str(main.id),
        "deleted_subtask_count": 1,
        "deleted_log_count": 0,
    }
    assert db_session.get(StorageMainTask, main.id) is None
    assert db_session.get(StorageSubTask, sub.id) is None
```

- [ ] **Step 3: Write the failing active-task rejection test**

Append this test to `backend/tests/test_storage_tasks_api.py`:

```python
def test_delete_storage_main_task_rejects_active_status(db_session, test_user):
    import pytest

    from backend.app.models.storage_task import StorageMainTask
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.service import StorageTaskService

    main = StorageMainTask(
        alias="active-main",
        display_name="active-main",
        source="batch",
        storage_mode="single",
        status="running",
        total_count=0,
        created_by=test_user.id,
        config_snapshot={},
    )
    db_session.add(main)
    db_session.commit()

    service = StorageTaskService(db_session, StorageConfigService())

    with pytest.raises(ValueError, match="运行中的存储任务不能删除，请先停止任务"):
        service.delete_main_task(main.id, test_user.id)

    assert db_session.get(StorageMainTask, main.id) is not None
```

- [ ] **Step 4: Run the service tests and verify they fail**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_removes_rows_and_subtask_logs \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_succeeds_when_subtask_log_is_missing \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_rejects_active_status \
  -q
```

Expected: FAIL with `AttributeError: 'StorageTaskService' object has no attribute 'delete_main_task'`.

- [ ] **Step 5: Add repository methods**

In `backend/app/modules/storage/tasks/repository.py`, add these methods after `get_subtask()`:

```python
    def list_subtask_ids(self, main_task_id: uuid.UUID) -> list[uuid.UUID]:
        rows = (
            self.db.query(StorageSubTask.id)
            .filter(StorageSubTask.main_task_id == main_task_id)
            .order_by(StorageSubTask.created_at.asc())
            .all()
        )
        return [row[0] for row in rows]

    def delete_main_task(self, main_task: StorageMainTask) -> None:
        self.db.delete(main_task)
```

- [ ] **Step 6: Add service deletion**

In `backend/app/modules/storage/tasks/service.py`, change the logs import:

```python
from backend.app.modules.storage.tasks.logs import delete_storage_subtask_log, write_storage_subtask_log
```

Then add this method after `restart_main_task()`:

```python
    def delete_main_task(self, task_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        task = self.repository.get_main(task_id)
        if task is None or task.created_by != user_id:
            raise LookupError("存储任务不存在")
        if task.status in {"queued", "running", "stopping"}:
            raise ValueError("运行中的存储任务不能删除，请先停止任务")

        subtask_ids = self.repository.list_subtask_ids(task.id)
        task_id_text = str(task.id)
        owner_id = str(task.created_by)
        deleted_log_count = 0
        for subtask_id in subtask_ids:
            if delete_storage_subtask_log(str(subtask_id)):
                deleted_log_count += 1

        self.repository.delete_main_task(task)
        self.db.commit()

        from backend.app.modules.storage.tasks.events import publish_storage_main_deleted
        publish_storage_main_deleted(owner_id, task_id_text)

        return {
            "id": task_id_text,
            "deleted_subtask_count": len(subtask_ids),
            "deleted_log_count": deleted_log_count,
        }
```

- [ ] **Step 7: Run the service tests and verify they pass**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_removes_rows_and_subtask_logs \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_succeeds_when_subtask_log_is_missing \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_rejects_active_status \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit service deletion**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/tasks/repository.py backend/app/modules/storage/tasks/service.py backend/tests/test_storage_tasks_api.py
git commit -m "feat: delete storage main tasks"
```

Expected: commit succeeds.

## Task 3: Backend Route And Realtime Delete Event

**Files:**
- Modify: `backend/app/modules/storage/tasks/events.py`
- Modify: `backend/app/modules/storage/tasks/router.py`
- Test: `backend/tests/test_storage_realtime_events.py`
- Test: `backend/tests/test_storage_tasks_api.py`

- [ ] **Step 1: Write the realtime event test**

Append this test to `backend/tests/test_storage_realtime_events.py`:

```python
def test_publish_storage_main_deleted_sends_deleted_event_to_owner() -> None:
    from backend.app.modules.realtime.bus import event_bus
    from backend.app.modules.storage.tasks.events import publish_storage_main_deleted

    owner_id = "user-storage-delete"
    queue = event_bus.subscribe(owner_id)
    try:
        publish_storage_main_deleted(owner_id, "main-delete-1")

        event = queue.get_nowait()
        assert event.event == "storage.main.deleted"
        assert event.scope == "storage.main"
        assert event.owner_id == owner_id
        assert event.resource_id == "main-delete-1"
        assert event.payload == {"id": "main-delete-1"}
    finally:
        event_bus.unsubscribe(owner_id, queue)
```

- [ ] **Step 2: Write the API delete test**

Append this test to `backend/tests/test_storage_tasks_api.py`:

```python
def test_delete_storage_main_task_api_removes_task_and_logs(client, db_session, auth_headers, test_user, monkeypatch, tmp_path):
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs, write_storage_subtask_log

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="api-del-001")
    created = client.post(
        "/api/storage/tasks/push",
        json={"movie_id": str(movie.id), "storage_mode": "single", "selected_storage_location": "A"},
        headers=auth_headers,
    ).json()["data"]
    subtask_id = client.get(
        f"/api/storage/tasks/{created['id']}/subtasks",
        headers=auth_headers,
    ).json()["data"]["rows"][0]["id"]
    write_storage_subtask_log(subtask_id, "INFO", "API 删除日志", {"main_task_id": created["id"]})

    from backend.app.models.storage_task import StorageMainTask

    main = db_session.get(StorageMainTask, uuid.UUID(created["id"]))
    main.status = "completed"
    db_session.commit()

    response = client.delete(f"/api/storage/tasks/{created['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert client.get(f"/api/storage/tasks/{created['id']}", headers=auth_headers).status_code == 404
    assert client.get(f"/api/storage/tasks/subtasks/{subtask_id}", headers=auth_headers).status_code == 404
    assert read_storage_subtask_logs(subtask_id) == []
```

- [ ] **Step 3: Write the active API rejection test**

Append this test to `backend/tests/test_storage_tasks_api.py`:

```python
def test_delete_storage_main_task_api_rejects_running_task(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="api-del-running")
    created = client.post(
        "/api/storage/tasks/push",
        json={"movie_id": str(movie.id), "storage_mode": "single", "selected_storage_location": "A"},
        headers=auth_headers,
    ).json()["data"]

    response = client.delete(f"/api/storage/tasks/{created['id']}", headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "运行中的存储任务不能删除，请先停止任务"
    assert client.get(f"/api/storage/tasks/{created['id']}", headers=auth_headers).status_code == 200
```

- [ ] **Step 4: Run the route tests and verify they fail**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_realtime_events.py::test_publish_storage_main_deleted_sends_deleted_event_to_owner \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_api_removes_task_and_logs \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_api_rejects_running_task \
  -q
```

Expected: FAIL because the event publisher and DELETE route do not exist.

- [ ] **Step 5: Add the realtime delete publisher**

In `backend/app/modules/storage/tasks/events.py`, add this function after `publish_storage_main_updated()`:

```python
def publish_storage_main_deleted(owner_id: str, task_id: str) -> None:
    event_bus.publish(make_realtime_event(
        event="storage.main.deleted",
        scope="storage.main",
        owner_id=owner_id,
        resource_id=task_id,
        payload={"id": task_id},
    ))
```

- [ ] **Step 6: Add the DELETE route**

In `backend/app/modules/storage/tasks/router.py`, add this route after `get_storage_main_task()` and before `list_storage_subtasks()`:

```python
@router.delete("/{main_task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_storage_main_task(main_task_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        service.delete_main_task(main_task_id, current_user.id)
        return None
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

- [ ] **Step 7: Run the route tests and verify they pass**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_realtime_events.py::test_publish_storage_main_deleted_sends_deleted_event_to_owner \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_api_removes_task_and_logs \
  backend/tests/test_storage_tasks_api.py::test_delete_storage_main_task_api_rejects_running_task \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit route and event**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/tasks/events.py backend/app/modules/storage/tasks/router.py backend/tests/test_storage_realtime_events.py backend/tests/test_storage_tasks_api.py
git commit -m "feat: expose storage task delete api"
```

Expected: commit succeeds.

## Task 4: Frontend API, Realtime Type, And List Delete UI

**Files:**
- Modify: `frontend/src/api/storage/storageTasks/index.ts`
- Modify: `frontend/src/realtime/types.ts`
- Modify: `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`
- Test: `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

- [ ] **Step 1: Update the frontend test mock and add a delete UI test**

Replace the imports at the top of `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx` with:

```typescript
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageTaskListPage from '../StorageTaskListPage'
import { deleteStorageMainTask, listStorageMainTasks } from '@/api/storage/storageTasks'
```

Replace the API mock in the same file with:

```typescript
vi.mock('@/api/storage/storageTasks', () => ({
  listStorageMainTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  stopStorageMainTask: vi.fn(),
  restartStorageMainTask: vi.fn(),
  deleteStorageMainTask: vi.fn().mockResolvedValue(undefined),
}))
```

Add this test inside the existing `describe('StorageTaskListPage', () => { ... })` block:

```typescript
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('deletes a completed storage task after confirmation', async () => {
    vi.mocked(listStorageMainTasks)
      .mockResolvedValueOnce({
        rows: [
          {
            id: 'task-delete-1',
            alias: '云存储_删除测试',
            display_name: '云存储_删除测试',
            source: 'single',
            storage_mode: 'single',
            status: 'completed',
            total_count: 1,
            success_count: 1,
            failed_count: 0,
            skipped_count: 0,
            created_at: '2026-07-05T00:00:00Z',
          },
        ],
        total: 1,
      })
      .mockResolvedValueOnce({ rows: [], total: 0 })

    render(<StorageTaskListPage />)

    expect(await screen.findByText('云存储_删除测试')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    fireEvent.click(await screen.findByRole('button', { name: '确定' }))

    await waitFor(() => {
      expect(deleteStorageMainTask).toHaveBeenCalledWith('task-delete-1')
    })
    await waitFor(() => {
      expect(listStorageMainTasks).toHaveBeenCalledTimes(2)
    })
  })
```

- [ ] **Step 2: Run the frontend delete UI test and verify it fails**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
```

Expected: FAIL because `deleteStorageMainTask` and the delete button are not implemented.

- [ ] **Step 3: Add the frontend delete API**

In `frontend/src/api/storage/storageTasks/index.ts`, add this function after `restartStorageMainTask()`:

```typescript
export function deleteStorageMainTask(id: string): Promise<void> {
  return request.delete<void>(`${BASE_URL}/${id}`)
}
```

- [ ] **Step 4: Add realtime delete types**

In `frontend/src/realtime/types.ts`, add this type after `StorageMainUpdatedPayload`:

```typescript
export type StorageMainDeletedPayload = {
  id: string
}
```

Then add this event name to `RealtimeEventName`:

```typescript
  | 'storage.main.deleted'
```

- [ ] **Step 5: Update the storage task list imports**

In `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`, replace:

```typescript
import { EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Space, Table, Tag } from 'antd'
import { listStorageMainTasks, restartStorageMainTask, stopStorageMainTask } from '@/api/storage/storageTasks'
```

with:

```typescript
import { DeleteOutlined, EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Popconfirm, Space, Table, Tag } from 'antd'
import {
  deleteStorageMainTask,
  listStorageMainTasks,
  restartStorageMainTask,
  stopStorageMainTask,
} from '@/api/storage/storageTasks'
```

And replace:

```typescript
import type { RealtimeEvent } from '@/realtime/types'
```

with:

```typescript
import type { RealtimeEvent, StorageMainDeletedPayload } from '@/realtime/types'
```

- [ ] **Step 6: Add delete handler and realtime delete subscription**

In `StorageTaskListPage()`, add this handler after `handleRestart`:

```typescript
  const handleDelete = useCallback(async (task: StorageMainTask) => {
    try {
      await deleteStorageMainTask(task.id)
      if (tasks.length === 1 && current > 1) {
        setCurrent((page) => page - 1)
        return
      }
      void fetchTasks(current, pageSize)
    } catch {
      // error handled by request interceptor
    }
  }, [current, fetchTasks, pageSize, tasks.length])
```

Replace the realtime `useEffect` body with:

```typescript
  useEffect(() => {
    connectRealtime()

    const unsubscribeUpdated = subscribeRealtime<StorageMainTask>(
      'storage.main.updated',
      (event: RealtimeEvent<StorageMainTask>) => {
        const updatedTask = event.payload
        setTasks((prev) =>
          prev.map((task) =>
            task.id === updatedTask.id ? { ...task, ...updatedTask } : task,
          ),
        )
      },
    )

    const unsubscribeDeleted = subscribeRealtime<StorageMainDeletedPayload>(
      'storage.main.deleted',
      (event: RealtimeEvent<StorageMainDeletedPayload>) => {
        setTasks((prev) => prev.filter((task) => task.id !== event.payload.id))
        setTotal((count) => Math.max(0, count - 1))
      },
    )

    return () => {
      unsubscribeUpdated()
      unsubscribeDeleted()
    }
  }, [])
```

- [ ] **Step 7: Add the delete button to the actions column**

In the actions column `render`, after the restart button block, add:

```tsx
          {!['queued', 'running', 'stopping'].includes(record.status) && (
            <Popconfirm
              title="删除存储任务"
              description="将删除主任务、子任务和对应日志，不会删除网盘文件。"
              okText="确定"
              cancelText="取消"
              onConfirm={() => void handleDelete(record)}
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
          )}
```

- [ ] **Step 8: Run the frontend delete UI test and verify it passes**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit frontend delete UI**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add frontend/src/api/storage/storageTasks/index.ts frontend/src/realtime/types.ts frontend/src/pages/storage/tasks/StorageTaskListPage.tsx frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
git commit -m "feat: add storage task delete UI"
```

Expected: commit succeeds.

## Task 5: Full Verification

**Files:**
- Verify: `backend/app/modules/storage/tasks/logs.py`
- Verify: `backend/app/modules/storage/tasks/repository.py`
- Verify: `backend/app/modules/storage/tasks/service.py`
- Verify: `backend/app/modules/storage/tasks/router.py`
- Verify: `backend/app/modules/storage/tasks/events.py`
- Verify: `frontend/src/api/storage/storageTasks/index.ts`
- Verify: `frontend/src/realtime/types.ts`
- Verify: `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`

- [ ] **Step 1: Run backend storage task tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_tasks_api.py \
  backend/tests/test_storage_realtime_events.py \
  backend/tests/test_storage_worker_service.py \
  -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run frontend storage task tests**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend typecheck build**

Run:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npm run build
```

Expected: build completes successfully.

- [ ] **Step 4: Manual API verification**

Start the backend:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

In the app, open the storage task list, choose a `completed`, `failed`, or `stopped` task, click `删除`, and confirm.

Expected:

```text
The row disappears from the storage task list.
GET /api/storage/tasks/{deleted_id} returns 404.
GET /api/storage/tasks/{deleted_id}/subtasks returns 404.
The files under APP_DATA_DIR/logs/storage/tasks/{subtask_id}.jsonl no longer exist for the deleted task.
No movie records, CloudDrive files, download folders, or target folders are deleted.
```

- [ ] **Step 5: Commit any verification fixes**

Run this only when verification changed tracked source files:

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge
git add backend/app/modules/storage/tasks/logs.py backend/app/modules/storage/tasks/repository.py backend/app/modules/storage/tasks/service.py backend/app/modules/storage/tasks/router.py backend/app/modules/storage/tasks/events.py backend/tests/test_storage_tasks_api.py backend/tests/test_storage_realtime_events.py frontend/src/api/storage/storageTasks/index.ts frontend/src/realtime/types.ts frontend/src/pages/storage/tasks/StorageTaskListPage.tsx frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
git commit -m "fix: verify storage task deletion"
```

Expected: commit succeeds when source files were changed during verification.

## Self-Review

- Spec coverage: The plan deletes `storage_main_tasks`, deletes `storage_sub_tasks` through existing cascade, and deletes every related JSONL log file.
- Ownership and active state: The service requires the current user id and rejects active tasks so the worker does not operate on deleted rows.
- Frontend coverage: The plan adds the API client, list action, confirmation UI, refresh after delete, and realtime deletion handling.
- Type consistency: Function names used by tests match the planned implementations: `delete_storage_subtask_log`, `list_subtask_ids`, `delete_main_task`, `publish_storage_main_deleted`, and `deleteStorageMainTask`.
- Verification: Backend tests cover row deletion, log deletion, route status codes, and realtime event payloads; frontend tests cover the delete button flow.

## Execution Options

1. Subagent-Driven (recommended) - Use `superpowers:subagent-driven-development` to dispatch one fresh worker per task, then review between tasks.
2. Inline Execution - Use `superpowers:executing-plans` to execute this plan in the current session with checkpoints.
