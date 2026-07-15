# Crawler Task URL Subset Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-task `URL 爬取` so users can run one crawler task against a selected subset of its configured URLs in incremental or full mode.

**Architecture:** The backend adds a normal `CrawlRun` creation path that stores selected task URL IDs in `run.result`, then filters the scraper task from that immutable run snapshot at execution time. The frontend adds a dedicated `useTaskUrlRun` hook plus a pure modal form, and task cards only trigger the hook.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic, pytest, React 19, TypeScript 6, Ant Design 6, Vitest, React Testing Library.

## Global Constraints

- Add a `URL 爬取` action to each crawler task card.
- Let the user multi-select existing URLs from that task.
- Let the user choose `incremental` or `full`.
- Create a normal `CrawlRun` attached to the task.
- Preserve current stop, restart, realtime status, run list, run detail, logs, duplicate handling, and movie persistence behavior.
- Keep frontend orchestration in a dedicated hook.
- No support for manually entered URLs in this modal.
- No support for raw movie codes.
- No new persistent task type.
- No changes to the existing global `临时任务` detail-page workflow.
- No automatic navigation to the run detail page after submit.
- The request sends `url_ids`, and the run stores the selected IDs in `run.result`.
- Restarting a URL subset run must run the same selected URL subset again.

---

## File Structure

Backend files to modify:

- `backend/app/schemas/crawl_task.py`: add `CrawlTaskUrlRunCreate`.
- `backend/app/modules/crawler/tasks/router.py`: add `POST /api/crawler/tasks/{task_id}/url-run`.
- `backend/app/modules/crawler/tasks/service.py`: add `create_url_subset_run`.
- `backend/app/modules/crawler/runtime/service.py`: extend `create_run` with optional selected task URL IDs.
- `backend/app/modules/crawler/runtime/task_adapter.py`: add URL ID filtering support while preserving task URL order.
- `backend/app/modules/crawler/runtime/executor.py`: read the URL subset snapshot and pass it to the adapter path.
- `backend/app/modules/crawler/runtime/threaded.py`: pass selected URL IDs into `to_scraper_task`.

Backend tests:

- `backend/tests/test_crawler_task_url_subset_run.py`: API/service validation and run snapshot tests.
- `backend/tests/test_crawler_runtime_adapters.py`: adapter filtering and order tests.

Frontend files to modify or create:

- `frontend/src/api/crawlTask/types.ts`: add `TaskUrlRunCreateParams` and `TaskUrlRunFormValues`.
- `frontend/src/api/crawlTask/index.ts`: add `createTaskUrlRun`.
- `frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts`: dedicated hook for modal state, submit, messages, and runtime refresh callback.
- `frontend/src/pages/crawler/tasks/components/TaskUrlRunModal.tsx`: pure form modal.
- `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`: add per-card `URL 爬取` action.
- `frontend/src/pages/crawler/tasks/TaskListPage.tsx`: wire hook, modal, and task cards.

Frontend tests:

- `frontend/tests/task-url-run-modal.ui.test.tsx`: modal validation and payload tests.
- `frontend/tests/crawler-run-controls.ui.test.tsx`: task list integration and successful submit path.

Do not modify unrelated current work in:

- `frontend/src/pages/dashboard/DashboardPage.module.less`
- `frontend/src/pages/dashboard/components/DashboardMetricCards.tsx`
- `frontend/src/pages/init/InitPage.tsx`
- `docs/superpowers/plans/2026-07-14-dashboard-runtime-overview.md`

---

### Task 1: Backend URL Subset Run API

**Files:**
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Create: `backend/tests/test_crawler_task_url_subset_run.py`

**Interfaces:**
- Consumes:
  - `CrawlerRunService.create_run(task: CrawlTask, crawl_mode: str, selected_task_url_ids: list[uuid.UUID] | None = None) -> CrawlRun`
- Produces:
  - `CrawlTaskUrlRunCreate(url_ids: list[uuid.UUID], crawl_mode: Literal["incremental", "full"])`
  - `CrawlerTaskService.create_url_subset_run(task_id: uuid.UUID, data: CrawlTaskUrlRunCreate, owner_id: uuid.UUID) -> dict`
  - `POST /api/crawler/tasks/{task_id}/url-run`

- [ ] **Step 1: Write failing backend API tests**

Create `backend/tests/test_crawler_task_url_subset_run.py`:

```python
from http import HTTPStatus
import uuid

from fastapi.testclient import TestClient

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.crawl_run import CrawlRun
from backend.tests.conftest import TestingSessionLocal


def auth_headers(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


class FakeRuntime:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue_run(self, run_id: str) -> None:
        self.enqueued.append(run_id)


def make_task(owner_id: uuid.UUID, *, name: str = "任务A", is_skip: bool = False) -> tuple[CrawlTask, CrawlTaskUrl, CrawlTaskUrl]:
    session = TestingSessionLocal()
    task = CrawlTask(name=name, storage_location="JP", is_skip=is_skip, owner_id=owner_id)
    task.urls = [
        CrawlTaskUrl(
            position=0,
            url="https://javdb.com/actors/a",
            url_type="actors",
            has_magnet=True,
            has_chinese_sub=False,
            sort_type=0,
            source="javdb",
            final_url="https://javdb.com/actors/a",
            url_name="演员A",
        ),
        CrawlTaskUrl(
            position=1,
            url="https://javdb.com/tags/b",
            url_type="tags",
            has_magnet=False,
            has_chinese_sub=True,
            sort_type=0,
            source="javdb",
            final_url="https://javdb.com/tags/b",
            url_name="标签B",
        ),
    ]
    session.add(task)
    session.commit()
    session.refresh(task)
    first, second = task.urls
    session.expunge(task)
    session.close()
    return task, first, second


def test_url_subset_run_creates_queued_incremental_run(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client)
    task, first_url, second_url = make_task(admin_user.id)
    runtime = FakeRuntime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id), str(second_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()["data"]
    assert body["task_id"] == str(task.id)
    assert body["status"] == "queued"
    assert body["crawl_mode"] == "incremental"
    assert body["result"] == {
        "url_subset": True,
        "selected_task_url_ids": [str(first_url.id), str(second_url.id)],
        "selected_task_url_count": 2,
    }
    assert runtime.enqueued == [body["id"]]


def test_url_subset_run_accepts_full_mode(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id)
    runtime = FakeRuntime()
    monkeypatch.setattr("backend.app.modules.crawler.tasks.service.get_runtime_state", lambda: runtime)
    monkeypatch.setattr("backend.app.modules.crawler.runtime.service.ensure_crawler_worker_started", lambda runtime: None)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id)], "crawl_mode": "full"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["data"]["crawl_mode"] == "full"


def test_url_subset_run_rejects_duplicate_url_ids(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id), str(first_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "任务 URL 不能重复选择"


def test_url_subset_run_rejects_empty_url_selection(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, _first_url, _second_url = make_task(admin_user.id)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "至少选择 1 条任务 URL"


def test_url_subset_run_rejects_foreign_url_id(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id, name="任务A")
    other_task, other_url, _other_second = make_task(admin_user.id, name="任务B")

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id), str(other_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert str(other_task.id) != str(task.id)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "选择的 URL 不属于该任务"


def test_url_subset_run_rejects_disabled_task(client: TestClient, admin_user) -> None:
    headers = auth_headers(client)
    task, first_url, _second_url = make_task(admin_user.id, is_skip=True)

    response = client.post(
        f"/api/crawler/tasks/{task.id}/url-run",
        json={"url_ids": [str(first_url.id)], "crawl_mode": "incremental"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == "禁用任务不能执行"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_task_url_subset_run.py -v
```

Expected: FAIL with `404 Not Found` or import failure because `url-run` and `CrawlTaskUrlRunCreate` do not exist.

- [ ] **Step 3: Add request schema**

Modify `backend/app/schemas/crawl_task.py` imports:

```python
from typing import Literal
```

Add this model below `TemporaryCrawlRunCreate`:

```python
class CrawlTaskUrlRunCreate(BaseModel):
    url_ids: list[uuid.UUID] = Field(default_factory=list)
    crawl_mode: Literal["incremental", "full"]
```

- [ ] **Step 4: Extend runtime run creation**

Modify `backend/app/modules/crawler/runtime/service.py` `create_run` signature and body:

```python
    def create_run(
        self,
        task: CrawlTask,
        crawl_mode: str,
        *,
        selected_task_url_ids: list[uuid.UUID] | None = None,
    ) -> CrawlRun:
        if crawl_mode not in {"incremental", "full"}:
            raise ValueError("crawl_mode must be incremental or full")
        result = None
        if selected_task_url_ids is not None:
            selected_ids = [str(url_id) for url_id in selected_task_url_ids]
            result = {
                "url_subset": True,
                "selected_task_url_ids": selected_ids,
                "selected_task_url_count": len(selected_ids),
            }
        run = CrawlRun(
            task_id=task.id,
            task_name=task.name,
            status="queued",
            crawl_mode=crawl_mode,
            queued_at=datetime.now(),
            result=result,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        self.runtime.enqueue_run(str(run.id))
        self._ensure_worker_started()
        return run
```

- [ ] **Step 5: Add task service method**

Modify `backend/app/modules/crawler/tasks/service.py` imports:

```python
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskStats,
    CrawlTaskUpdate,
    CrawlTaskUrlRunCreate,
    TemporaryCrawlRunCreate,
)
```

Add this method after `run_task`:

```python
    def create_url_subset_run(
        self,
        task_id: uuid.UUID,
        data: CrawlTaskUrlRunCreate,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if task.is_skip:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")

        selected_ids = list(data.url_ids)
        if not selected_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择 1 条任务 URL")
        if len(set(selected_ids)) != len(selected_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务 URL 不能重复选择")

        task_url_ids = {row.id for row in task.urls}
        if not set(selected_ids).issubset(task_url_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="选择的 URL 不属于该任务")

        try:
            run = CrawlerRunService(self.db, get_runtime_state()).create_run(
                task,
                data.crawl_mode,
                selected_task_url_ids=selected_ids,
            )
        except Exception as exc:
            self.db.rollback()
            logger.exception("Create crawler URL subset run failed")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
        return CrawlRunRead.model_validate(run).model_dump(mode="json")
```

- [ ] **Step 6: Add router endpoint**

Modify `backend/app/modules/crawler/tasks/router.py` imports:

```python
    CrawlTaskUrlRunCreate,
```

Add endpoint after `run_task`:

```python
@router.post("/{task_id}/url-run", status_code=status.HTTP_201_CREATED)
def run_task_url_subset(
    task_id: uuid.UUID,
    data: CrawlTaskUrlRunCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.create_url_subset_run(task_id, data, current_user.id))
```

- [ ] **Step 7: Run backend API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_task_url_subset_run.py -v
```

Expected: all tests in `test_crawler_task_url_subset_run.py` pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/crawl_task.py backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_task_url_subset_run.py
git commit -m "feat: add crawler task url subset run api"
```

---

### Task 2: Runtime Task URL Filtering

**Files:**
- Modify: `backend/app/modules/crawler/runtime/task_adapter.py`
- Modify: `backend/app/modules/crawler/runtime/executor.py`
- Modify: `backend/tests/test_crawler_runtime_adapters.py`

**Interfaces:**
- Consumes:
  - `run.result["selected_task_url_ids"]` from Task 1.
- Produces:
  - `selected_task_url_ids_from_run(run: CrawlRun) -> list[uuid.UUID] | None`
  - `to_scraper_task(task: BackendCrawlTask, selected_url_ids: list[uuid.UUID] | None = None) -> CrawlTask`

- [ ] **Step 1: Add failing adapter tests**

Append to `backend/tests/test_crawler_runtime_adapters.py`:

```python
import uuid


def test_to_scraper_task_filters_selected_url_ids_and_preserves_task_order(admin_user) -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    third_id = uuid.uuid4()
    task = CrawlTask(name="任务C", owner_id=admin_user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(id=first_id, position=0, url="https://javdb.com/actors/a", url_type="actors", final_url="https://javdb.com/actors/a", source="javdb"),
        CrawlTaskUrl(id=second_id, position=1, url="https://javdb.com/tags/b", url_type="tags", final_url="https://javdb.com/tags/b", source="javdb"),
        CrawlTaskUrl(id=third_id, position=2, url="https://javdb.com/series/c", url_type="series", final_url="https://javdb.com/series/c", source="javdb"),
    ]

    converted = to_scraper_task(task, selected_url_ids=[third_id, first_id])

    assert [url.url for url in converted.urls] == [
        "https://javdb.com/actors/a",
        "https://javdb.com/series/c",
    ]


def test_to_scraper_task_raises_when_subset_matches_no_urls(admin_user) -> None:
    task = CrawlTask(name="任务D", owner_id=admin_user.id, is_skip=False)
    task.urls = [
        CrawlTaskUrl(id=uuid.uuid4(), position=0, url="https://javdb.com/actors/a", url_type="actors", final_url="https://javdb.com/actors/a", source="javdb")
    ]

    try:
        to_scraper_task(task, selected_url_ids=[uuid.uuid4()])
    except ValueError as exc:
        assert str(exc) == "选择的 URL 不属于该任务"
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run adapter tests to verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_adapters.py::test_to_scraper_task_filters_selected_url_ids_and_preserves_task_order backend/tests/test_crawler_runtime_adapters.py::test_to_scraper_task_raises_when_subset_matches_no_urls -v
```

Expected: FAIL because `to_scraper_task` does not accept `selected_url_ids`.

- [ ] **Step 3: Update task adapter**

Replace `backend/app/modules/crawler/runtime/task_adapter.py` with:

```python
from __future__ import annotations

import uuid

from backend.app.models.crawl_task import CrawlTask as BackendCrawlTask
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def _normalize_selected_ids(selected_url_ids: list[uuid.UUID] | None) -> set[uuid.UUID] | None:
    if selected_url_ids is None:
        return None
    return {uuid.UUID(str(url_id)) for url_id in selected_url_ids}


def to_scraper_task(
    task: BackendCrawlTask,
    selected_url_ids: list[uuid.UUID] | None = None,
) -> CrawlTask:
    selected_ids = _normalize_selected_ids(selected_url_ids)
    sorted_urls = sorted(task.urls, key=lambda item: item.position)
    if selected_ids is not None:
        sorted_urls = [url for url in sorted_urls if url.id in selected_ids]
        if not sorted_urls:
            raise ValueError("选择的 URL 不属于该任务")

    urls = [
        CrawlTaskUrlEntry(
            url=url.url,
            url_type=url.url_type,
            has_magnet=bool(url.has_magnet),
            has_chinese_sub=bool(url.has_chinese_sub),
            sort_type=int(url.sort_type or 0),
            source=url.source,
            final_url=url.final_url,
            url_name=url.url_name,
        )
        for url in sorted_urls
    ]
    return CrawlTask(
        name=task.name,
        urls=urls,
        is_skip=bool(task.is_skip),
        filter=getattr(task, "filter", None),
    )
```

- [ ] **Step 4: Add run snapshot helper and executor wiring**

Modify `backend/app/modules/crawler/runtime/executor.py` imports:

```python
import uuid
```

Add helper above `execute_run`:

```python
def selected_task_url_ids_from_run(run: CrawlRun) -> list[uuid.UUID] | None:
    result = run.result or {}
    if not result.get("url_subset"):
        return None
    raw_ids = result.get("selected_task_url_ids") or []
    return [uuid.UUID(str(raw_id)) for raw_id in raw_ids]
```

Modify the `execute_threaded_crawl` call:

```python
        result = execute_threaded_crawl(
            db,
            run,
            task,
            runtime,
            detail_only=detail_only,
            selected_task_url_ids=selected_task_url_ids_from_run(run),
        )
```

Modify `backend/app/modules/crawler/runtime/threaded.py` function signature for `execute_threaded_crawl` to accept `selected_task_url_ids: list[uuid.UUID] | None = None`, import `uuid`, and pass it to `to_scraper_task(task, selected_url_ids=selected_task_url_ids)`.

The exact target block should become:

```python
scraper_task = to_scraper_task(task, selected_url_ids=selected_task_url_ids)
```

- [ ] **Step 5: Run adapter tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runtime_adapters.py -v
```

Expected: all adapter tests pass.

- [ ] **Step 6: Run backend URL subset tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_task_url_subset_run.py -v
```

Expected: all URL subset API tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/task_adapter.py backend/app/modules/crawler/runtime/executor.py backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_runtime_adapters.py
git commit -m "feat: filter crawler runs by selected task urls"
```

---

### Task 3: Frontend API, Hook, And Modal

**Files:**
- Modify: `frontend/src/api/crawlTask/types.ts`
- Modify: `frontend/src/api/crawlTask/index.ts`
- Create: `frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts`
- Create: `frontend/src/pages/crawler/tasks/components/TaskUrlRunModal.tsx`
- Create: `frontend/tests/task-url-run-modal.ui.test.tsx`

**Interfaces:**
- Consumes:
  - `TaskUrlEntry.id` from existing task list API.
- Produces:
  - `TaskUrlRunCreateParams`
  - `createTaskUrlRun(taskId: string, data: TaskUrlRunCreateParams): Promise<CrawlRun>`
  - `useTaskUrlRun({ onSubmitted }: { onSubmitted: () => void | Promise<void> })`
  - `TaskUrlRunModal`

- [ ] **Step 1: Write failing modal tests**

Create `frontend/tests/task-url-run-modal.ui.test.tsx`:

```tsx
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CrawlTask } from '../src/api/crawlTask/types'
import TaskUrlRunModal from '../src/pages/crawler/tasks/components/TaskUrlRunModal'

const task: CrawlTask = {
  id: 'task-1',
  _id: 'task-1',
  name: '任务A',
  storage_location: 'JP',
  urls: [
    {
      id: 'url-1',
      position: 0,
      url: 'https://javdb.com/actors/a',
      url_type: 'actors',
      has_magnet: true,
      has_chinese_sub: false,
      sort_type: 0,
      source: 'javdb',
      final_url: 'https://javdb.com/actors/a',
      url_name: '演员A',
    },
    {
      id: 'url-2',
      position: 1,
      url: 'https://javdb.com/tags/b',
      url_type: 'tags',
      has_magnet: false,
      has_chinese_sub: true,
      sort_type: 0,
      source: 'javdb',
      final_url: 'https://javdb.com/tags/b',
      url_name: null,
    },
  ],
  is_skip: false,
  status: 'pending',
  task_id: null,
  error_message: null,
  total_found: 0,
  total_qualified: 0,
  owner_id: 'owner-1',
  created_at: '2026-07-15T00:00:00Z',
  updated_at: null,
  last_run_at: null,
  last_run_status: null,
}

function renderModal(props?: Partial<React.ComponentProps<typeof TaskUrlRunModal>>) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const onCancel = vi.fn()
  render(
    <AntApp>
      <TaskUrlRunModal
        open
        task={task}
        submitting={false}
        onCancel={onCancel}
        onSubmit={onSubmit}
        {...props}
      />
    </AntApp>,
  )
  return { onSubmit, onCancel }
}

describe('TaskUrlRunModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('submits selected url ids with default incremental mode', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('选择 URL'))
    await userEvent.click(await screen.findByText('演员A'))
    await userEvent.click(screen.getByRole('button', { name: '开始爬取' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        url_ids: ['url-1'],
        crawl_mode: 'incremental',
      })
    })
  })

  it('submits full mode when selected', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByLabelText('选择 URL'))
    await userEvent.click(await screen.findByText('演员A'))
    await userEvent.click(screen.getByLabelText('爬取模式'))
    await userEvent.click(await screen.findByText('全量爬取'))
    await userEvent.click(screen.getByRole('button', { name: '开始爬取' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        url_ids: ['url-1'],
        crawl_mode: 'full',
      })
    })
  })

  it('blocks empty url selection', async () => {
    const { onSubmit } = renderModal()

    await userEvent.click(screen.getByRole('button', { name: '开始爬取' }))

    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled()
    })
    expect(await screen.findByText('请选择至少 1 条任务 URL')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run modal tests to verify failure**

Run:

```bash
cd frontend
npm test -- task-url-run-modal.ui.test.tsx --run
```

Expected: FAIL because `TaskUrlRunModal` does not exist.

- [ ] **Step 3: Add frontend API types and client**

Modify `frontend/src/api/crawlTask/types.ts`:

```ts
export interface TaskUrlRunCreateParams {
  url_ids: string[]
  crawl_mode: 'incremental' | 'full'
}

export type TaskUrlRunFormValues = TaskUrlRunCreateParams
```

Modify `frontend/src/api/crawlTask/index.ts` imports to include `TaskUrlRunCreateParams`, then add:

```ts
export function createTaskUrlRun(taskId: string, data: TaskUrlRunCreateParams): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${taskId}/url-run`, data)
}
```

- [ ] **Step 4: Add dedicated hook**

Create `frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts`:

```ts
import { useCallback, useState } from 'react'
import { App } from 'antd'
import { createTaskUrlRun } from '@/api/crawlTask'
import type { CrawlTask, TaskUrlRunFormValues } from '@/api/crawlTask/types'

interface UseTaskUrlRunOptions {
  onSubmitted: () => void | Promise<void>
}

export function useTaskUrlRun({ onSubmitted }: UseTaskUrlRunOptions) {
  const { message } = App.useApp()
  const [selectedTask, setSelectedTask] = useState<CrawlTask | null>(null)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const openTaskUrlRun = useCallback((task: CrawlTask) => {
    setSelectedTask(task)
    setOpen(true)
  }, [])

  const closeTaskUrlRun = useCallback(() => {
    if (submitting) return
    setOpen(false)
    setSelectedTask(null)
  }, [submitting])

  const submitTaskUrlRun = useCallback(async (values: TaskUrlRunFormValues) => {
    if (!selectedTask) return
    setSubmitting(true)
    try {
      await createTaskUrlRun(selectedTask.id, values)
      message.success('URL 爬取任务已提交')
      setOpen(false)
      setSelectedTask(null)
      await onSubmitted()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'URL 爬取任务提交失败')
    } finally {
      setSubmitting(false)
    }
  }, [message, onSubmitted, selectedTask])

  return {
    selectedTask,
    open,
    submitting,
    openTaskUrlRun,
    closeTaskUrlRun,
    submitTaskUrlRun,
  }
}
```

- [ ] **Step 5: Add modal component**

Create `frontend/src/pages/crawler/tasks/components/TaskUrlRunModal.tsx`:

```tsx
import { Form, Modal, Select, Space, Tag, Typography } from 'antd'
import type { CrawlTask, TaskUrlEntry, TaskUrlRunFormValues } from '@/api/crawlTask/types'

interface TaskUrlRunModalProps {
  open: boolean
  task: CrawlTask | null
  submitting: boolean
  onCancel: () => void
  onSubmit: (values: TaskUrlRunFormValues) => Promise<void>
}

function optionLabel(url: TaskUrlEntry) {
  const title = url.url_name?.trim() || url.url
  return (
    <Space direction="vertical" size={2}>
      <Typography.Text>{title}</Typography.Text>
      <Space size={4}>
        <Tag>{url.url_type}</Tag>
        {url.has_magnet ? <Tag color="blue">磁链</Tag> : null}
        {url.has_chinese_sub ? <Tag color="green">字幕</Tag> : null}
      </Space>
    </Space>
  )
}

export default function TaskUrlRunModal({
  open,
  task,
  submitting,
  onCancel,
  onSubmit,
}: TaskUrlRunModalProps) {
  const [form] = Form.useForm<TaskUrlRunFormValues>()
  const options = (task?.urls ?? [])
    .slice()
    .sort((left, right) => (left.position ?? 0) - (right.position ?? 0))
    .filter((url) => Boolean(url.id))
    .map((url) => ({
      value: String(url.id),
      label: optionLabel(url),
    }))

  const handleFinish = async (values: TaskUrlRunFormValues) => {
    await onSubmit(values)
    form.resetFields()
  }

  return (
    <Modal
      title={task ? `URL 爬取 - ${task.name}` : 'URL 爬取'}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText="开始爬取"
      cancelText="取消"
      confirmLoading={submitting}
      destroyOnHidden
      afterOpenChange={(nextOpen) => {
        if (!nextOpen) form.resetFields()
      }}
    >
      <Form<TaskUrlRunFormValues>
        form={form}
        layout="vertical"
        initialValues={{ crawl_mode: 'incremental', url_ids: [] }}
        onFinish={(values) => void handleFinish(values)}
      >
        <Form.Item
          name="url_ids"
          label="选择 URL"
          rules={[{ required: true, message: '请选择至少 1 条任务 URL' }]}
        >
          <Select
            aria-label="选择 URL"
            mode="multiple"
            options={options}
            placeholder="请选择任务 URL"
            disabled={submitting || options.length === 0}
            optionLabelProp="value"
          />
        </Form.Item>
        <Form.Item
          name="crawl_mode"
          label="爬取模式"
          rules={[{ required: true, message: '请选择爬取模式' }]}
        >
          <Select
            aria-label="爬取模式"
            disabled={submitting}
            options={[
              { value: 'incremental', label: '增量爬取' },
              { value: 'full', label: '全量爬取' },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
```

- [ ] **Step 6: Run modal tests**

Run:

```bash
cd frontend
npm test -- task-url-run-modal.ui.test.tsx --run
```

Expected: modal tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/crawlTask/index.ts frontend/src/api/crawlTask/types.ts frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts frontend/src/pages/crawler/tasks/components/TaskUrlRunModal.tsx frontend/tests/task-url-run-modal.ui.test.tsx
git commit -m "feat: add task url run modal hook"
```

---

### Task 4: Frontend Task List Integration

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/tests/crawler-run-controls.ui.test.tsx`

**Interfaces:**
- Consumes:
  - `useTaskUrlRun`
  - `TaskUrlRunModal`
- Produces:
  - Per-card `URL 爬取` action.

- [ ] **Step 1: Add failing integration test**

Modify `frontend/tests/crawler-run-controls.ui.test.tsx` imports:

```tsx
import { createTemporaryCrawlRun, createTaskUrlRun, getCrawlTaskStats, getCrawlTasks, getTaskDict } from '../src/api/crawlTask'
```

Modify the `vi.mock('../src/api/crawlTask', ...)` block to include:

```tsx
  createTaskUrlRun: vi.fn(),
```

Modify the default `getCrawlTasks` mock row so `urls` contains one selectable URL:

```tsx
        urls: [{
          id: 'url-1',
          position: 0,
          url: 'https://javdb.com/actors/a',
          url_type: 'actors',
          has_magnet: true,
          has_chinese_sub: false,
          sort_type: 0,
          source: 'javdb',
          final_url: 'https://javdb.com/actors/a',
          url_name: '演员A',
        }],
```

Add this mock in `beforeEach` after `createTemporaryCrawlRun`:

```tsx
    vi.mocked(createTaskUrlRun).mockResolvedValue({
      id: 'run-url-1',
      task_id: 'task-1',
      task_name: '任务A',
      status: 'queued',
      crawl_mode: 'incremental',
      queued_at: '2026-07-15T00:00:00',
      started_at: null,
      finished_at: null,
      result: { url_subset: true, selected_task_url_ids: ['url-1'], selected_task_url_count: 1 },
      error: null,
      resumed_from: null,
      created_at: '2026-07-15T00:00:00',
      updated_at: null,
      logs: [],
    })
```

Append this test:

```tsx
it('submits url subset run from a task card', async () => {
  const user = userEvent.setup()
  renderPage()

  const urlRunButton = await screen.findByRole('button', { name: 'URL 爬取' })
  await user.click(urlRunButton)

  expect(await screen.findByText(/URL 爬取 -/)).toBeInTheDocument()
  await user.click(screen.getByLabelText('选择 URL'))
  await user.click(await screen.findByText('演员A'))
  await user.click(screen.getByRole('button', { name: '开始爬取' }))

  await waitFor(() => {
    expect(createTaskUrlRun).toHaveBeenCalledWith('task-1', {
      url_ids: ['url-1'],
      crawl_mode: 'incremental',
    })
  })
})
```

- [ ] **Step 2: Run integration test to verify failure**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx --run
```

Expected: FAIL because task cards do not render `URL 爬取`.

- [ ] **Step 3: Add card action prop and button**

Modify `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx` prop type:

```ts
  onUrlRun: (task: CrawlTask) => void
```

Add `onUrlRun` to `TaskCard` props and destructuring.

Compute availability in `TaskCard`:

```ts
  const hasUrls = task.urls.length > 0
  const canUrlRun = canRun && hasUrls
```

Render the button next to the existing whole-task run dropdown:

```tsx
        <Button
          size="small"
          icon={<PlayCircleOutlined />}
          disabled={!canUrlRun}
          onClick={() => onUrlRun(task)}
        >
          URL 爬取
        </Button>
```

Pass `onUrlRun` through the `tasks.map` render:

```tsx
                onUrlRun={onUrlRun}
```

- [ ] **Step 4: Wire hook and modal in page**

Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx` imports:

```tsx
import TaskUrlRunModal from './components/TaskUrlRunModal'
import { useTaskUrlRun } from './hooks/useTaskUrlRun'
```

Add hook after temporary-task state:

```tsx
  const taskUrlRun = useTaskUrlRun({ onSubmitted: fetchRuntimeStatuses })
```

Pass the handler to `TaskListCards`:

```tsx
          onUrlRun={taskUrlRun.openTaskUrlRun}
```

Render the modal after `TemporaryTaskModal`:

```tsx
      <TaskUrlRunModal
        open={taskUrlRun.open}
        task={taskUrlRun.selectedTask}
        submitting={taskUrlRun.submitting}
        onCancel={taskUrlRun.closeTaskUrlRun}
        onSubmit={taskUrlRun.submitTaskUrlRun}
      />
```

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd frontend
npm test -- task-url-run-modal.ui.test.tsx crawler-run-controls.ui.test.tsx --run
```

Expected: selected frontend tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/tests/crawler-run-controls.ui.test.tsx
git commit -m "feat: wire task url run action"
```

---

### Task 5: Final Verification

**Files:**
- Modify only files required by verification failures.

**Interfaces:**
- Consumes:
  - Backend URL subset API and runtime filtering from Tasks 1-2.
  - Frontend API, hook, modal, and task card integration from Tasks 3-4.
- Produces:
  - Passing targeted backend tests, frontend tests, frontend build, and a clean intentional diff.

- [ ] **Step 1: Run backend URL subset tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_task_url_subset_run.py backend/tests/test_crawler_runtime_adapters.py -v
```

Expected: PASS.

- [ ] **Step 2: Run adjacent backend regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_runs_api.py backend/tests/test_crawler_threaded_runtime.py backend/tests/test_crawler_detail_queue.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend targeted tests**

Run:

```bash
cd frontend
npm test -- task-url-run-modal.ui.test.tsx crawler-run-controls.ui.test.tsx temporary-task-modal.ui.test.tsx --run
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Confirm existing temporary task copy remains**

Run:

```bash
rg -n "创建临时任务|临时任务已提交|TemporaryTaskModal" frontend/src/pages/crawler/tasks frontend/tests
```

Expected: matches still exist for the existing temporary detail-page workflow.

- [ ] **Step 6: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional files from this feature are modified. Existing unrelated files may still appear from earlier work; do not add or revert them unless the user explicitly asks.

- [ ] **Step 7: Commit verification fixes if any**

If verification required changes, commit only this feature's files:

```bash
git add backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runtime/task_adapter.py backend/app/modules/crawler/runtime/executor.py backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_task_url_subset_run.py backend/tests/test_crawler_runtime_adapters.py frontend/src/api/crawlTask/index.ts frontend/src/api/crawlTask/types.ts frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts frontend/src/pages/crawler/tasks/components/TaskUrlRunModal.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/tests/task-url-run-modal.ui.test.tsx frontend/tests/crawler-run-controls.ui.test.tsx
git commit -m "fix: verify crawler task url subset runs"
```

If no files changed after verification, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: the plan covers per-card `URL 爬取`, URL multi-select, incremental/full mode, backend URL ID validation, run snapshot storage, runtime filtering, restart determinism through `run.result`, the dedicated frontend hook, modal behavior, and preservation of the existing global `临时任务`.
- Scope: one backend API plus runtime task URL filtering and one frontend modal/hook integration; no new persistent task type or unrelated crawler workflow.
- Type consistency: backend request field `url_ids` matches frontend `TaskUrlRunCreateParams.url_ids`; backend `crawl_mode` literal matches frontend mode values; `selected_task_url_ids` is stored as strings in `run.result` and normalized to UUIDs in runtime execution.
