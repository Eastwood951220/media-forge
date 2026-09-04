# Crawler Batch Task Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add batch crawler task creation from pasted URLs and make newly submitted crawler runs show `排队中` immediately in the task list.

**Architecture:** Backend owns batch creation, URL name extraction, task-name conflict suffixing, and the longer `storage_location` schema. Frontend adds a focused batch-create drawer and optimistic runtime-store updates after run submission, while existing realtime events remain the source of truth.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, pytest, React 19, Vite, TypeScript, Ant Design, TanStack Query, Zustand, Vitest, React Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-04-crawler-batch-task-creation-design.md`

## Global Constraints

- Do not create or use a Git worktree in this repository.
- Stage intended source files explicitly instead of using `git add .` or `git add -A`.
- Keep crawler execution scheduling and queue semantics unchanged.
- Do not auto-start created batch tasks after saving.
- Save one independent crawler task per pasted URL.
- Use each fetched URL name as both the task name and storage location.
- Increase crawler task `storage_location` capacity from 10 characters to 200 characters.
- Preserve existing single-task create/edit behavior.

---

## File Structure

- Modify `backend/app/schemas/crawl_task.py`: add batch request/response schemas and widen `storage_location` validation.
- Modify `backend/app/models/crawl_task.py`: widen the ORM column type for `storage_location`.
- Create `backend/alembic/versions/20260904_0001_widen_crawl_task_storage_location.py`: database migration for `crawl_tasks.storage_location`.
- Create `backend/app/modules/crawler/tasks/url_detection.py`: backend URL type detection matching the existing frontend route patterns.
- Modify `backend/app/modules/crawler/tasks/service.py`: add `batch_create_tasks`, per-item transaction handling, name extraction, and conflict suffixing.
- Modify `backend/app/modules/crawler/tasks/router.py`: add `POST /api/crawler/tasks/batch` before UUID routes.
- Modify `backend/tests/test_crawler_tasks_api.py`: backend API coverage for batch creation, conflict suffixing, failures, duplicates, and long storage locations.
- Modify `frontend/src/api/crawler/crawlTask/types.ts`: add batch-create and run-action response types.
- Modify `frontend/src/api/crawler/crawlTask/index.ts`: add `batchCreateCrawlTasks` and type run-submission APIs precisely.
- Create `frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx`: left drawer for multiline URL input and default options.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`: own drawer state, submit batch requests, refresh task lists, and pass batch-open handler.
- Modify `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`: add the `批量新建` toolbar button.
- Modify `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`: optimistic queued runtime update after normal task run.
- Modify `frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts`: optimistic queued runtime update after URL subset run.
- Modify `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`: assert toolbar opens the batch drawer and normal run shows queued immediately.
- Create or modify `frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx`: drawer input, submit, success, and partial-failure tests.

---

### Task 1: Backend Batch Create Contract And Storage Length

**Files:**
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/models/crawl_task.py`
- Create: `backend/alembic/versions/20260904_0001_widen_crawl_task_storage_location.py`
- Test: `backend/tests/test_crawler_tasks_api.py`

**Interfaces:**
- Produces: `CrawlTaskBatchCreate`, `CrawlTaskBatchCreateResult`, `CrawlTaskBatchCreatedItem`, `CrawlTaskBatchFailedItem` Pydantic schemas.
- Produces: `CrawlTask.storage_location` accepts up to 200 characters at API and database model level.
- Consumes: existing `CrawlTaskRead` serializer output for created task payloads.

- [ ] **Step 1: Write failing backend tests for long storage location and batch route schema**

Add these tests to `backend/tests/test_crawler_tasks_api.py`:

```python
def test_create_task_accepts_long_storage_location(client, auth_headers):
    long_name = "演员名称超过十个字符"
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": long_name,
            "storage_location": long_name,
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/long-name", "url_type": "actors"}],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["data"]["storage_location"] == long_name


def test_batch_create_route_rejects_empty_url_list(client, auth_headers):
    response = client.post(
        "/api/crawler/tasks/batch",
        json={"urls": ["", "   "]},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["msg"] == "请至少提供 1 个 URL"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_create_task_accepts_long_storage_location tests/test_crawler_tasks_api.py::test_batch_create_route_rejects_empty_url_list -v
```

Expected: the first test fails on existing 10-character validation or storage length, and the second fails because `/api/crawler/tasks/batch` does not exist.

- [ ] **Step 3: Add schemas and widen model/schema length**

In `backend/app/schemas/crawl_task.py`, change:

```python
storage_location: str = Field(..., min_length=1, max_length=10)
```

to:

```python
storage_location: str = Field(..., min_length=1, max_length=200)
```

Add this request schema after `CrawlTaskCreate`:

```python
class CrawlTaskBatchCreate(BaseModel):
    urls: list[str] = Field(..., min_length=1)
    has_magnet: bool = True
    has_chinese_sub: bool = False
    sort_type: int = Field(default=0, ge=0)
    is_skip: bool = False
```

Add these response schemas after `CrawlTaskRead`, because
`CrawlTaskBatchCreatedItem.task` references `CrawlTaskRead`:

```python

class CrawlTaskBatchCreatedItem(BaseModel):
    url: str
    task: CrawlTaskRead


class CrawlTaskBatchFailedItem(BaseModel):
    url: str
    reason: str


class CrawlTaskBatchCreateResult(BaseModel):
    created: list[CrawlTaskBatchCreatedItem]
    failed: list[CrawlTaskBatchFailedItem]
    created_count: int
    failed_count: int
```

In `backend/app/models/crawl_task.py`, change:

```python
storage_location: Mapped[str] = mapped_column(String(10), nullable=False, default="")
```

to:

```python
storage_location: Mapped[str] = mapped_column(String(200), nullable=False, default="")
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/alembic/versions/20260904_0001_widen_crawl_task_storage_location.py`:

```python
"""widen crawl task storage location

Revision ID: 20260904_0001
Revises: 20260817_0001
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0001"
down_revision = "20260817_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "crawl_tasks",
        "storage_location",
        existing_type=sa.String(length=10),
        type_=sa.String(length=200),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "crawl_tasks",
        "storage_location",
        existing_type=sa.String(length=200),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_create_task_accepts_long_storage_location -v
```

Expected: PASS for the long storage-location test. The empty batch route test may still fail until Task 2 adds the route.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/app/schemas/crawl_task.py backend/app/models/crawl_task.py backend/alembic/versions/20260904_0001_widen_crawl_task_storage_location.py backend/tests/test_crawler_tasks_api.py
git diff --cached --name-only
git commit -m "feat: widen crawler task storage location"
```

---

### Task 2: Backend Batch Create Service And API

**Files:**
- Create: `backend/app/modules/crawler/tasks/url_detection.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Test: `backend/tests/test_crawler_tasks_api.py`

**Interfaces:**
- Consumes: `CrawlTaskBatchCreate` from Task 1.
- Produces: `detect_task_url_type(url: str, source: str | None = None) -> str | None`.
- Produces: `CrawlerTaskService.batch_create_tasks(data: CrawlTaskBatchCreate, owner_id: uuid.UUID) -> dict`.
- Produces: `POST /api/crawler/tasks/batch`.

- [ ] **Step 1: Write failing API tests for successful, partial, and suffixed batch creation**

Add these tests to `backend/tests/test_crawler_tasks_api.py`:

```python
def test_batch_create_creates_one_task_per_url(client, auth_headers, monkeypatch):
    from backend.app.modules.crawler.tasks import service as task_service

    names = {
        "https://javdb.com/actors/alpha": "Alpha Actor",
        "https://javdb.com/series/beta": "Beta Series",
    }
    monkeypatch.setattr(
        task_service,
        "extract_task_name",
        lambda body: names[body.url],
    )

    response = client.post(
        "/api/crawler/tasks/batch",
        json={
            "urls": [" https://javdb.com/actors/alpha ", "https://javdb.com/series/beta"],
            "has_magnet": True,
            "has_chinese_sub": True,
            "sort_type": 5,
            "is_skip": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["created_count"] == 2
    assert data["failed_count"] == 0
    assert [item["task"]["name"] for item in data["created"]] == ["Alpha Actor", "Beta Series"]
    assert data["created"][0]["task"]["storage_location"] == "Alpha Actor"
    assert data["created"][0]["task"]["urls"][0]["url"] == "https://javdb.com/actors/alpha"
    assert data["created"][0]["task"]["urls"][0]["url_type"] == "actors"
    assert data["created"][0]["task"]["urls"][0]["has_magnet"] is True
    assert data["created"][0]["task"]["urls"][0]["has_chinese_sub"] is True
    assert data["created"][0]["task"]["urls"][0]["sort_type"] == 5
    assert data["created"][0]["task"]["urls"][0]["url_name"] == "Alpha Actor"


def test_batch_create_suffixes_duplicate_task_names(client, auth_headers, monkeypatch):
    from backend.app.modules.crawler.tasks import service as task_service

    monkeypatch.setattr(task_service, "extract_task_name", lambda body: "Same Name")

    existing = client.post(
        "/api/crawler/tasks",
        json={
            "name": "Same Name",
            "storage_location": "Same Name",
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/existing", "url_type": "actors"}],
        },
        headers=auth_headers,
    )
    assert existing.status_code == 201

    response = client.post(
        "/api/crawler/tasks/batch",
        json={"urls": ["https://javdb.com/actors/a", "https://javdb.com/actors/b"]},
        headers=auth_headers,
    )

    assert response.status_code == 201
    created = response.json()["data"]["created"]
    assert [item["task"]["name"] for item in created] == ["Same Name (2)", "Same Name (3)"]
    assert [item["task"]["storage_location"] for item in created] == ["Same Name (2)", "Same Name (3)"]


def test_batch_create_keeps_successes_when_some_urls_fail(client, auth_headers, monkeypatch):
    from fastapi import HTTPException
    from backend.app.modules.crawler.tasks import service as task_service

    def fake_extract(body):
        if body.url.endswith("/bad"):
            raise HTTPException(status_code=502, detail="页面不可访问")
        return "Good Name"

    monkeypatch.setattr(task_service, "extract_task_name", fake_extract)

    response = client.post(
        "/api/crawler/tasks/batch",
        json={
            "urls": [
                "https://javdb.com/actors/good",
                "https://javdb.com/actors/good",
                "https://example.com/nope",
                "https://javdb.com/actors/bad",
            ]
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["created_count"] == 1
    assert data["failed_count"] == 3
    assert data["created"][0]["task"]["name"] == "Good Name"
    assert data["failed"] == [
        {"url": "https://javdb.com/actors/good", "reason": "URL 重复"},
        {"url": "https://example.com/nope", "reason": "不支持的 URL 来源"},
        {"url": "https://javdb.com/actors/bad", "reason": "页面不可访问"},
    ]
```

- [ ] **Step 2: Run failing batch tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_batch_create_route_rejects_empty_url_list tests/test_crawler_tasks_api.py::test_batch_create_creates_one_task_per_url tests/test_crawler_tasks_api.py::test_batch_create_suffixes_duplicate_task_names tests/test_crawler_tasks_api.py::test_batch_create_keeps_successes_when_some_urls_fail -v
```

Expected: FAIL because the batch route and service do not exist.

- [ ] **Step 3: Add backend URL type detection helper**

Create `backend/app/modules/crawler/tasks/url_detection.py`:

```python
from __future__ import annotations

from urllib.parse import urlparse


def detect_task_url_type(url: str, source: str | None = None) -> str | None:
    parsed = urlparse(url.strip())
    path = parsed.path or ""

    if path.startswith("/search"):
        return "search"
    if path.startswith("/actors/"):
        return "actors"
    if path.startswith("/series/"):
        return "series"
    if path.startswith("/makers/"):
        return "makers"
    if path.startswith("/directors/"):
        return "directors"
    if path.startswith("/video_codes/"):
        return "video_codes"
    if path.startswith("/lists/"):
        return "lists"
    if path == "/tags" or path.startswith("/tags/"):
        return "tags"
    if source == "javbus":
        return "detail"
    return None
```

- [ ] **Step 4: Add batch service implementation**

In `backend/app/modules/crawler/tasks/service.py`, add imports:

```python
from fastapi import HTTPException, status

from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
from backend.app.modules.crawler.tasks.url_detection import detect_task_url_type
from backend.app.schemas.crawl_task import (
    CrawlTaskBatchCreate,
    CrawlTaskBatchCreateResult,
    CrawlTaskBatchCreatedItem,
    CrawlTaskBatchFailedItem,
    CrawlTaskCreate,
    CrawlTaskListResponse,
    CrawlTaskUpdate,
    CrawlTaskUrlRunCreate,
    ExtractNameRequest,
    TaskUrlEntryCreate,
    TemporaryCrawlRunCreate,
)
from scraper.tasks.task_utils import determine_source
```

Add helper methods inside `CrawlerTaskService`:

```python
    def _unique_task_name(self, owner_id: uuid.UUID, base_name: str, reserved: set[str]) -> str:
        candidate = base_name
        suffix = 2
        while candidate in reserved or self.repo.get_by_name(owner_id, candidate):
            candidate = f"{base_name} ({suffix})"
            suffix += 1
        reserved.add(candidate)
        return candidate

    def batch_create_tasks(self, data: CrawlTaskBatchCreate, owner_id: uuid.UUID) -> dict:
        normalized_urls = [url.strip() for url in data.urls if url.strip()]
        if not normalized_urls:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少提供 1 个 URL")

        created: list[CrawlTaskBatchCreatedItem] = []
        failed: list[CrawlTaskBatchFailedItem] = []
        seen_urls: set[str] = set()
        reserved_names: set[str] = set()

        for url in normalized_urls:
            if url in seen_urls:
                failed.append(CrawlTaskBatchFailedItem(url=url, reason="URL 重复"))
                continue
            seen_urls.add(url)

            source = determine_source(url)
            if source == "unknown":
                failed.append(CrawlTaskBatchFailedItem(url=url, reason="不支持的 URL 来源"))
                continue

            url_type = detect_task_url_type(url, source)
            if not url_type:
                failed.append(CrawlTaskBatchFailedItem(url=url, reason="无法识别 URL 类型"))
                continue

            try:
                extracted_name = extract_task_name(ExtractNameRequest(url=url, url_type=url_type)).strip()
                if not extracted_name:
                    raise ValueError("未解析到 URL 名称")
                task_name = self._unique_task_name(owner_id, extracted_name, reserved_names)
                task_url = TaskUrlEntryCreate(
                    url=url,
                    url_type=url_type,
                    has_magnet=data.has_magnet,
                    has_chinese_sub=data.has_chinese_sub,
                    sort_type=data.sort_type,
                    url_name=extracted_name,
                )
                task = self.repo.create_with_urls(
                    owner_id=owner_id,
                    name=task_name,
                    storage_location=task_name,
                    is_skip=data.is_skip,
                    urls=[task_url],
                )
                created.append(CrawlTaskBatchCreatedItem(url=url, task=serialize_task(task)))
            except HTTPException as exc:
                self.db.rollback()
                failed.append(CrawlTaskBatchFailedItem(url=url, reason=str(exc.detail)))
            except Exception as exc:
                self.db.rollback()
                failed.append(CrawlTaskBatchFailedItem(url=url, reason=str(exc)))

        return CrawlTaskBatchCreateResult(
            created=created,
            failed=failed,
            created_count=len(created),
            failed_count=len(failed),
        ).model_dump(mode="json")
```

- [ ] **Step 5: Add batch route before UUID route declarations**

In `backend/app/modules/crawler/tasks/router.py`, import `CrawlTaskBatchCreate` and add this route before `@router.get("/{task_id:uuid}")`:

```python
@router.post("/batch", status_code=status.HTTP_201_CREATED)
def batch_create_tasks(
    data: CrawlTaskBatchCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.batch_create_tasks(data, current_user.id))
```

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_batch_create_route_rejects_empty_url_list tests/test_crawler_tasks_api.py::test_batch_create_creates_one_task_per_url tests/test_crawler_tasks_api.py::test_batch_create_suffixes_duplicate_task_names tests/test_crawler_tasks_api.py::test_batch_create_keeps_successes_when_some_urls_fail -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/app/modules/crawler/tasks/url_detection.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_tasks_api.py
git diff --cached --name-only
git commit -m "feat: add crawler batch task creation api"
```

---

### Task 3: Frontend Batch Create API And Drawer

**Files:**
- Modify: `frontend/src/api/crawler/crawlTask/types.ts`
- Modify: `frontend/src/api/crawler/crawlTask/index.ts`
- Create: `frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx`
- Create or modify: `frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx`

**Interfaces:**
- Produces: `BatchCrawlTaskCreateParams`, `BatchCrawlTaskCreateResult`, `BatchCrawlTaskCreatedItem`, `BatchCrawlTaskFailedItem`.
- Produces: `batchCreateCrawlTasks(data: BatchCrawlTaskCreateParams): Promise<BatchCrawlTaskCreateResult>`.
- Produces: `BatchTaskCreateDrawer` props:

```ts
type BatchTaskCreateDrawerProps = {
  open: boolean
  submitting: boolean
  failedUrls: string[]
  onCancel: () => void
  onSubmit: (values: BatchTaskCreateFormValues) => void | Promise<void>
}
```

- [ ] **Step 1: Write failing drawer tests**

Create `frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx`:

```tsx
import { App } from 'antd'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'
import BatchTaskCreateDrawer from '../components/BatchTaskCreateDrawer'

function wrapper({ children }: PropsWithChildren) {
  return <App>{children}</App>
}

describe('BatchTaskCreateDrawer', () => {
  const onSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('blocks empty input before submit', async () => {
    render(
      <BatchTaskCreateDrawer
        open
        submitting={false}
        failedUrls={[]}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
      { wrapper },
    )

    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('请至少输入 1 个 URL')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('normalizes multiline URLs and sends default options', async () => {
    render(
      <BatchTaskCreateDrawer
        open
        submitting={false}
        failedUrls={[]}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
      { wrapper },
    )

    await userEvent.type(
      screen.getByLabelText('URL 列表'),
      ' https://javdb.com/actors/a {enter}{enter}https://javdb.com/series/b ',
    )
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        urls: ['https://javdb.com/actors/a', 'https://javdb.com/series/b'],
        has_magnet: true,
        has_chinese_sub: false,
        sort_type: 0,
        is_skip: false,
      })
    })
  })

  it('loads failed urls when partial failure result is retried', async () => {
    const { rerender } = render(
      <BatchTaskCreateDrawer
        open
        submitting={false}
        failedUrls={[]}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
      { wrapper },
    )

    rerender(
      <App>
        <BatchTaskCreateDrawer
          open
          submitting={false}
          failedUrls={['https://javdb.com/actors/bad']}
          onCancel={vi.fn()}
          onSubmit={onSubmit}
        />
      </App>,
    )

    expect(within(screen.getByRole('dialog')).getByLabelText('URL 列表')).toHaveValue('https://javdb.com/actors/bad')
  })
})
```

- [ ] **Step 2: Run drawer tests and verify they fail**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx
```

Expected: FAIL because `BatchTaskCreateDrawer` and batch API types do not exist.

- [ ] **Step 3: Add frontend API types**

In `frontend/src/api/crawler/crawlTask/types.ts`, add:

```ts
export interface BatchCrawlTaskCreateParams {
  urls: string[]
  has_magnet?: boolean
  has_chinese_sub?: boolean
  sort_type?: number
  is_skip?: boolean
}

export interface BatchCrawlTaskCreatedItem {
  url: string
  task: CrawlTask
}

export interface BatchCrawlTaskFailedItem {
  url: string
  reason: string
}

export interface BatchCrawlTaskCreateResult {
  created: BatchCrawlTaskCreatedItem[]
  failed: BatchCrawlTaskFailedItem[]
  created_count: number
  failed_count: number
}
```

- [ ] **Step 4: Add frontend batch API function**

In `frontend/src/api/crawler/crawlTask/index.ts`, import the new types and add:

```ts
export function batchCreateCrawlTasks(
  data: BatchCrawlTaskCreateParams,
): Promise<BatchCrawlTaskCreateResult> {
  return request.post<BatchCrawlTaskCreateResult>(`${BASE_URL}/batch`, data)
}
```

- [ ] **Step 5: Implement the drawer component**

Create `frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx`:

```tsx
import { useEffect } from 'react'
import { Button, Drawer, Form, Input, Select, Space, Switch } from 'antd'
import { SORT_OPTIONS } from '../taskUrlUtils'
import styles from '../TaskPages.module.less'

export interface BatchTaskCreateFormValues {
  urls: string[]
  has_magnet: boolean
  has_chinese_sub: boolean
  sort_type: number
  is_skip: boolean
}

interface BatchTaskCreateDrawerProps {
  open: boolean
  submitting: boolean
  failedUrls: string[]
  onCancel: () => void
  onSubmit: (values: BatchTaskCreateFormValues) => void | Promise<void>
}

function parseUrlLines(value: string | undefined): string[] {
  return (value ?? '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export default function BatchTaskCreateDrawer({
  open,
  submitting,
  failedUrls,
  onCancel,
  onSubmit,
}: BatchTaskCreateDrawerProps) {
  const [form] = Form.useForm<{
    urlText: string
    has_magnet: boolean
    has_chinese_sub: boolean
    sort_type: number
    is_skip: boolean
  }>()

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      urlText: failedUrls.length > 0 ? failedUrls.join('\n') : form.getFieldValue('urlText') ?? '',
      has_magnet: form.getFieldValue('has_magnet') ?? true,
      has_chinese_sub: form.getFieldValue('has_chinese_sub') ?? false,
      sort_type: form.getFieldValue('sort_type') ?? 0,
      is_skip: form.getFieldValue('is_skip') ?? false,
    })
  }, [failedUrls, form, open])

  const handleSave = async () => {
    const values = await form.validateFields()
    const urls = parseUrlLines(values.urlText)
    if (urls.length === 0) {
      form.setFields([{ name: 'urlText', errors: ['请至少输入 1 个 URL'] }])
      return
    }
    await onSubmit({
      urls,
      has_magnet: values.has_magnet ?? true,
      has_chinese_sub: values.has_chinese_sub ?? false,
      sort_type: values.sort_type ?? 0,
      is_skip: values.is_skip ?? false,
    })
  }

  return (
    <Drawer
      title="批量新建任务"
      placement="left"
      open={open}
      onClose={onCancel}
      width={560}
      className={styles.batchTaskDrawer}
      footer={
        <div className={styles.urlEntryDrawerFooter}>
          <Button onClick={onCancel} disabled={submitting}>取消</Button>
          <Button type="primary" onClick={() => void handleSave()} loading={submitting}>保存</Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        disabled={submitting}
        initialValues={{
          urlText: '',
          has_magnet: true,
          has_chinese_sub: false,
          sort_type: 0,
          is_skip: false,
        }}
      >
        <Form.Item name="urlText" label="URL 列表" required>
          <Input.TextArea rows={12} placeholder="每行一个 URL" />
        </Form.Item>
        <Space size={16} wrap>
          <Form.Item name="has_magnet" label="磁力" valuePropName="checked">
            <Switch checkedChildren="有" unCheckedChildren="不限" />
          </Form.Item>
          <Form.Item name="has_chinese_sub" label="中文字幕" valuePropName="checked">
            <Switch checkedChildren="有" unCheckedChildren="不限" />
          </Form.Item>
          <Form.Item name="is_skip" label="创建后禁用" valuePropName="checked">
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
        </Space>
        <Form.Item name="sort_type" label="排序方式">
          <Select options={SORT_OPTIONS} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
```

- [ ] **Step 6: Run drawer tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add frontend/src/api/crawler/crawlTask/types.ts frontend/src/api/crawler/crawlTask/index.ts frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx
git diff --cached --name-only
git commit -m "feat: add crawler batch task drawer"
```

---

### Task 4: Wire Batch Create Into Task List

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`

**Interfaces:**
- Consumes: `BatchTaskCreateDrawer` and `batchCreateCrawlTasks` from Task 3.
- Produces: `TaskListCardsProps.onBatchTaskClick: () => void`.

- [ ] **Step 1: Write failing integration test for the toolbar button**

In `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`, add `onBatchTaskClick={vi.fn()}` to existing `TaskListCards` renders, then add:

```tsx
it('calls batch create handler from the toolbar', () => {
  const onBatchTaskClick = vi.fn()
  render(
    <TaskListCards
      tasks={[baseTask as never]}
      loading={false}
      total={1}
      runtimeByTaskId={{ 'task-1': { task_id: 'task-1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2026-09-04T00:00:00Z', last_run_at: null } } as never}
      runtimeReady={true}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleSkip={vi.fn()}
      onRun={vi.fn()}
      onStop={vi.fn()}
      onRestart={vi.fn()}
      onUrlRun={vi.fn()}
      onTemporaryTaskClick={vi.fn()}
      onBatchTaskClick={onBatchTaskClick}
      current={1}
      pageSize={20}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />,
  )

  fireEvent.click(screen.getByRole('button', { name: /批量新建/ }))

  expect(onBatchTaskClick).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: FAIL because `onBatchTaskClick` and the button do not exist.

- [ ] **Step 3: Add toolbar prop and button**

In `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`, add `onBatchTaskClick` to `TaskListCardsProps` and function arguments. Add the button near `新建任务`:

```tsx
<Button onClick={onBatchTaskClick}>
  批量新建
</Button>
```

- [ ] **Step 4: Wire drawer state and submit handling in `TaskListPage`**

In `frontend/src/pages/crawler/tasks/TaskListPage.tsx`, import:

```ts
import { batchCreateCrawlTasks } from '@/api/crawler/crawlTask'
import { invalidateCrawlerTaskLists } from '@/api/queryInvalidation'
import { useQueryClient } from '@tanstack/react-query'
import BatchTaskCreateDrawer from './components/BatchTaskCreateDrawer'
import type { BatchTaskCreateFormValues } from './components/BatchTaskCreateDrawer'
```

Add state:

```ts
const queryClient = useQueryClient()
const [batchDrawerOpen, setBatchDrawerOpen] = useState(false)
const [batchSubmitting, setBatchSubmitting] = useState(false)
const [batchFailedUrls, setBatchFailedUrls] = useState<string[]>([])
```

Add submit handler:

```ts
const handleBatchSubmit = useCallback(async (values: BatchTaskCreateFormValues) => {
  setBatchSubmitting(true)
  try {
    const result = await batchCreateCrawlTasks(values)
    await invalidateCrawlerTaskLists(queryClient)
    if (result.failed_count > 0) {
      setBatchFailedUrls(result.failed.map((item) => item.url))
      await message.warning(`已创建 ${result.created_count} 个任务，${result.failed_count} 个失败`)
      return
    }
    setBatchFailedUrls([])
    setBatchDrawerOpen(false)
    await message.success(`已创建 ${result.created_count} 个任务`)
  } catch (error) {
    await message.error(error instanceof Error ? error.message : '批量新建任务失败')
  } finally {
    setBatchSubmitting(false)
  }
}, [message, queryClient])
```

Pass `onBatchTaskClick={() => setBatchDrawerOpen(true)}` to `TaskListCards`, and render:

```tsx
<BatchTaskCreateDrawer
  open={batchDrawerOpen}
  submitting={batchSubmitting}
  failedUrls={batchFailedUrls}
  onCancel={() => {
    if (batchSubmitting) return
    setBatchDrawerOpen(false)
    setBatchFailedUrls([])
  }}
  onSubmit={handleBatchSubmit}
/>
```

- [ ] **Step 5: Run focused frontend tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
git diff --cached --name-only
git commit -m "feat: wire crawler batch task creation"
```

---

### Task 5: Optimistic Queued Runtime Updates

**Files:**
- Modify: `frontend/src/api/crawler/crawlTask/types.ts`
- Modify: `frontend/src/api/crawler/crawlTask/index.ts`
- Modify: `frontend/src/api/crawler/crawlerRun/index.ts`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`

**Interfaces:**
- Produces: `RunActionAcceptedResponse`:

```ts
export interface RunActionAcceptedResponse {
  accepted: boolean
  run_id: string
}
```

- Produces: task-list run handlers call `useCrawlerRuntimeStore.getState().upsertTaskRuntime`.

- [ ] **Step 1: Use the existing accepted run action payload**

`backend/app/modules/crawler/runs/schemas.py` already returns this shape from
`accepted_run_action(run.id)`:

```ts
{
  run_id: string
  accepted: true
}
```

Use `run_id` as the optimistic snapshot's `latest_run_id`.

- [ ] **Step 2: Write failing test for optimistic queued update**

In `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`, add a focused hook/page-level test if the existing component-only harness cannot reach `useTaskListData`. The expected assertion is:

```tsx
expect(useCrawlerRuntimeStore.getState().taskRuntimeById['task-1']).toEqual(expect.objectContaining({
  task_id: 'task-1',
  runtime_status: 'queued',
  latest_run_id: 'run-1',
}))
```

Mock `runCrawlTask` to resolve `{ accepted: true, run_id: 'run-1' }`, click the normal `爬取` action, and wait for the store update.

- [ ] **Step 3: Type run action responses**

In `frontend/src/api/crawler/crawlTask/types.ts`, add:

```ts
export interface RunActionAcceptedResponse {
  accepted: boolean
  run_id: string
}
```

In `frontend/src/api/crawler/crawlerRun/index.ts`, make `runCrawlTask` return `Promise<RunActionAcceptedResponse>` instead of a broad or inferred type.

In `frontend/src/api/crawler/crawlTask/index.ts`, make `createTaskUrlRun` return `Promise<RunActionAcceptedResponse>`.

- [ ] **Step 4: Add local helper for queued snapshots**

In `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`, add:

```ts
function queuedSnapshot(taskId: string, runId: string | null) {
  const now = new Date().toISOString()
  return {
    task_id: taskId,
    runtime_status: 'queued' as const,
    latest_run_id: runId,
    state_updated_at: now,
    last_run_at: now,
  }
}
```

Inside `handleRun`, change:

```ts
await runCrawlTask(task.id, mode)
```

to:

```ts
const result = await runCrawlTask(task.id, mode)
useCrawlerRuntimeStore.getState().upsertTaskRuntime(queuedSnapshot(task.id, result.run_id ?? null))
```

- [ ] **Step 5: Apply the same optimistic update to URL subset runs**

In `frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts`, after `createTaskUrlRun` resolves:

```ts
const result = await createTaskUrlRun(selectedTask.id, values)
useCrawlerRuntimeStore.getState().upsertTaskRuntime({
  task_id: selectedTask.id,
  runtime_status: 'queued',
  latest_run_id: result.run_id ?? null,
  state_updated_at: new Date().toISOString(),
  last_run_at: new Date().toISOString(),
})
```

Keep `await onSubmitted()` so run-list invalidation still happens.

- [ ] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add frontend/src/api/crawler/crawlTask/types.ts frontend/src/api/crawler/crawlTask/index.ts frontend/src/api/crawler/crawlerRun/index.ts frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx frontend/src/pages/crawler/tasks/hooks/useTaskUrlRun.ts frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
git diff --cached --name-only
git commit -m "fix: show queued crawler tasks immediately"
```

---

### Task 6: Final Verification And Cleanup

**Files:**
- Modify only files needed for compile/test fixes discovered by verification.
- Do not edit generated build output.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: verified backend and frontend behavior.

- [ ] **Step 1: Run backend focused crawler tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py tests/test_crawl_tasks_api.py tests/test_crawler_task_url_subset_run.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused task tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && pnpm build
```

Expected: PASS.

- [ ] **Step 4: Inspect Git state and staged content**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intentional source, test, migration, spec, or plan files are present.

- [ ] **Step 5: Commit any verification fixes**

If Step 1, 2, or 3 required small fixes, commit only those files:

```bash
git add <exact files changed by verification fixes>
git diff --cached --name-only
git commit -m "test: stabilize crawler batch task creation"
```

If no files changed during final verification, skip this commit.
