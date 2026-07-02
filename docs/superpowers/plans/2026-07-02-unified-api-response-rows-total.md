# Unified API Response Rows Total Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make backend crawler task APIs return the frontend `ApiResponse<T>` envelope and update frontend list code to read `rows` and `total`.

**Architecture:** Add reusable backend response schemas/helpers for `{ code, msg, data }` and paginated `{ code, msg, rows, total }`, then apply them to `/api/crawler/tasks` and legacy `/api/crawl-tasks`. Update the frontend request transform so object endpoints unwrap `data` for existing callers, while list endpoints preserve a typed `{ rows, total }` result for pages that need pagination.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, Pytest, React 19, TypeScript 6, Axios, Vitest, React Testing Library.

---

## Current Context

Frontend contract already exists in `frontend/src/request/types.ts`:

```ts
export interface ApiResponse<T = unknown> {
  code?: number | string
  msg?: string
  data?: T
  rows?: T
  total?: number
  [key: string]: unknown
}
```

Current mismatch:

- `frontend/src/request/transform.ts` treats any response without `code` as success and returns the raw response body.
- `backend/app/modules/crawler/tasks/router.py` currently returns raw `list[CrawlTaskRead]` from `GET /api/crawler/tasks`.
- `frontend/src/api/crawlTask/index.ts` types `getCrawlTasks()` as `Promise<CrawlTask[]>`.
- `frontend/src/pages/crawler/tasks/TaskListPage.tsx` estimates total from list length instead of using backend `total`.

Target behavior:

- Object endpoints return `{ code: 200, msg: "success", data: <object> }`.
- List endpoints return `{ code: 200, msg: "success", rows: <array>, total: <number> }`.
- Frontend object API clients continue receiving unwrapped domain objects because `transformResponse()` returns `data` when `data` exists.
- Frontend list API clients receive `{ rows, total }` and pages use those fields directly.

## File Structure

- Create `backend/app/schemas/response.py` for unified response models and helper functions.
- Modify `backend/app/modules/crawler/tasks/router.py` to return `PageResponse[CrawlTaskRead]` and `ApiResponse[CrawlTaskRead]`.
- Modify `backend/app/modules/crawl_tasks/router.py` compatibility response models to match canonical response envelopes.
- Modify `backend/tests/test_crawl_tasks_api.py` to assert `rows` and `total`.
- Modify `frontend/src/request/types.ts` to add `PageResponse<T>` / `ListResponse<T>` aliases.
- Modify `frontend/src/request/transform.ts` to unwrap `data` and preserve `rows`/`total`.
- Modify `frontend/src/api/crawlTask/index.ts` so `getCrawlTasks()` returns `PageResponse<CrawlTask>`.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx` to read `rows` and `total`.
- Modify `frontend/tests/crawler-task-pages.ui.test.tsx` or `frontend/tests/App.test.tsx` mocks to return `{ rows, total }`.
- Add `frontend/tests/request-transform.test.ts` for envelope behavior.

---

### Task 1: Frontend Request Transform Supports Unified Envelopes

**Files:**
- Modify: `frontend/src/request/types.ts`
- Modify: `frontend/src/request/transform.ts`
- Test: `frontend/tests/request-transform.test.ts`

- [ ] **Step 1: Write request transform tests**

Create `frontend/tests/request-transform.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { AxiosResponse } from 'axios'
import { transformResponse } from '../src/request/transform'
import type { ApiResponse } from '../src/request/types'

function response(data: ApiResponse): AxiosResponse<ApiResponse> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
    request: { responseType: 'json' },
  } as AxiosResponse<ApiResponse>
}

describe('transformResponse unified envelope handling', () => {
  it('unwraps data responses for object endpoints', () => {
    const result = transformResponse(response({
      code: 200,
      msg: 'success',
      data: { access_token: 'token-1', token_type: 'bearer' },
    }))

    expect(result).toEqual({ access_token: 'token-1', token_type: 'bearer' })
  })

  it('preserves rows and total for list endpoints', () => {
    const result = transformResponse(response({
      code: 200,
      msg: 'success',
      rows: [{ id: 'task-1', name: 'Task 1' }],
      total: 1,
    }))

    expect(result).toEqual({
      code: 200,
      msg: 'success',
      rows: [{ id: 'task-1', name: 'Task 1' }],
      total: 1,
    })
  })

  it('keeps raw success bodies for endpoints not migrated yet', () => {
    const result = transformResponse(response({
      initialized: true,
      databaseConfigured: true,
      redisConfigured: true,
    }))

    expect(result).toEqual({
      initialized: true,
      databaseConfigured: true,
      redisConfigured: true,
    })
  })
})
```

- [ ] **Step 2: Run request transform tests to verify they fail**

Run:

```bash
cd frontend && npm test -- request-transform.test.ts
```

Expected: FAIL because `transformResponse()` currently returns the whole `{ code, msg, data }` wrapper for object endpoints.

- [ ] **Step 3: Add frontend list response type alias**

Modify `frontend/src/request/types.ts`:

```ts
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'

export interface ApiResponse<T = unknown> {
  code?: number | string
  msg?: string
  data?: T
  rows?: T
  total?: number
  [key: string]: unknown
}

export type PageResponse<T> = ApiResponse<T[]> & {
  rows: T[]
  total: number
}

export type RepeatStrategy = 'reuse' | 'cancel-prev' | 'ignore-new' | 'none'

export interface RequestConfig extends AxiosRequestConfig {
  /** false 时不注入 Authorization。兼容 headers.isToken = false。 */
  isToken?: boolean

  /** true 时启用重复提交拦截。兼容 headers.repeatSubmit = false 关闭拦截。 */
  isRepeatSubmit?: boolean

  /** 单接口自定义重复提交间隔。 */
  repeatSubmitInterval?: number

  /** true 时直接返回 AxiosResponse。 */
  isReturnNativeResponse?: boolean

  /** true 时直接返回 response.data，不做业务 code 判断。 */
  isTransformResponse?: boolean

  /** false 时关闭进行中相同请求去重。 */
  isDedupe?: boolean

  /** 是否允许请求取消。默认 true。 */
  isCancelable?: boolean

  /** 请求取消分组。常用于页面级取消。 */
  cancelGroup?: string

  /**
   * 重复请求处理策略。
   *
   * - reuse: 复用进行中的相同请求 Promise
   * - cancel-prev: 取消上一次相同请求，然后发起新请求
   * - ignore-new: 忽略新请求，直接返回旧请求 Promise
   * - none: 不处理重复请求
   *
   * 默认：GET 使用 reuse；其他方法使用 none。
   */
  repeatStrategy?: RepeatStrategy

  /** 是否展示全局错误提示。默认 true。 */
  showError?: boolean

  /** 是否启用 GET 结果缓存。默认 false。 */
  cache?: boolean

  /** 缓存时间，单位 ms。 */
  cacheTime?: number

  /** 自定义缓存 key。 */
  cacheKey?: string
}

export type PlusInternalRequestConfig = InternalAxiosRequestConfig & RequestConfig

export type RepeatSubmitRecord = {
  url?: string
  data?: string
  time: number
}

export type RequestPendingRecord = {
  promise: Promise<unknown>
}
```

- [ ] **Step 4: Update transformResponse to unwrap data and preserve rows**

Modify the success branch in `frontend/src/request/transform.ts`:

```ts
function hasOwn(data: ApiResponse, key: keyof ApiResponse): boolean {
  return Object.prototype.hasOwnProperty.call(data, key)
}

function resolveSuccessPayload(data: ApiResponse): unknown {
  if (hasOwn(data, 'rows')) {
    return {
      code: data.code,
      msg: data.msg,
      rows: Array.isArray(data.rows) ? data.rows : [],
      total: typeof data.total === 'number' ? data.total : 0,
    }
  }

  if (hasOwn(data, 'data')) {
    return data.data
  }

  return data
}
```

Then replace this block:

```ts
if (code === HttpStatus.SUCCESS || code === String(HttpStatus.SUCCESS)) {
  return response.data
}
```

with:

```ts
if (code === HttpStatus.SUCCESS || code === String(HttpStatus.SUCCESS)) {
  return resolveSuccessPayload(response.data)
}
```

- [ ] **Step 5: Run request transform tests**

Run:

```bash
cd frontend && npm test -- request-transform.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add frontend/src/request/types.ts frontend/src/request/transform.ts frontend/tests/request-transform.test.ts
git commit -m "feat: support unified api response envelope"
```

Expected: Commit succeeds.

---

### Task 2: Backend Unified Response Helper And Crawler Task Envelopes

**Files:**
- Create: `backend/app/schemas/response.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/app/modules/crawl_tasks/router.py`
- Modify: `backend/tests/test_crawl_tasks_api.py`

- [ ] **Step 1: Update backend tests for rows and total**

Modify `backend/tests/test_crawl_tasks_api.py` so list assertions expect `rows` and `total`:

```python
from http import HTTPStatus

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def task_payload() -> dict:
    return {
        "name": "每日媒体索引",
        "description": "跟踪测试资源",
        "keywords": ["media", "forge"],
        "target_websites": ["https://example.com"],
        "schedule": "daily",
        "max_pages": 100,
        "crawl_depth": 3,
    }


class TestCrawlTasksApi:
    def test_legacy_route_returns_rows_total_instead_of_raw_list(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        response = client.get(
            "/api/crawl-tasks?skip=0&limit=20",
            headers=auth_headers(client, admin_user),
        )

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body["code"] == 200
        assert body["msg"] == "success"
        assert body["rows"] == []
        assert body["total"] == 0

    def test_canonical_route_creates_and_lists_task_with_rows_total(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)

        created_response = client.post(
            "/api/crawler/tasks",
            json=task_payload(),
            headers=headers,
        )

        assert created_response.status_code == HTTPStatus.CREATED
        created_body = created_response.json()
        assert created_body["code"] == 200
        created = created_body["data"]
        assert created["name"] == "每日媒体索引"
        assert created["owner_id"] == str(admin_user.id)
        assert created["status"] == "pending"

        list_response = client.get("/api/crawler/tasks", headers=headers)
        assert list_response.status_code == HTTPStatus.OK
        list_body = list_response.json()
        assert list_body["code"] == 200
        assert list_body["total"] == 1
        assert [item["name"] for item in list_body["rows"]] == ["每日媒体索引"]

    def test_legacy_route_uses_same_rows_as_canonical_route(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        client.post("/api/crawler/tasks", json=task_payload(), headers=headers)

        response = client.get("/api/crawl-tasks?skip=0&limit=20", headers=headers)

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body["total"] == 1
        assert [item["name"] for item in body["rows"]] == ["每日媒体索引"]
```

- [ ] **Step 2: Run backend tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: FAIL because list endpoints currently return raw arrays and object endpoints return raw objects.

- [ ] **Step 3: Add backend response schema helpers**

Create `backend/app/schemas/response.py`:

```python
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int | str = 200
    msg: str = "success"
    data: T | None = None


class PageResponse(BaseModel, Generic[T]):
    code: int | str = 200
    msg: str = "success"
    rows: list[T] = Field(default_factory=list)
    total: int = 0


def ok(data: T | None = None, *, msg: str = "success") -> ApiResponse[T]:
    return ApiResponse[T](code=200, msg=msg, data=data)


def page(rows: list[T], total: int, *, msg: str = "success") -> PageResponse[T]:
    return PageResponse[T](code=200, msg=msg, rows=rows, total=total)
```

- [ ] **Step 4: Wrap canonical crawler task routes**

Modify `backend/app/modules/crawler/tasks/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.models.crawl_task import CrawlTask
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskRead,
    CrawlTaskUpdate,
)
from backend.app.schemas.response import ApiResponse, PageResponse, ok, page

router = APIRouter(prefix="/api/crawler/tasks", tags=["crawler-tasks"])


@router.get("", response_model=PageResponse[CrawlTaskRead])
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> PageResponse[CrawlTask]:
    repo = CrawlTaskRepository(db)
    rows = repo.get_by_owner(current_user.id, skip=skip, limit=limit)
    total = repo.count_by_owner(current_user.id)
    return page(rows, total)


@router.get("/stats", response_model=ApiResponse[dict[str, int]])
def get_stats(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, int]]:
    repo = CrawlTaskRepository(db)
    return ok({"total": repo.count_by_owner(current_user.id)})


@router.get("/{task_id}", response_model=ApiResponse[CrawlTaskRead])
def get_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[CrawlTask]:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return ok(task)


@router.post("", response_model=ApiResponse[CrawlTaskRead], status_code=status.HTTP_201_CREATED)
def create_task(
    data: CrawlTaskCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[CrawlTask]:
    task = CrawlTask(**data.model_dump(), owner_id=current_user.id)
    repo = CrawlTaskRepository(db)
    return ok(repo.create(task))


@router.put("/{task_id}", response_model=ApiResponse[CrawlTaskRead])
def update_task(
    task_id: uuid.UUID,
    data: CrawlTaskUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[CrawlTask]:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    return ok(repo.update(task))


@router.delete("/{task_id}", response_model=ApiResponse[None])
def delete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ApiResponse[None]:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    repo.delete(task)
    return ok(None, msg="deleted")
```

- [ ] **Step 5: Update legacy compatibility response models**

Modify `backend/app/modules/crawl_tasks/router.py`:

```python
"""Compatibility routes for the old /api/crawl-tasks prefix."""

from fastapi import APIRouter

from backend.app.modules.crawler.tasks.router import (
    create_task,
    delete_task,
    get_stats,
    get_task,
    list_tasks,
    update_task,
)
from backend.app.schemas.crawl_task import CrawlTaskRead
from backend.app.schemas.response import ApiResponse, PageResponse

router = APIRouter(prefix="/api/crawl-tasks", tags=["crawl-tasks-compat"])

router.add_api_route("", list_tasks, methods=["GET"], response_model=PageResponse[CrawlTaskRead])
router.add_api_route("/stats", get_stats, methods=["GET"], response_model=ApiResponse[dict[str, int]])
router.add_api_route("/{task_id}", get_task, methods=["GET"], response_model=ApiResponse[CrawlTaskRead])
router.add_api_route("", create_task, methods=["POST"], status_code=201, response_model=ApiResponse[CrawlTaskRead])
router.add_api_route("/{task_id}", update_task, methods=["PUT"], response_model=ApiResponse[CrawlTaskRead])
router.add_api_route("/{task_id}", delete_task, methods=["DELETE"], response_model=ApiResponse[None])
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git add backend/app/schemas/response.py backend/app/modules/crawler/tasks/router.py backend/app/modules/crawl_tasks/router.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat: wrap crawler task responses"
```

Expected: Commit succeeds.

---

### Task 3: Frontend Crawler Task List Reads rows And total

**Files:**
- Modify: `frontend/src/api/crawlTask/index.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/tests/App.test.tsx`
- Test: `frontend/tests/crawler-task-pages.ui.test.tsx`

- [ ] **Step 1: Add or update crawler task page tests for rows/total**

Create `frontend/tests/crawler-task-pages.ui.test.tsx` if it does not exist:

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'

const navigateMock = vi.fn()

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

vi.mock('../src/api/crawlTask', () => ({
  deleteCrawlTask: vi.fn().mockResolvedValue(undefined),
  getCrawlTasks: vi.fn().mockResolvedValue({
    code: 200,
    msg: 'success',
    rows: [
      {
        id: 'task-1',
        name: '每日媒体索引',
        description: '跟踪测试资源',
        keywords: ['media', 'forge'],
        target_websites: ['https://example.com'],
        schedule: 'daily',
        max_pages: 100,
        crawl_depth: 3,
        status: 'pending',
        task_id: null,
        error_message: null,
        started_at: null,
        completed_at: null,
        total_found: 0,
        total_qualified: 0,
        owner_id: 'user-1',
        created_at: '2026-07-02T00:00:00Z',
        updated_at: null,
      },
    ],
    total: 42,
  }),
}))

describe('crawler task list rows total handling', () => {
  beforeEach(() => {
    navigateMock.mockReset()
  })

  it('renders rows from ApiResponse and uses backend total', async () => {
    render(
      <AntApp>
        <TaskListPage />
      </AntApp>,
    )

    expect(await screen.findByText('每日媒体索引')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('共 42 条')).toBeInTheDocument()
    })
  })
})
```

Modify `frontend/tests/App.test.tsx` mock for `getCrawlTasks`:

```ts
vi.mock('@/api/crawlTask', () => ({
  getCrawlTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  deleteCrawlTask: vi.fn().mockResolvedValue(undefined),
}))
```

- [ ] **Step 2: Run frontend page tests to verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx App.test.tsx
```

Expected: FAIL because `TaskListPage` still treats `getCrawlTasks()` as an array and computes `total` locally.

- [ ] **Step 3: Update crawl task API client return type**

Modify `frontend/src/api/crawlTask/index.ts`:

```ts
import { request } from '@/request'
import type { PageResponse } from '@/request'
import type {
  CrawlTask,
  CrawlTaskCreateParams,
  CrawlTaskStats,
  CrawlTaskUpdateParams,
} from './types'

const BASE_URL = '/api/crawler/tasks'

export function getCrawlTasks(params?: {
  skip?: number
  limit?: number
}): Promise<PageResponse<CrawlTask>> {
  return request.get<PageResponse<CrawlTask>>(BASE_URL, params)
}

export function getCrawlTaskStats(): Promise<CrawlTaskStats> {
  return request.get<CrawlTaskStats>(`${BASE_URL}/stats`)
}

export function getCrawlTask(taskId: string): Promise<CrawlTask> {
  return request.get<CrawlTask>(`${BASE_URL}/${taskId}`)
}

export function createCrawlTask(data: CrawlTaskCreateParams): Promise<CrawlTask> {
  return request.post<CrawlTask>(BASE_URL, data)
}

export function updateCrawlTask(
  taskId: string,
  data: CrawlTaskUpdateParams,
): Promise<CrawlTask> {
  return request.put<CrawlTask>(`${BASE_URL}/${taskId}`, data)
}

export function deleteCrawlTask(taskId: string): Promise<void> {
  return request.delete(`${BASE_URL}/${taskId}`)
}
```

If `frontend/src/request/index.ts` does not export `PageResponse`, update its type export line:

```ts
export type {ApiResponse, PageResponse, RequestConfig, RepeatStrategy}
```

- [ ] **Step 4: Update TaskListPage to consume rows and total**

Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx` `fetchTasks` body:

```tsx
  const fetchTasks = useCallback(async (page: number) => {
    setLoading(true)
    try {
      const skip = (page - 1) * PAGE_SIZE
      const result = await getCrawlTasks({ skip, limit: PAGE_SIZE })
      setTasks(result.rows)
      setTotal(result.total)
    } finally {
      setLoading(false)
    }
  }, [])
```

- [ ] **Step 5: Run frontend page tests**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx App.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add frontend/src/api/crawlTask/index.ts frontend/src/request/index.ts frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/tests/crawler-task-pages.ui.test.tsx frontend/tests/App.test.tsx
git commit -m "feat: consume task list rows and total"
```

Expected: Commit succeeds.

---

### Task 4: Full Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run backend crawler API tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run all backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- request-transform.test.ts crawler-task-pages.ui.test.tsx App.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run all frontend tests**

Run:

```bash
cd frontend && npm test
```

Expected: PASS.

- [ ] **Step 5: Run frontend lint and build**

Run:

```bash
cd frontend && npm run lint && npm run build
```

Expected: PASS.

---

## Self-Review

**Spec coverage:** The plan adds a backend unified response helper, returns `rows` and `total` from crawler list endpoints, wraps crawler object endpoints in `data`, keeps legacy `/api/crawl-tasks` compatible, updates frontend transform behavior for the existing `ApiResponse<T>` type, and updates task list code to consume `rows` and `total`.

**Placeholder scan:** No placeholder markers or incomplete steps remain.

**Type consistency:** `ApiResponse<T>`, `PageResponse<T>`, `rows`, `total`, and `CrawlTask` are consistently named across backend helpers, frontend request types, API client, page code, and tests.
