# Temporary Crawler Detail Task Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a crawler task-list `临时任务` action that creates a queued temporary run under an existing task from 1-50 JavDB detail-page URLs, reusing the normal detail crawling and movie persistence path.

**Architecture:** Treat a temporary task as a `CrawlRun` with `crawl_mode = "temporary"` and pre-created `CrawlRunDetailTask` rows, not as a new `CrawlTask`. Backend API validates the selected owned task and URL list, seeds pending detail rows, enqueues the run, and the threaded runtime skips list collection for temporary runs. Frontend adds a modal next to the existing `新建任务` action, loads task dictionary options, validates dynamic URL rows, calls the new API, and refreshes runtime status.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, Vitest 3, React Testing Library.

## Global Constraints

- Project scope remains the Media Forge refactor and optimization of `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.
- Supported input is JavDB movie detail URLs only, for example `https://javdb.com/v/...`.
- Do not create a new persistent `CrawlTask` for temporary runs.
- Temporary runs must create normal `CrawlRun` records attached to the selected existing task.
- Temporary runs must remain visible in the existing run list and run detail pages.
- Existing detail ingestion must handle movie creation, magnet persistence, duplicate checks, skipped rows, logs, stop, and retry.
- The frontend must keep the user on the task list after successful submission.
- The URL count must be 1 to 50 after trimming.

---

## File Structure

- Modify `backend/app/schemas/crawl_task.py`
  - Add `TemporaryCrawlRunCreate`.
- Modify `backend/app/modules/crawler/tasks/validation.py`
  - Add JavDB detail URL normalization/validation helpers.
- Modify `backend/app/modules/crawler/runtime/service.py`
  - Add `CrawlerRunService.create_temporary_detail_run()`.
  - Update detail processing to preserve parsed codes when detail rows start without a code.
  - Append selected task IDs when detail processing skips an already-existing movie.
- Modify `backend/app/modules/crawler/runtime/executor.py`
  - Treat temporary runs as detail-only runs.
- Modify `backend/app/modules/crawler/tasks/service.py`
  - Add `CrawlerTaskService.create_temporary_run()`.
- Modify `backend/app/modules/crawler/tasks/router.py`
  - Add `POST /api/crawler/tasks/temp-run`.
- Modify `backend/app/modules/crawler/runs/schemas.py`
  - Allow/serialize `crawl_mode = "temporary"` through existing string fields; no schema change is required unless tests reveal stricter frontend typing only.
- Modify backend tests:
  - `backend/tests/test_crawl_tasks_api.py`
  - `backend/tests/test_crawler_threaded_runtime.py`
- Modify `frontend/src/api/crawlTask/types.ts`
  - Add `TemporaryCrawlRunCreateParams`.
- Modify `frontend/src/api/crawlTask/index.ts`
  - Add `createTemporaryCrawlRun()`.
- Create `frontend/src/pages/crawler/tasks/components/TemporaryTaskModal.tsx`
  - Modal form for task selection and dynamic JavDB detail URL rows.
- Modify `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
  - Add `临时任务` button beside existing `新建任务`.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
  - Own modal open state and task-dictionary loading/retry wiring.
- Modify `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
  - Expose `fetchRuntimeStatuses` for refresh after temporary submit if not already consumed.
- Modify `frontend/src/api/crawlerRun/types.ts`
  - Add `temporary` to `CrawlMode`.
- Modify `frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx`
  - Display `temporary` as `临时`.
- Modify frontend tests:
  - `frontend/tests/crawler-run-controls.ui.test.tsx`
  - Add `frontend/tests/temporary-task-modal.ui.test.tsx`.

---

### Task 1: Backend Temporary Run API

**Files:**
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/validation.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Test: `backend/tests/test_crawl_tasks_api.py`

**Interfaces:**
- Produces `TemporaryCrawlRunCreate(BaseModel)`:
  - `task_id: uuid.UUID`
  - `detail_urls: list[str]`
- Produces `normalize_temporary_detail_urls(detail_urls: list[str]) -> list[str]`.
- Produces `CrawlerRunService.create_temporary_detail_run(task: CrawlTask, detail_urls: list[str]) -> CrawlRun`.
- Produces `CrawlerTaskService.create_temporary_run(data: TemporaryCrawlRunCreate, owner_id: uuid.UUID) -> dict`.
- Produces `POST /api/crawler/tasks/temp-run`.

- [ ] **Step 1: Add backend success and validation tests**

Append these tests to `backend/tests/test_crawl_tasks_api.py`:

```python
def test_create_temporary_run_seeds_detail_rows_and_enqueues(client: TestClient, admin_user, monkeypatch) -> None:
    from backend.app.models.crawl_run import CrawlRunDetailTask
    from backend.app.modules.crawler.runs.schemas import CrawlRunRead

    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]

    class Runtime:
        def __init__(self) -> None:
            self.enqueued: list[str] = []
            self.cleared: list[str] = []

        def enqueue_run(self, run_id: str) -> None:
            self.enqueued.append(run_id)

        def clear_stop(self, run_id: str) -> None:
            self.cleared.append(run_id)

    runtime = Runtime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    response = client.post(
        "/api/crawler/tasks/temp-run",
        json={
            "task_id": task_id,
            "detail_urls": [
                " https://javdb.com/v/abc123 ",
                "https://javdb.com/v/def456",
            ],
        },
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["task_id"] == task_id
    assert body["status"] == "queued"
    assert body["crawl_mode"] == "temporary"
    assert body["result"] == {"temporary": True, "detail_url_count": 2}
    assert runtime.enqueued == [body["id"]]

    session = TestingSessionLocal()
    try:
        rows = (
            session.query(CrawlRunDetailTask)
            .filter(CrawlRunDetailTask.run_id == body["id"])
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        assert [row.source_url for row in rows] == [
            "https://javdb.com/v/abc123",
            "https://javdb.com/v/def456",
        ]
        assert [row.status for row in rows] == ["pending_crawl", "pending_crawl"]
        assert [row.task_url_type for row in rows] == ["temporary_detail", "temporary_detail"]
        assert [row.source_url_name for row in rows] == ["临时任务", "临时任务"]
    finally:
        session.close()
```

Append validation tests:

```python
def test_create_temporary_run_rejects_invalid_inputs(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    task_response = client.post("/api/crawler/tasks", json=task_payload(), headers=headers)
    task_id = task_response.json()["data"]["id"]

    cases = [
        ([], "至少需要 1 条详情页 URL"),
        (["https://javdb.com/actors/abc"], "第 1 条不是有效的 JavDB 详情页 URL"),
        (["https://javdb.com/v/abc", " https://javdb.com/v/abc "], "第 2 条详情页 URL 重复"),
        ([f"https://javdb.com/v/{index:03d}" for index in range(51)], "临时任务最多支持 50 条详情页 URL"),
    ]

    for detail_urls, expected_message in cases:
        response = client.post(
            "/api/crawler/tasks/temp-run",
            json={"task_id": task_id, "detail_urls": detail_urls},
            headers=headers,
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert expected_message in response.json()["msg"]


def test_create_temporary_run_rejects_disabled_task(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    payload = task_payload()
    payload["is_skip"] = True
    task_response = client.post("/api/crawler/tasks", json=payload, headers=headers)
    task_id = task_response.json()["data"]["id"]

    response = client.post(
        "/api/crawler/tasks/temp-run",
        json={"task_id": task_id, "detail_urls": ["https://javdb.com/v/abc123"]},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["msg"] == "禁用任务不能执行"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::test_create_temporary_run_seeds_detail_rows_and_enqueues backend/tests/test_crawl_tasks_api.py::test_create_temporary_run_rejects_invalid_inputs backend/tests/test_crawl_tasks_api.py::test_create_temporary_run_rejects_disabled_task -v
```

Expected: FAIL because `POST /api/crawler/tasks/temp-run` does not exist.

- [ ] **Step 3: Add request schema**

In `backend/app/schemas/crawl_task.py`, add below `CrawlTaskUpdate`:

```python
class TemporaryCrawlRunCreate(BaseModel):
    task_id: uuid.UUID
    detail_urls: list[str] = Field(..., min_length=1, max_length=50)
```

- [ ] **Step 4: Add URL validation helper**

In `backend/app/modules/crawler/tasks/validation.py`, add imports if missing:

```python
from urllib.parse import urlparse
```

Add this function:

```python
def normalize_temporary_detail_urls(detail_urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    if not detail_urls:
        raise ValueError("至少需要 1 条详情页 URL")
    if len(detail_urls) > 50:
        raise ValueError("临时任务最多支持 50 条详情页 URL")
    for index, raw_url in enumerate(detail_urls, start=1):
        url = str(raw_url or "").strip()
        if not url:
            raise ValueError(f"第 {index} 条详情页 URL 不能为空")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"javdb.com", "www.javdb.com"} or not parsed.path.startswith("/v/"):
            raise ValueError(f"第 {index} 条不是有效的 JavDB 详情页 URL")
        if url in seen:
            raise ValueError(f"第 {index} 条详情页 URL 重复")
        seen.add(url)
        normalized.append(url)
    return normalized
```

- [ ] **Step 5: Add runtime method to create temporary run**

In `backend/app/modules/crawler/runtime/service.py`, add `upsert_detail_task` to imports:

```python
from backend.app.modules.crawler.runtime.detail_queue import upsert_detail_task
```

Add this method to `CrawlerRunService` after `create_run()`:

```python
    def create_temporary_detail_run(self, task: CrawlTask, detail_urls: list[str]) -> CrawlRun:
        run = CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="queued",
            crawl_mode="temporary",
            queued_at=datetime.now(),
            result={"temporary": True, "detail_url_count": len(detail_urls)},
        )
        self.db.add(run)
        self.db.flush()
        for detail_url in detail_urls:
            upsert_detail_task(
                self.db,
                run=run,
                task_name=task.name,
                item={
                    "url": detail_url,
                    "source_url": detail_url,
                    "name": "临时详情页",
                    "source_name": "临时详情页",
                    "_task_url_name": "临时任务",
                    "_task_url": detail_url,
                    "_task_final_url": detail_url,
                    "_task_url_type": "temporary_detail",
                },
            )
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        return run
```

- [ ] **Step 6: Add task service method**

In `backend/app/modules/crawler/tasks/service.py`, import the new schema/helper:

```python
from backend.app.modules.crawler.tasks.validation import (
    check_urls_unique,
    ensure_delete_mode_supported,
    normalize_temporary_detail_urls,
)
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskStats,
    CrawlTaskUpdate,
    TemporaryCrawlRunCreate,
)
```

Add this method after `run_task()`:

```python
    def create_temporary_run(
        self,
        data: TemporaryCrawlRunCreate,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(data.task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if task.is_skip:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")
        try:
            detail_urls = normalize_temporary_detail_urls(data.detail_urls)
            run = CrawlerRunService(self.db, get_runtime_state()).create_temporary_detail_run(task, detail_urls)
        except ValueError as exc:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            self.db.rollback()
            logger.exception("Create temporary crawler run failed")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
        return CrawlRunRead.model_validate(run).model_dump(mode="json")
```

- [ ] **Step 7: Add router endpoint**

In `backend/app/modules/crawler/tasks/router.py`, import `TemporaryCrawlRunCreate`:

```python
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskUpdate,
    ExtractNameRequest,
    TemporaryCrawlRunCreate,
)
```

Add before `@router.get("/{task_id}")`:

```python
@router.post("/temp-run", status_code=status.HTTP_201_CREATED)
def create_temporary_run(
    data: TemporaryCrawlRunCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.create_temporary_run(data, current_user.id))
```

- [ ] **Step 8: Run backend API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::test_create_temporary_run_seeds_detail_rows_and_enqueues backend/tests/test_crawl_tasks_api.py::test_create_temporary_run_rejects_invalid_inputs backend/tests/test_crawl_tasks_api.py::test_create_temporary_run_rejects_disabled_task -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/validation.py backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat: add temporary crawler run api"
```

---

### Task 2: Runtime Detail-Only Execution And Parsed-Code Ownership

**Files:**
- Modify: `backend/app/modules/crawler/runtime/executor.py`
- Modify: `backend/app/modules/crawler/runtime/threaded.py`
- Test: `backend/tests/test_crawler_threaded_runtime.py`

**Interfaces:**
- Consumes temporary run marker: `run.crawl_mode == "temporary"` or `(run.result or {}).get("temporary") is True`.
- Produces detail-only execution for temporary runs.
- Produces parsed-code persistence when a temp detail row has `code = None`.
- Produces source-task ownership append for skipped already-existing detail results.

- [ ] **Step 1: Add runtime tests**

Append to `backend/tests/test_crawler_threaded_runtime.py`:

```python
def test_temporary_run_skips_list_phase_and_processes_seeded_detail(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    run.crawl_mode = "temporary"
    run.result = {"temporary": True, "detail_url_count": 1}
    db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete()
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=None,
        source_url="https://javdb.com/v/temp001",
        source_name="临时详情页",
        source_url_name="临时任务",
        task_url="https://javdb.com/v/temp001",
        task_final_url="https://javdb.com/v/temp001",
        task_url_type="temporary_detail",
        status="pending_crawl",
        created_at=datetime.now(),
    ))
    db_session.commit()

    class TempSpider(FakeSpider):
        def collect_detail_tasks_for_url(self, **kwargs):
            raise AssertionError("temporary run must not collect list URLs")

        def run_single_detail_task(self, task, **kwargs):
            self.detail_started = True
            completed = {
                **task,
                "status": "completed",
                "detail": {"code": "TEMP-001", "source_name": "Temp Movie"},
            }
            kwargs["on_detail_completed"](completed)
            return completed

    spider = TempSpider()
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: spider)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime(), detail_only=True)

    row = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).one()
    assert result["total_tasks"] == 1
    assert result["saved"] == 1
    assert row.status == "saved"
    assert row.item_data["code"] == "TEMP-001"
    movie = db_session.scalar(select(Movie).where(Movie.code == "TEMP-001"))
    assert movie is not None
    assert str(task.id) in [str(value) for value in movie.source_task_ids]
```

Append existing-movie ownership test:

```python
def test_detail_skip_existing_appends_source_task_id(db_session, monkeypatch) -> None:
    task, run = make_task_and_run(db_session)
    run.crawl_mode = "temporary"
    db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete()
    db_session.add(Movie(code="TEMP-EXIST", source_name="Existing", source_task_ids=[]))
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=None,
        source_url="https://javdb.com/v/exist",
        source_name="临时详情页",
        source_url_name="临时任务",
        task_url_type="temporary_detail",
        status="pending_crawl",
        created_at=datetime.now(),
    ))
    db_session.commit()

    class ExistingSpider(FakeSpider):
        def collect_detail_tasks_for_url(self, **kwargs):
            raise AssertionError("temporary run must not collect list URLs")

        def run_single_detail_task(self, task, **kwargs):
            payload = {**task, "code": "TEMP-EXIST", "status": "skipped", "reason": "already_exists"}
            kwargs["on_item_already_exists"](payload)
            return payload

    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_spider", lambda: ExistingSpider())
    monkeypatch.setattr("backend.app.modules.crawler.runtime.threaded.build_pipeline", lambda: FakePipeline())

    result = execute_threaded_crawl(db_session, run, task, Runtime(), detail_only=True)
    movie = db_session.scalar(select(Movie).where(Movie.code == "TEMP-EXIST"))
    row = db_session.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).one()

    assert result["skipped"] == 1
    assert row.status == "skipped"
    assert row.error == "already_exists"
    assert str(task.id) in [str(value) for value in movie.source_task_ids]
```

- [ ] **Step 2: Run runtime tests to verify RED**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py::test_temporary_run_skips_list_phase_and_processes_seeded_detail backend/tests/test_crawler_threaded_runtime.py::test_detail_skip_existing_appends_source_task_id -v
```

Expected: FAIL because parsed codes are not preserved and existing skips do not append task IDs in threaded detail processing.

- [ ] **Step 3: Make executor choose detail-only for temporary runs**

In `backend/app/modules/crawler/runtime/executor.py`, replace:

```python
        detail_only = bool(pending_detail_retry_rows and (detail_phase_restart or detail_retry_requested))
```

with:

```python
        temporary_run = run.crawl_mode == "temporary" or bool((run.result or {}).get("temporary"))
        detail_only = temporary_run or bool(pending_detail_retry_rows and (detail_phase_restart or detail_retry_requested))
```

Update the log message branch:

```python
        if temporary_run:
            append_run_log_for_run(db, run, f"临时任务详情子任务 {len(pending_detail_retry_rows)} 条，跳过列表收集直接处理详情", "INFO")
        elif detail_only:
            append_run_log_for_run(
                db,
                run,
                f"检测到待重试详情子任务 {len(pending_detail_retry_rows)} 条，跳过列表收集直接重试详情",
                "INFO",
            )
```

- [ ] **Step 4: Preserve parsed code and append ownership on skipped detail**

In `backend/app/modules/crawler/runtime/threaded.py`, in `_process_single_detail()`, define a callback before `run_single_detail_task()`:

```python
    def handle_already_exists(task_info: dict) -> None:
        code = task_info.get("code") or detail.code
        if code:
            append_source_task_id(db, code, task.id)
```

Pass it to spider:

```python
        on_item_already_exists=handle_already_exists,
```

In the completed branch, replace:

```python
            "code": detail.code,
```

with:

```python
            "code": detail.code or detail_data.get("code") or result.get("code"),
```

After `cleaned` is truthy and before setting `detail.status`, add:

```python
            detail.code = detail.code or cleaned.get("code")
```

In the skipped branch, add:

```python
        detail.code = detail.code or result.get("code")
        if detail.code:
            append_source_task_id(db, detail.code, task.id)
```

- [ ] **Step 5: Run runtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py::test_temporary_run_skips_list_phase_and_processes_seeded_detail backend/tests/test_crawler_threaded_runtime.py::test_detail_skip_existing_appends_source_task_id -v
```

Expected: PASS.

- [ ] **Step 6: Run backend temporary API/runtime group**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py backend/tests/test_crawler_threaded_runtime.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/executor.py backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_threaded_runtime.py
git commit -m "feat: run temporary crawler details directly"
```

---

### Task 3: Frontend API And Temporary Task Modal

**Files:**
- Modify: `frontend/src/api/crawlTask/types.ts`
- Modify: `frontend/src/api/crawlTask/index.ts`
- Create: `frontend/src/pages/crawler/tasks/components/TemporaryTaskModal.tsx`
- Test: `frontend/tests/temporary-task-modal.ui.test.tsx`

**Interfaces:**
- Produces `TemporaryCrawlRunCreateParams`.
- Produces `createTemporaryCrawlRun(data: TemporaryCrawlRunCreateParams): Promise<CrawlRun>`.
- Produces `TemporaryTaskModal` props:
  - `open: boolean`
  - `tasks: TaskDictItem[]`
  - `tasksLoading: boolean`
  - `tasksError: string | null`
  - `submitting: boolean`
  - `onCancel: () => void`
  - `onReloadTasks: () => Promise<void> | void`
  - `onSubmit: (payload: TemporaryCrawlRunCreateParams) => Promise<void>`

- [ ] **Step 1: Add frontend modal tests**

Create `frontend/tests/temporary-task-modal.ui.test.tsx`:

```tsx
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TemporaryTaskModal from '../src/pages/crawler/tasks/components/TemporaryTaskModal'

function renderModal(props?: Partial<React.ComponentProps<typeof TemporaryTaskModal>>) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const onCancel = vi.fn()
  const onReloadTasks = vi.fn()
  render(
    <AntApp>
      <TemporaryTaskModal
        open
        tasks={[{ id: 'task-1', name: '任务A' }]}
        tasksLoading={false}
        tasksError={null}
        submitting={false}
        onCancel={onCancel}
        onReloadTasks={onReloadTasks}
        onSubmit={onSubmit}
        {...props}
      />
    </AntApp>,
  )
  return { onSubmit, onCancel, onReloadTasks }
}

describe('TemporaryTaskModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('submits selected task and normalized detail urls', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('归属任务'))
    await userEvent.click(await screen.findByText('任务A'))
    await userEvent.type(screen.getByPlaceholderText(/请输入 JavDB 详情页 URL/), ' https://javdb.com/v/abc123 ')
    await userEvent.click(screen.getByRole('button', { name: '创建临时任务' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        task_id: 'task-1',
        detail_urls: ['https://javdb.com/v/abc123'],
      })
    })
  })

  it('supports adding and removing url rows while keeping one row', async () => {
    renderModal()

    expect(screen.getAllByPlaceholderText(/请输入 JavDB 详情页 URL/)).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: '新增详情页' }))
    expect(screen.getAllByPlaceholderText(/请输入 JavDB 详情页 URL/)).toHaveLength(2)
    await userEvent.click(screen.getAllByRole('button', { name: '删除详情页' })[0])
    expect(screen.getAllByPlaceholderText(/请输入 JavDB 详情页 URL/)).toHaveLength(1)
    expect(screen.queryByRole('button', { name: '删除详情页' })).not.toBeInTheDocument()
  })

  it('blocks invalid and duplicate urls before submit', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('归属任务'))
    await userEvent.click(await screen.findByText('任务A'))
    await userEvent.type(screen.getByPlaceholderText(/请输入 JavDB 详情页 URL/), 'https://javdb.com/actors/abc')
    await userEvent.click(screen.getByRole('button', { name: '创建临时任务' }))
    expect(await screen.findByText('第 1 条不是有效的 JavDB 详情页 URL')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('keeps modal open and disables submit when task dictionary loading failed', async () => {
    const { onReloadTasks } = renderModal({
      tasks: [],
      tasksError: '任务列表加载失败',
    })

    expect(screen.getByText('任务列表加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建临时任务' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: '重新加载任务' }))
    expect(onReloadTasks).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run modal tests to verify RED**

Run:

```bash
cd frontend
npm test -- temporary-task-modal.ui.test.tsx
```

Expected: FAIL because `TemporaryTaskModal` does not exist.

- [ ] **Step 3: Add frontend API types**

In `frontend/src/api/crawlTask/types.ts`, import `CrawlRun` if needed from crawlerRun types in API file only. Add:

```ts
export interface TemporaryCrawlRunCreateParams {
  task_id: string
  detail_urls: string[]
}
```

In `frontend/src/api/crawlTask/index.ts`, import `CrawlRun`:

```ts
import type { CrawlRun } from '@/api/crawlerRun/types'
```

Add `TemporaryCrawlRunCreateParams` to existing type import list and add:

```ts
export function createTemporaryCrawlRun(data: TemporaryCrawlRunCreateParams): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/temp-run`, data)
}
```

- [ ] **Step 4: Create modal component**

Create `frontend/src/pages/crawler/tasks/components/TemporaryTaskModal.tsx`:

```tsx
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input, Modal, Select, Space, Typography } from 'antd'
import type { TemporaryCrawlRunCreateParams, TaskDictItem } from '@/api/crawlTask/types'

interface TemporaryTaskModalProps {
  open: boolean
  tasks: TaskDictItem[]
  tasksLoading: boolean
  tasksError: string | null
  submitting: boolean
  onCancel: () => void
  onReloadTasks: () => Promise<void> | void
  onSubmit: (payload: TemporaryCrawlRunCreateParams) => Promise<void>
}

interface FormValues {
  task_id: string
  detail_urls: Array<{ url: string }>
}

function normalizeAndValidateUrls(rows: Array<{ url?: string }>): string[] {
  const urls: string[] = []
  const seen = new Set<string>()
  if (rows.length === 0) {
    throw new Error('至少需要 1 条详情页 URL')
  }
  if (rows.length > 50) {
    throw new Error('临时任务最多支持 50 条详情页 URL')
  }
  rows.forEach((row, index) => {
    const url = String(row.url ?? '').trim()
    const rowNumber = index + 1
    if (!url) throw new Error(`第 ${rowNumber} 条详情页 URL 不能为空`)
    if (!/^https?:\/\/(www\.)?javdb\.com\/v\/[^/\s?#]+/i.test(url)) {
      throw new Error(`第 ${rowNumber} 条不是有效的 JavDB 详情页 URL`)
    }
    if (seen.has(url)) throw new Error(`第 ${rowNumber} 条详情页 URL 重复`)
    seen.add(url)
    urls.push(url)
  })
  return urls
}

export default function TemporaryTaskModal({
  open,
  tasks,
  tasksLoading,
  tasksError,
  submitting,
  onCancel,
  onReloadTasks,
  onSubmit,
}: TemporaryTaskModalProps) {
  const [form] = Form.useForm<FormValues>()
  const submitDisabled = Boolean(tasksError) || tasks.length === 0

  const handleFinish = async (values: FormValues) => {
    try {
      const detailUrls = normalizeAndValidateUrls(values.detail_urls ?? [])
      await onSubmit({ task_id: values.task_id, detail_urls: detailUrls })
      form.resetFields()
    } catch (error) {
      form.setFields([{ name: ['detail_urls'], errors: [error instanceof Error ? error.message : '临时任务参数错误'] }])
    }
  }

  return (
    <Modal
      title="创建临时任务"
      open={open}
      onCancel={onCancel}
      footer={null}
      width={720}
      destroyOnHidden
    >
      {tasksError && (
        <Alert
          type="error"
          showIcon
          message={tasksError}
          action={(
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void onReloadTasks()}>
              重新加载任务
            </Button>
          )}
          style={{ marginBottom: 16 }}
        />
      )}
      {!tasksError && tasks.length === 0 && (
        <Alert type="warning" showIcon message="请先创建爬虫任务" style={{ marginBottom: 16 }} />
      )}
      <Form<FormValues>
        form={form}
        layout="vertical"
        initialValues={{ detail_urls: [{ url: '' }] }}
        onFinish={(values) => void handleFinish(values)}
      >
        <Form.Item name="task_id" label="归属任务" rules={[{ required: true, message: '请选择归属任务' }]}>
          <Select
            aria-label="归属任务"
            loading={tasksLoading}
            disabled={tasksLoading || Boolean(tasksError)}
            placeholder="请选择归属任务"
            options={tasks.map((task) => ({ value: task.id, label: task.name }))}
          />
        </Form.Item>

        <Typography.Text strong>详情页 URL</Typography.Text>
        <Form.ErrorList errors={form.getFieldError('detail_urls')} />
        <Form.List name="detail_urls">
          {(fields, { add, remove }) => (
            <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
              {fields.map((field) => (
                <Space key={field.key} align="baseline" style={{ display: 'flex' }}>
                  <Form.Item
                    {...field}
                    name={[field.name, 'url']}
                    rules={[{ required: true, message: '请输入 JavDB 详情页 URL' }]}
                    style={{ flex: 1, marginBottom: 8 }}
                  >
                    <Input placeholder="请输入 JavDB 详情页 URL，例如 https://javdb.com/v/..." />
                  </Form.Item>
                  {fields.length > 1 && (
                    <Button aria-label="删除详情页" icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                  )}
                </Space>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ url: '' })}>
                新增详情页
              </Button>
            </Space>
          )}
        </Form.List>

        <Space style={{ marginTop: 20 }}>
          <Button type="primary" htmlType="submit" loading={submitting} disabled={submitDisabled}>
            创建临时任务
          </Button>
          <Button onClick={onCancel}>取消</Button>
        </Space>
      </Form>
    </Modal>
  )
}
```

- [ ] **Step 5: Run modal tests**

Run:

```bash
cd frontend
npm test -- temporary-task-modal.ui.test.tsx
```

Expected: PASS. If Ant Design form error rendering requires async waits, keep assertions inside `await screen.findByText(...)`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/crawlTask/types.ts frontend/src/api/crawlTask/index.ts frontend/src/pages/crawler/tasks/components/TemporaryTaskModal.tsx frontend/tests/temporary-task-modal.ui.test.tsx
git commit -m "feat: add temporary crawler task modal"
```

---

### Task 4: Frontend Task List Integration

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
- Modify: `frontend/src/api/crawlerRun/types.ts`
- Modify: `frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx`
- Test: `frontend/tests/crawler-run-controls.ui.test.tsx`

**Interfaces:**
- Consumes `TemporaryTaskModal`.
- Consumes `getTaskDict()` and `createTemporaryCrawlRun()`.
- Produces `TaskListCards` props:
  - `onTemporaryTaskClick: () => void`
- Produces `CrawlMode = 'incremental' | 'full' | 'temporary'`.

- [ ] **Step 1: Update task-list integration test**

In `frontend/tests/crawler-run-controls.ui.test.tsx`, update the crawlTask mock:

```tsx
import { createTemporaryCrawlRun, getCrawlTaskStats, getCrawlTasks, getTaskDict } from '../src/api/crawlTask'
```

```tsx
vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getCrawlTaskStats: vi.fn(),
  getCrawlTaskRuntimeStatuses: vi.fn().mockResolvedValue({ tasks: [], stats: { total: 1, idle: 1, running: 0, queued: 0, stopped: 0 } }),
  getTaskDict: vi.fn(),
  createTemporaryCrawlRun: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))
```

In `beforeEach()`, add:

```tsx
    vi.mocked(getTaskDict).mockResolvedValue([{ id: 'task-1', name: '任务A' }])
    vi.mocked(createTemporaryCrawlRun).mockResolvedValue({
      id: 'run-temp-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'queued',
      crawl_mode: 'temporary',
      queued_at: '2026-07-13T00:00:00',
      started_at: null,
      finished_at: null,
      result: { temporary: true, detail_url_count: 1 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-13T00:00:00',
      updated_at: null,
      logs: [],
    })
```

Append:

```tsx
  it('creates a temporary run from the task list modal', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '临时任务' }))
    await userEvent.click(await screen.findByLabelText('归属任务'))
    await userEvent.click(await screen.findByText('任务A'))
    await userEvent.type(screen.getByPlaceholderText(/请输入 JavDB 详情页 URL/), 'https://javdb.com/v/temp001')
    await userEvent.click(screen.getByRole('button', { name: '创建临时任务' }))

    await waitFor(() => {
      expect(createTemporaryCrawlRun).toHaveBeenCalledWith({
        task_id: 'task-1',
        detail_urls: ['https://javdb.com/v/temp001'],
      })
    })
    expect(await screen.findByText('临时任务已提交')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run integration test to verify RED**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx
```

Expected: FAIL because task list does not render `临时任务` and the API function does not exist until Task 3 is complete.

- [ ] **Step 3: Add temporary mode to run types and summary label**

In `frontend/src/api/crawlerRun/types.ts`, replace:

```ts
export type CrawlMode = 'incremental' | 'full'
```

with:

```ts
export type CrawlMode = 'incremental' | 'full' | 'temporary'
```

In `frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx`, add:

```tsx
const crawlModeLabels: Record<string, string> = {
  incremental: '增量',
  full: '全量',
  temporary: '临时',
}
```

Replace:

```tsx
<Descriptions.Item label="模式">{run.crawl_mode === 'incremental' ? '增量' : '全量'}</Descriptions.Item>
```

with:

```tsx
<Descriptions.Item label="模式">{crawlModeLabels[run.crawl_mode] ?? run.crawl_mode}</Descriptions.Item>
```

- [ ] **Step 4: Add task-list button prop**

In `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`, add prop:

```ts
  onTemporaryTaskClick: () => void
```

Destructure it in `TaskListCards()`. In the toolbar, render:

```tsx
        <Space>
          <Button onClick={onTemporaryTaskClick}>
            临时任务
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate({ to: '/crawler/tasks/new' })}
          >
            新建任务
          </Button>
        </Space>
```

This replaces the existing single `新建任务` button.

- [ ] **Step 5: Wire modal in task list page**

In `frontend/src/pages/crawler/tasks/TaskListPage.tsx`, import:

```tsx
import { useCallback, useState } from 'react'
import { App } from 'antd'
import { createTemporaryCrawlRun, getTaskDict } from '@/api/crawlTask'
import type { TaskDictItem, TemporaryCrawlRunCreateParams } from '@/api/crawlTask/types'
import TemporaryTaskModal from './components/TemporaryTaskModal'
```

Inside `TaskListPage()` add state:

```tsx
  const { message } = App.useApp()
  const [temporaryModalOpen, setTemporaryModalOpen] = useState(false)
  const [taskOptions, setTaskOptions] = useState<TaskDictItem[]>([])
  const [taskOptionsLoading, setTaskOptionsLoading] = useState(false)
  const [taskOptionsError, setTaskOptionsError] = useState<string | null>(null)
  const [temporarySubmitting, setTemporarySubmitting] = useState(false)
```

Add loaders:

```tsx
  const loadTaskOptions = useCallback(async () => {
    setTaskOptionsLoading(true)
    setTaskOptionsError(null)
    try {
      setTaskOptions(await getTaskDict())
    } catch (error) {
      setTaskOptionsError(error instanceof Error ? error.message : '任务列表加载失败')
    } finally {
      setTaskOptionsLoading(false)
    }
  }, [])

  const openTemporaryModal = useCallback(() => {
    setTemporaryModalOpen(true)
    void loadTaskOptions()
  }, [loadTaskOptions])

  const handleTemporarySubmit = useCallback(async (payload: TemporaryCrawlRunCreateParams) => {
    setTemporarySubmitting(true)
    try {
      await createTemporaryCrawlRun(payload)
      message.success('临时任务已提交')
      setTemporaryModalOpen(false)
      void fetchRuntimeStatuses()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '临时任务提交失败')
    } finally {
      setTemporarySubmitting(false)
    }
  }, [fetchRuntimeStatuses, message])
```

Pass the new prop:

```tsx
          onTemporaryTaskClick={openTemporaryModal}
```

Render modal after the panel:

```tsx
      <TemporaryTaskModal
        open={temporaryModalOpen}
        tasks={taskOptions}
        tasksLoading={taskOptionsLoading}
        tasksError={taskOptionsError}
        submitting={temporarySubmitting}
        onCancel={() => setTemporaryModalOpen(false)}
        onReloadTasks={loadTaskOptions}
        onSubmit={handleTemporarySubmit}
      />
```

- [ ] **Step 6: Run frontend integration test**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx temporary-task-modal.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/crawlerRun/types.ts frontend/src/pages/crawler/runs/components/RunSummaryCard.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx frontend/tests/crawler-run-controls.ui.test.tsx
git commit -m "feat: integrate temporary crawler task action"
```

---

## Final Verification

- [ ] Run backend tests:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py backend/tests/test_crawler_threaded_runtime.py backend/tests/test_crawler_runs_api.py -v
```

Expected: PASS.

- [ ] Run frontend tests:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx temporary-task-modal.ui.test.tsx run-detail-realtime.ui.test.tsx
```

Expected: PASS.

- [ ] Run frontend build:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] Run lint as an informational check:

```bash
cd frontend
npm run lint
```

Expected: The current repository may already fail lint with existing `react-hooks/set-state-in-effect` and `@ts-nocheck` violations. If lint fails only with pre-existing unrelated violations, record the output and do not expand scope. If lint reports new errors in files changed by this plan, fix them before completion.

## Self-Review

- Spec coverage:
  - Temporary task button beside new task: Task 4.
  - Existing-task ownership dropdown: Tasks 3 and 4.
  - Dynamic detail URL form with add/remove/minimum one: Task 3.
  - JavDB detail URL only: Tasks 1 and 3.
  - Temporary run attached to selected task and visible in run pages: Tasks 1 and 4.
  - Reuse normal detail crawler and movie persistence: Task 2.
  - Existing movie skip appends selected task ID: Task 2.
  - Queue behavior allows temporary runs while other runs exist: Task 1 uses existing runtime enqueue.
  - Dictionary loading failure opens modal and disables submit with retry: Task 3.
- Placeholder scan: no unfinished placeholder markers or deferred implementation notes remain.
- Type consistency: `TemporaryCrawlRunCreate`, `TemporaryCrawlRunCreateParams`, `createTemporaryCrawlRun`, `create_temporary_run`, and `create_temporary_detail_run` are defined before use.
