# Crawler Run Detail Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add single, selected, and retry-all controls for `crawl_failed` child tasks on the crawler run detail page, reusing the original run record.

**Architecture:** Add a focused run-detail retry API that validates ended parent runs, resets only selected `crawl_failed` detail rows to `pending_crawl`, and requeues the same run ID. Adjust detail-only execution to consume only `pending_crawl` rows so selected retry does not pull unrelated historical failures. Add frontend table selection, row actions, and retry handlers around the existing run detail snapshot and realtime flow.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, pytest, React 19, TypeScript 6, Vite 8, Ant Design 6, Vitest, React Testing Library.

## Global Constraints

- Retry must happen inside the original `crawl_runs` row; do not create a new run.
- Retry only `crawl_failed`; do not retry `save_failed`.
- Retry is allowed only for parent runs in `completed`, `failed`, or `stopped`.
- Support single-row retry, selected-row retry, and retry-all failed.
- Keep the feature inside the crawler refactor scope; do not add scheduling, retry history tables, or new queue models.
- Preserve existing run-level stop and restart semantics except where executor filtering is explicitly narrowed to exact `pending_crawl` retry rows.

---

## File Structure

- Modify `backend/app/modules/crawler/runs/schemas.py`
  - Add `RunDetailRetryRequest` for `detail_ids` and `retry_all`.
- Modify `backend/app/modules/crawler/runs/router.py`
  - Add `POST /api/crawler/runs/{run_id}/tasks/retry`.
- Modify `backend/app/modules/crawler/runtime/details.py`
  - Add constants/helpers for ended run statuses and pending retry row selection.
- Modify `backend/app/modules/crawler/runtime/service.py`
  - Add `CrawlerRunService.retry_failed_details(...)`.
- Modify `backend/app/modules/crawler/runtime/executor.py`
  - Use only `pending_crawl` rows for detail-only execution.
- Modify `backend/tests/test_crawler_runs_api.py`
  - Add API coverage for retry success and rejection cases.
- Modify `backend/tests/test_crawler_worker_service.py`
  - Add executor coverage proving unselected `crawl_failed` rows are not retried.
- Modify `frontend/src/api/crawlerRun/types.ts`
  - Add `RetryCrawlerRunTasksRequest`.
- Modify `frontend/src/api/crawlerRun/index.ts`
  - Add `retryCrawlerRunTasks`.
- Modify `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
  - Add retry handlers and retry loading state.
- Modify `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
  - Pass run status and retry handlers to `RunTaskTable`.
- Modify `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
  - Add selectable failed rows, row action, selected retry, and retry-all action.
- Create `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`
  - Cover button availability and API payloads.

---

### Task 1: Backend Retry API and Service

**Files:**
- Modify: `backend/app/modules/crawler/runs/schemas.py`
- Modify: `backend/app/modules/crawler/runs/router.py`
- Modify: `backend/app/modules/crawler/runtime/details.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Consumes: existing `CrawlerRunService`, `CrawlRun`, `CrawlRunDetailTask`, `publish_run_updated`, `publish_run_detail_updated`, `append_run_log_for_run`, and `get_runtime_state`.
- Produces:
  - `RunDetailRetryRequest(BaseModel)` with `detail_ids: list[uuid.UUID] = []` and `retry_all: bool = False`.
  - `CrawlerRunService.retry_failed_details(run_id: uuid.UUID, detail_ids: list[uuid.UUID] | None = None, retry_all: bool = False) -> CrawlRun`.
  - `ENDED_RUN_STATUSES = {"completed", "failed", "stopped"}`.
  - `POST /api/crawler/runs/{run_id}/tasks/retry`.

- [ ] **Step 1: Add failing backend API tests**

Append these tests to `backend/tests/test_crawler_runs_api.py`:

```python
def test_retry_one_failed_detail_requeues_same_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    session = TestingSessionLocal()
    run = CrawlRun(
        task_id=task_id,
        task_name="任务",
        status="completed",
        crawl_mode="incremental",
        queued_at=datetime.now(),
        started_at=datetime.now(),
        finished_at=datetime.now(),
        result={"total_tasks": 2},
        error="old error",
    )
    session.add(run)
    session.flush()
    failed = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="FAIL-001",
        source_url="https://example.test/fail-001",
        source_name="FAIL 001",
        status="crawl_failed",
        error="timeout",
        item_data={"stale": True},
        created_at=datetime.now(),
        crawled_at=datetime.now(),
    )
    other_failed = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="FAIL-002",
        source_url="https://example.test/fail-002",
        source_name="FAIL 002",
        status="crawl_failed",
        error="dns",
        created_at=datetime.now(),
        crawled_at=datetime.now(),
    )
    saved = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="SAVED-001",
        source_url="https://example.test/saved-001",
        source_name="SAVED 001",
        status="saved",
        created_at=datetime.now(),
        crawled_at=datetime.now(),
        saved_at=datetime.now(),
    )
    session.add_all([failed, other_failed, saved])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(failed.id)], "retry_all": False},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["result"] is None
    assert body["error"] is None
    assert runtime.cleared == [str(run.id)]
    assert runtime.enqueued == [str(run.id)]

    session.expire_all()
    statuses = {
        row.code: (row.status, row.error, row.item_data, row.crawled_at, row.saved_at)
        for row in session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    }
    assert statuses["FAIL-001"] == ("pending_crawl", None, None, None, None)
    assert statuses["FAIL-002"][0] == "crawl_failed"
    assert statuses["SAVED-001"][0] == "saved"


def test_retry_all_failed_details_requeues_all_crawl_failed_rows(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]
    session = TestingSessionLocal()
    run = CrawlRun(task_id=task_id, task_name="任务", status="failed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="crawl_failed", error="a", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="B", source_url="https://b", source_name="B", status="crawl_failed", error="b", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name="任务", code="C", source_url="https://c", source_name="C", status="save_failed", error="db", created_at=datetime.now(), crawled_at=datetime.now()),
    ])
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"retry_all": True},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["data"]["status"] == "queued"
    session.expire_all()
    statuses = {
        row.code: row.status
        for row in session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
    }
    assert statuses == {"A": "pending_crawl", "B": "pending_crawl", "C": "save_failed"}


def test_retry_failed_details_rejects_running_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="running", crawl_mode="incremental")
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="crawl_failed", created_at=datetime.now())
    session.add(detail)
    session.commit()
    runtime = RuntimeForStopRestart()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: runtime)

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(detail.id)]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "运行中" in response.json()["message"] or "运行中" in response.json()["detail"]
    assert runtime.enqueued == []


def test_retry_failed_details_rejects_non_crawl_failed_selection(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    session.add(run)
    session.flush()
    detail = CrawlRunDetailTask(run_id=run.id, task_name="任务", code="A", source_url="https://a", source_name="A", status="save_failed", created_at=datetime.now())
    session.add(detail)
    session.commit()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: RuntimeForStopRestart())

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(detail.id)]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "crawl_failed" in str(response.json())


def test_retry_failed_details_rejects_detail_from_other_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    run = CrawlRun(task_name="任务1", status="completed", crawl_mode="incremental")
    other_run = CrawlRun(task_name="任务2", status="completed", crawl_mode="incremental")
    session.add_all([run, other_run])
    session.flush()
    detail = CrawlRunDetailTask(run_id=other_run.id, task_name="任务2", code="A", source_url="https://a", source_name="A", status="crawl_failed", created_at=datetime.now())
    session.add(detail)
    session.commit()
    monkeypatch.setattr("backend.app.modules.crawler.runs.router.get_runtime_state", lambda: RuntimeForStopRestart())

    response = client.post(
        f"/api/crawler/runs/{run.id}/tasks/retry",
        json={"detail_ids": [str(detail.id)]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "不属于当前运行" in str(response.json()) or "无效" in str(response.json())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -k "retry_failed_details or retry_one_failed_detail or retry_all_failed" -v
```

Expected: FAIL with `404 Not Found` for `/tasks/retry` or import/name errors for missing request/service code.

- [ ] **Step 3: Add schema and constants**

In `backend/app/modules/crawler/runs/schemas.py`, add this import and model:

```python
from pydantic import BaseModel, ConfigDict, Field
```

Replace the existing `from pydantic import BaseModel, ConfigDict` import with the line above, then add:

```python
class RunDetailRetryRequest(BaseModel):
    detail_ids: list[uuid.UUID] = Field(default_factory=list)
    retry_all: bool = False
```

In `backend/app/modules/crawler/runtime/details.py`, add:

```python
ENDED_RUN_STATUSES = {"completed", "failed", "stopped"}
DETAIL_RETRY_STATUS = "pending_crawl"
```

- [ ] **Step 4: Implement service method**

In `backend/app/modules/crawler/runtime/service.py`, add `append_run_log_for_run` to the events import:

```python
from backend.app.modules.crawler.runtime.events import (
    append_run_log_for_run,
    publish_run_detail_updated,
    publish_run_updated,
)
```

Add `ENDED_RUN_STATUSES` to the details import:

```python
from backend.app.modules.crawler.runtime.details import (
    ENDED_RUN_STATUSES,
    RESTARTABLE_DETAIL_STATUSES,
    clear_run_detail_tasks,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)
```

Add this method inside `CrawlerRunService`, after `restart_run`:

```python
    def retry_failed_details(
        self,
        run_id: uuid.UUID,
        *,
        detail_ids: list[uuid.UUID] | None = None,
        retry_all: bool = False,
    ) -> CrawlRun:
        run = self.db.get(CrawlRun, run_id)
        if run is None:
            raise ValueError("运行记录不存在")
        if run.status not in ENDED_RUN_STATUSES:
            raise ValueError("运行中不能重试失败子任务")

        if retry_all:
            details = (
                self.db.query(CrawlRunDetailTask)
                .filter(
                    CrawlRunDetailTask.run_id == run.id,
                    CrawlRunDetailTask.status == "crawl_failed",
                )
                .order_by(CrawlRunDetailTask.created_at.asc())
                .all()
            )
            retry_label = "全部失败"
        else:
            if not detail_ids:
                raise ValueError("请选择要重新爬取的失败子任务")
            details = (
                self.db.query(CrawlRunDetailTask)
                .filter(CrawlRunDetailTask.id.in_(detail_ids))
                .order_by(CrawlRunDetailTask.created_at.asc())
                .all()
            )
            found_ids = {detail.id for detail in details}
            missing_ids = [detail_id for detail_id in detail_ids if detail_id not in found_ids]
            if missing_ids:
                raise ValueError("包含无效的子任务选择")
            retry_label = "选中项" if len(details) > 1 else "单条"

        if not details:
            raise ValueError("没有爬取失败的子任务可重试")
        for detail in details:
            if detail.run_id != run.id:
                raise ValueError("包含不属于当前运行的子任务")
            if detail.status != "crawl_failed":
                raise ValueError("只能重试 crawl_failed 状态的子任务")

        for detail in details:
            detail.status = "pending_crawl"
            detail.error = None
            detail.item_data = None
            detail.crawled_at = None
            detail.saved_at = None

        run.status = "queued"
        run.queued_at = datetime.now()
        run.started_at = None
        run.finished_at = None
        run.result = None
        run.error = None
        self.db.commit()
        self.db.refresh(run)

        self.runtime.clear_stop(str(run.id))
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        publish_run_detail_updated(self.db, run, details)
        publish_run_updated(self.db, run)
        append_run_log_for_run(self.db, run, f"重新爬取{retry_label}失败子任务: {len(details)} 条", "INFO")
        return run
```

- [ ] **Step 5: Add router endpoint**

In `backend/app/modules/crawler/runs/router.py`, change the schema import:

```python
from backend.app.modules.crawler.runs.schemas import CrawlRunDetailTaskRead, CrawlRunRead, RunDetailRetryRequest
```

Add this endpoint after `list_run_tasks` and before `delete_run`:

```python
@router.post("/{run_id}/tasks/retry", status_code=status.HTTP_201_CREATED)
def retry_run_tasks(
    run_id: uuid.UUID,
    payload: RunDetailRetryRequest,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    try:
        run = CrawlerRunService(db, get_runtime_state()).retry_failed_details(
            run_id,
            detail_ids=payload.detail_ids,
            retry_all=payload.retry_all,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
    return success(data=CrawlRunRead.model_validate(run).model_dump(mode="json"))
```

- [ ] **Step 6: Run backend API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py -k "retry_failed_details or retry_one_failed_detail or retry_all_failed" -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runs/schemas.py backend/app/modules/crawler/runs/router.py backend/app/modules/crawler/runtime/details.py backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_runs_api.py
git commit -m "feat: add crawler detail retry api"
```

---

### Task 2: Executor Uses Exact Pending Retry Rows

**Files:**
- Modify: `backend/app/modules/crawler/runtime/executor.py`
- Test: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes: `CrawlRunDetailTask.status == "pending_crawl"` as the exact retry queue created by Task 1.
- Produces: detail-only execution that passes only pending rows to `engine.crawl_detail_tasks(...)`.

- [ ] **Step 1: Add failing executor test**

Append this stub and test to `backend/tests/test_crawler_worker_service.py`:

```python
class DetailOnlyRecordingEngineStub:
    def __init__(self) -> None:
        self.detail_tasks = []

    def crawl_detail_tasks(self, task, *, detail_tasks, task_id=None, callbacks):
        self.detail_tasks = list(detail_tasks)
        return {
            "total_tasks": len(detail_tasks),
            "completed_tasks": 0,
            "failed_tasks": 0,
        }

    def crawl_task(self, task, *, task_id=None, crawl_mode="incremental", incremental_threshold=0, callbacks=None):
        raise AssertionError("detail retry must not run list crawl")


def test_execute_run_detail_retry_uses_only_pending_crawl_rows(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.executor import execute_run

    session = TestingSessionLocal()
    run, runtime = create_run_with_task("detail-retry")
    task = session.get(CrawlTask, run.task_id)
    run_obj = session.get(CrawlRun, run.id)
    run_obj.status = "queued"
    run_obj.started_at = datetime.now()
    session.add_all([
        CrawlRunDetailTask(run_id=run.id, task_name=task.name, code="PENDING-001", source_url="https://pending", source_name="Pending", status="pending_crawl", created_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name=task.name, code="FAILED-001", source_url="https://failed", source_name="Failed", status="crawl_failed", error="old", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name=task.name, code="SAVE-001", source_url="https://save", source_name="Save", status="save_failed", error="db", created_at=datetime.now(), crawled_at=datetime.now()),
        CrawlRunDetailTask(run_id=run.id, task_name=task.name, code="SAVED-001", source_url="https://saved", source_name="Saved", status="saved", created_at=datetime.now(), crawled_at=datetime.now(), saved_at=datetime.now()),
    ])
    session.commit()
    engine = DetailOnlyRecordingEngineStub()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.executor.get_crawler_engine", lambda: engine)

    execute_run(session, session.get(CrawlRun, run.id), runtime)

    assert [task_info["code"] for task_info in engine.detail_tasks] == ["PENDING-001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_detail_retry_uses_only_pending_crawl_rows -v
```

Expected: FAIL because the current executor includes `crawl_failed` and `save_failed` rows.

- [ ] **Step 3: Narrow executor detail-only selection**

In `backend/app/modules/crawler/runtime/executor.py`, replace the current `restartable_existing_details` block:

```python
        restartable_existing_details = [
            detail for detail in db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all()
            if detail.status in RESTARTABLE_DETAIL_STATUSES
        ]
        if detail_phase_restart and restartable_existing_details:
```

with:

```python
        pending_detail_retry_rows = (
            db.query(CrawlRunDetailTask)
            .filter(
                CrawlRunDetailTask.run_id == run.id,
                CrawlRunDetailTask.status == "pending_crawl",
            )
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        if detail_phase_restart and pending_detail_retry_rows:
```

Then replace both `restartable_existing_details` references in that branch with `pending_detail_retry_rows`:

```python
                f"检测到待重试详情子任务 {len(pending_detail_retry_rows)} 条，跳过列表收集直接重试详情",
```

and:

```python
                detail_tasks=[detail_row_to_task_info(detail) for detail in pending_detail_retry_rows],
```

Remove the now-unused `RESTARTABLE_DETAIL_STATUSES` import from `executor.py`.

- [ ] **Step 4: Run executor and restart regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_detail_retry_uses_only_pending_crawl_rows backend/tests/test_crawler_runs_api.py::test_restart_after_detail_phase_requeues_same_run_and_keeps_terminal_details -v
```

Expected: PASS. The run-level restart test should still pass because restart resets unfinished rows to `pending_crawl`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runtime/executor.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: limit detail retry execution to pending rows"
```

---

### Task 3: Frontend API, Hook, and Table Controls

**Files:**
- Modify: `frontend/src/api/crawlerRun/types.ts`
- Modify: `frontend/src/api/crawlerRun/index.ts`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`
- Modify: `frontend/src/pages/crawler/runs/RunDetailPage.tsx`
- Modify: `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
- Test: `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`

**Interfaces:**
- Consumes: backend endpoint from Task 1.
- Produces:
  - `RetryCrawlerRunTasksRequest`.
  - `retryCrawlerRunTasks(runId: string, payload: RetryCrawlerRunTasksRequest): Promise<CrawlRun>`.
  - `useRunDetail` retry handlers:
    - `handleRetryTask(detailId: string): Promise<void>`
    - `handleRetrySelectedTasks(detailIds: string[]): Promise<void>`
    - `handleRetryAllFailedTasks(): Promise<void>`
  - `RunTaskTable` props for run status, retry loading, and retry callbacks.

- [ ] **Step 1: Add failing frontend tests**

Create `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunDetailPage from '../RunDetailPage'
import {
  getCrawlerRun,
  getCrawlerRunLogs,
  getCrawlerRunTasks,
  retryCrawlerRunTasks,
} from '@/api/crawlerRun'

vi.mock('@tanstack/react-router', () => ({
  useParams: vi.fn().mockReturnValue({ id: 'run-1' }),
}))

vi.mock('@/api/crawlerRun', () => ({
  getCrawlerRun: vi.fn(),
  getCrawlerRunLogs: vi.fn().mockResolvedValue([]),
  getCrawlerRunTasks: vi.fn(),
  restartCrawlerRun: vi.fn(),
  stopCrawlerRun: vi.fn(),
  retryCrawlerRunTasks: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn().mockReturnValue(() => {}),
}))

const endedRun = {
  id: 'run-1',
  task_id: 'task-1',
  task_name: '任务',
  status: 'completed',
  crawl_mode: 'incremental',
  queued_at: null,
  started_at: null,
  finished_at: null,
  result: null,
  error: null,
  resumed_from: null,
  created_at: '2026-07-08T00:00:00Z',
  updated_at: null,
  logs: [],
}

const failedTask = {
  id: 'detail-1',
  run_id: 'run-1',
  task_name: '任务',
  code: 'FAIL-001',
  source_url: 'https://example.test/fail',
  source_name: 'FAIL 001',
  status: 'crawl_failed',
  error: 'timeout',
  item_data: null,
  created_at: '2026-07-08T00:00:00Z',
  crawled_at: null,
  saved_at: null,
}

const savedTask = {
  ...failedTask,
  id: 'detail-2',
  code: 'SAVED-001',
  source_name: 'SAVED 001',
  status: 'saved',
  error: null,
}

describe('RunDetail retry controls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getCrawlerRun).mockResolvedValue(endedRun)
    vi.mocked(getCrawlerRunLogs).mockResolvedValue([])
    vi.mocked(getCrawlerRunTasks).mockResolvedValue({ rows: [failedTask, savedTask], total: 2 })
    vi.mocked(retryCrawlerRunTasks).mockResolvedValue({ ...endedRun, status: 'queued' })
  })

  it('retries one failed row with one detail id', async () => {
    render(<RunDetailPage />)

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新爬取' }))
    const okButton = await screen.findByRole('button', { name: '确 定' })
    fireEvent.click(okButton)

    await waitFor(() => {
      expect(retryCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
        detail_ids: ['detail-1'],
        retry_all: false,
      })
    })
  })

  it('retries all failed rows with retry_all payload', async () => {
    render(<RunDetailPage />)

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新爬取全部失败' }))
    const okButton = await screen.findByRole('button', { name: '确 定' })
    fireEvent.click(okButton)

    await waitFor(() => {
      expect(retryCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
        retry_all: true,
      })
    })
  })

  it('hides retry controls while run is running', async () => {
    vi.mocked(getCrawlerRun).mockResolvedValueOnce({ ...endedRun, status: 'running' })

    render(<RunDetailPage />)

    expect(await screen.findByText('FAIL-001')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新爬取' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新爬取全部失败' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run frontend test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
```

Expected: FAIL because `retryCrawlerRunTasks` and retry controls do not exist.

- [ ] **Step 3: Add frontend API function**

In `frontend/src/api/crawlerRun/types.ts`, add:

```ts
export interface RetryCrawlerRunTasksRequest {
  detail_ids?: string[]
  retry_all?: boolean
}
```

In `frontend/src/api/crawlerRun/index.ts`, add `RetryCrawlerRunTasksRequest` to the type import:

```ts
  RetryCrawlerRunTasksRequest,
```

Then add:

```ts
export function retryCrawlerRunTasks(
  runId: string,
  payload: RetryCrawlerRunTasksRequest,
): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${runId}/tasks/retry`, payload)
}
```

- [ ] **Step 4: Add retry handlers to hook**

In `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts`, add `retryCrawlerRunTasks` to the API import.

Change action loading state:

```ts
const [actionLoading, setActionLoading] = useState<'stop' | 'restart' | 'retry' | null>(null)
```

Add these callbacks after `handleRestart`:

```ts
  const runRetryRequest = useCallback(
    async (payload: { detail_ids?: string[]; retry_all?: boolean }, successText: string) => {
      if (!id) return
      setActionLoading('retry')
      try {
        const retriedRun = await retryCrawlerRunTasks(id, payload)
        setRun(retriedRun)
        message.success(successText)
        resyncSnapshot()
      } catch (error) {
        const msg = error instanceof Error ? error.message : '重新爬取失败'
        message.error(msg)
        resyncSnapshot()
      } finally {
        setActionLoading(null)
      }
    },
    [id, resyncSnapshot],
  )

  const handleRetryTask = useCallback(
    async (detailId: string) => {
      await runRetryRequest({ detail_ids: [detailId], retry_all: false }, '已重新爬取该失败子任务')
    },
    [runRetryRequest],
  )

  const handleRetrySelectedTasks = useCallback(
    async (detailIds: string[]) => {
      await runRetryRequest({ detail_ids: detailIds, retry_all: false }, '已重新爬取选中失败子任务')
    },
    [runRetryRequest],
  )

  const handleRetryAllFailedTasks = useCallback(async () => {
    await runRetryRequest({ retry_all: true }, '已重新爬取全部失败子任务')
  }, [runRetryRequest])
```

Return these three handlers from the hook.

- [ ] **Step 5: Pass props from page**

In `frontend/src/pages/crawler/runs/RunDetailPage.tsx`, add these props to `RunTaskTable`:

```tsx
        actionLoading={detail.actionLoading}
        runStatus={detail.run?.status}
        onRetryAllFailed={detail.handleRetryAllFailedTasks}
        onRetrySelected={detail.handleRetrySelectedTasks}
        onRetryTask={detail.handleRetryTask}
```

- [ ] **Step 6: Implement table controls**

In `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`, update imports:

```tsx
import { Button, Card, Input, Modal, Select, Space, Table, Tag } from 'antd'
```

Move `columns` inside `RunTaskTable` so it can use props, then update props:

```tsx
  actionLoading: 'stop' | 'restart' | 'retry' | null
  runStatus: string | undefined
  onRetryTask: (detailId: string) => Promise<void>
  onRetrySelected: (detailIds: string[]) => Promise<void>
  onRetryAllFailed: () => Promise<void>
```

Inside the component add:

```tsx
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const retryEnabled = runStatus === 'completed' || runStatus === 'failed' || runStatus === 'stopped'
  const failedTasks = tasks.filter((task) => task.status === 'crawl_failed')
  const selectedFailedIds = selectedRowKeys.map(String)

  const confirmRetryTask = (detailId: string) => {
    Modal.confirm({
      title: '重新爬取失败子任务',
      content: '确认重新爬取该失败子任务？',
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        await onRetryTask(detailId)
        setSelectedRowKeys([])
      },
    })
  }

  const confirmRetrySelected = () => {
    Modal.confirm({
      title: '重新爬取选中项',
      content: `确认重新爬取选中的 ${selectedFailedIds.length} 个失败子任务？`,
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        await onRetrySelected(selectedFailedIds)
        setSelectedRowKeys([])
      },
    })
  }

  const confirmRetryAllFailed = () => {
    Modal.confirm({
      title: '重新爬取全部失败',
      content: `确认重新爬取全部 ${failedTasks.length} 个失败子任务？`,
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        await onRetryAllFailed()
        setSelectedRowKeys([])
      },
    })
  }
```

Add an operation column:

```tsx
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) =>
        retryEnabled && record.status === 'crawl_failed' ? (
          <Button
            type="link"
            size="small"
            loading={actionLoading === 'retry'}
            onClick={() => confirmRetryTask(record.id)}
          >
            重新爬取
          </Button>
        ) : null,
    },
```

Add buttons in the toolbar `Space` after `Input.Search`:

```tsx
        {retryEnabled && selectedFailedIds.length > 0 && (
          <Button loading={actionLoading === 'retry'} onClick={confirmRetrySelected}>
            重新爬取选中项
          </Button>
        )}
        {retryEnabled && failedTasks.length > 0 && (
          <Button loading={actionLoading === 'retry'} onClick={confirmRetryAllFailed}>
            重新爬取全部失败
          </Button>
        )}
```

Add `rowSelection` to `Table`:

```tsx
        rowSelection={
          retryEnabled
            ? {
                selectedRowKeys,
                onChange: setSelectedRowKeys,
                getCheckboxProps: (record) => ({
                  disabled: record.status !== 'crawl_failed',
                }),
              }
            : undefined
        }
```

Add `useState` and `React` key import support:

```tsx
import { useState } from 'react'
```

- [ ] **Step 7: Run frontend retry test**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/crawlerRun/types.ts frontend/src/api/crawlerRun/index.ts frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/src/pages/crawler/runs/components/RunTaskTable.tsx frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
git commit -m "feat: add crawler detail retry controls"
```

---

### Task 4: Full Verification and Polish

**Files:**
- Modify only files touched by Tasks 1-3 if verification reveals issues.

**Interfaces:**
- Consumes: completed backend and frontend retry implementation.
- Produces: passing focused regression suite and production frontend build.

- [ ] **Step 1: Run backend focused suite**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd frontend
npm test -- src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS with Vite production build output.

- [ ] **Step 4: Run lint if available**

Run:

```bash
cd frontend
npm run lint
```

Expected: PASS. If it fails on pre-existing unrelated files, record the unrelated failures and keep retry changes lint-clean.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` has no output. `git status --short` shows only intended retry implementation files plus any pre-existing unrelated worktree changes.

- [ ] **Step 6: Commit final polish if needed**

If Step 1-5 required fixes, commit only retry-related files:

```bash
git add backend/app/modules/crawler/runs/schemas.py backend/app/modules/crawler/runs/router.py backend/app/modules/crawler/runtime/details.py backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runtime/executor.py backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_worker_service.py frontend/src/api/crawlerRun/types.ts frontend/src/api/crawlerRun/index.ts frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/src/pages/crawler/runs/RunDetailPage.tsx frontend/src/pages/crawler/runs/components/RunTaskTable.tsx frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
git commit -m "test: verify crawler detail retry flow"
```

Expected: commit succeeds, or no commit is needed because earlier task commits already contain the final verified state.

---

## Self-Review Notes

- Spec coverage: Backend API, service validation, executor exact pending selection, frontend single/selected/all controls, error handling, and tests are each mapped to tasks.
- Red-flag scan: No incomplete marker language is present.
- Type consistency: The plan consistently uses `RunDetailRetryRequest`, `retryCrawlerRunTasks`, `detail_ids`, `retry_all`, and `CrawlerRunService.retry_failed_details`.
