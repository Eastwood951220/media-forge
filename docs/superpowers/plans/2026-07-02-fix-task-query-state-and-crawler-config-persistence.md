# Task Query State and Crawler Config Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix crawler task query conditions being lost after page switches, and make crawler config parameters survive backend/project restarts.

**Architecture:** Keep the existing TanStack Router layout and route keep-alive bridge, but add regression coverage that proves route/page state survives navigation. Store the crawler task list query state explicitly in a small Zustand page-state store so the search field is not dependent on an uncontrolled Ant Design input. Persist crawler config updates to the project env file that `scraper.config.settings` loads on startup, while still updating `os.environ` for the running process.

**Tech Stack:** React 19, TanStack Router 1.x, Zustand 5, Ant Design 6, Vitest, React Testing Library, FastAPI, Pydantic, Pytest, Python stdlib env-file parsing/writing.

---

## Root Cause Summary

- `frontend/src/layout/routeCache.tsx` exists, but the current tests only mock `KeepAlive` and assert props. They do not prove a page component keeps local state after navigating away and back.
- `frontend/src/pages/crawler/tasks/TaskListPage.tsx` does not own the search keyword state. `TaskListTable` renders an uncontrolled `Input.Search`, so the typed value can disappear whenever the page remounts.
- `TaskListPage` also ignores the keyword passed by `TaskListTable.onSearch`; it always calls `getCrawlTasks({ skip, limit })`.
- `backend/app/modules/crawler/config/router.py` persists crawler parameters only into `os.environ`. That explains why parameters work until process restart and then reset to defaults from `.env` / `.env.<APP_ENV>`.

## File Structure

- Create: `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts`
  - Own task-list page query state (`keyword`, `current`) independently of component mount lifecycle.
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
  - Read/write task-list query state and pass `keyword` to the API.
- Modify: `frontend/src/pages/crawlTasks/components/TaskListTable.tsx`
  - Make the search input controlled.
- Modify: `frontend/src/api/crawlTask/index.ts`
  - Add optional `keyword` query parameter.
- Modify: `backend/app/repositories/crawl_task.py`
  - Add keyword-aware listing/counting methods.
- Modify: `backend/app/modules/crawler/tasks/router.py`
  - Accept `keyword` and return filtered paginated rows.
- Modify: `backend/app/modules/crawler/config/router.py`
  - Persist changed config keys to `.env` or `.env.<APP_ENV>` and read persisted values when process env is absent.
- Modify: `backend/tests/test_crawler_config_api.py`
  - Add restart-simulation test for config persistence.
- Modify: `backend/tests/test_crawl_tasks_api.py`
  - Add keyword filter test.
- Create: `frontend/tests/task-list-query-state.ui.test.tsx`
  - Prove the query input value survives navigating away and back.
- Modify: `frontend/tests/route-keepalive.ui.test.tsx`
  - Add one test that uses the real keep-alive bridge behavior or a stateful wrapper, not only prop assertions.

---

### Task 1: Persist Crawler Config Updates to Env File

**Files:**
- Modify: `backend/tests/test_crawler_config_api.py`
- Modify: `backend/app/modules/crawler/config/router.py`

- [ ] **Step 1: Write the failing persistence test**

Append this test to `backend/tests/test_crawler_config_api.py`:

```python
def test_update_crawler_config_persists_to_env_file_after_env_reset(
    client: TestClient,
    admin_user,
    monkeypatch,
    tmp_path,
) -> None:
    from backend.app.modules.crawler.config import router as config_router

    env_file = tmp_path / ".env"
    env_file.write_text(
        "REQUEST_TIMEOUT=30\n"
        "UNCHANGED_VALUE=keep-me\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config_router.cfg, "BASE_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("MAX_LIST_PAGES", raising=False)
    monkeypatch.delenv("REQUEST_TIMEOUT", raising=False)

    response = client.put(
        "/api/crawler/config",
        json={
            "MAX_LIST_PAGES": 17,
            "REQUEST_TIMEOUT": 46,
        },
        headers=auth_headers(client, admin_user),
    )

    assert response.status_code == HTTPStatus.OK
    persisted = env_file.read_text(encoding="utf-8")
    assert "MAX_LIST_PAGES=17\n" in persisted
    assert "REQUEST_TIMEOUT=46\n" in persisted
    assert "UNCHANGED_VALUE=keep-me\n" in persisted

    monkeypatch.delenv("MAX_LIST_PAGES", raising=False)
    monkeypatch.delenv("REQUEST_TIMEOUT", raising=False)

    get_response = client.get(
        "/api/crawler/config",
        headers=auth_headers(client, admin_user),
    )

    assert get_response.status_code == HTTPStatus.OK
    data = get_response.json()["data"]
    assert data["MAX_LIST_PAGES"] == 17
    assert data["REQUEST_TIMEOUT"] == 46
```

- [ ] **Step 2: Run the failing backend config test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py::test_update_crawler_config_persists_to_env_file_after_env_reset -v
```

Expected: FAIL because `update_config` does not write any env file and `_read_config` does not read persisted env-file values when process env is empty.

- [ ] **Step 3: Replace crawler config router with persistent implementation**

Replace `backend/app/modules/crawler/config/router.py` with this complete content:

```python
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.crawler.config.schemas import ConfigUpdate, CookiesConfig
from scraper.config import settings as cfg
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/config", tags=["crawler-config"])

CONFIG_KEYS = [
    "MAX_LIST_PAGES",
    "LIST_PAGE_DELAY_MIN",
    "LIST_PAGE_DELAY_MAX",
    "DETAIL_PAGE_DELAY_MIN",
    "DETAIL_PAGE_DELAY_MAX",
    "SECURITY_WAIT_SECONDS",
    "REQUEST_TIMEOUT",
    "INCREMENTAL_EXIST_THRESHOLD",
]

DEFAULT_COOKIE_FILE = "javdb_cookies.json"


def _defaults() -> dict[str, Any]:
    return {
        "MAX_LIST_PAGES": cfg.MAX_LIST_PAGES,
        "LIST_PAGE_DELAY_MIN": cfg.LIST_PAGE_DELAY_MIN,
        "LIST_PAGE_DELAY_MAX": cfg.LIST_PAGE_DELAY_MAX,
        "DETAIL_PAGE_DELAY_MIN": cfg.DETAIL_PAGE_DELAY_MIN,
        "DETAIL_PAGE_DELAY_MAX": cfg.DETAIL_PAGE_DELAY_MAX,
        "SECURITY_WAIT_SECONDS": cfg.SECURITY_WAIT_SECONDS,
        "REQUEST_TIMEOUT": cfg.REQUEST_TIMEOUT,
        "INCREMENTAL_EXIST_THRESHOLD": cfg.INCREMENTAL_EXIST_THRESHOLD,
    }


def _env_file_path() -> Path:
    app_env = os.getenv("APP_ENV", "production")
    filename = f".env.{app_env}" if app_env != "production" else ".env"
    return cfg.BASE_DIR / filename


def _coerce_env_value(value: str) -> bool | int | float | str:
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


def _read_env_file_values() -> dict[str, str]:
    filepath = _env_file_path()
    if not filepath.exists():
        return {}

    values: dict[str, str] = {}
    for line in filepath.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _serialize_env_value(value: Any) -> str:
    text = str(value)
    if not text or any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _write_env_file_values(updated: dict[str, Any]) -> None:
    filepath = _env_file_path()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = filepath.read_text(encoding="utf-8").splitlines() if filepath.exists() else []
    remaining = dict(updated)
    next_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_lines.append(line)
            continue

        key, _value = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in remaining:
            next_lines.append(f"{normalized_key}={_serialize_env_value(remaining.pop(normalized_key))}")
        else:
            next_lines.append(line)

    for key, value in remaining.items():
        next_lines.append(f"{key}={_serialize_env_value(value)}")

    tmp_path = filepath.with_name(f"{filepath.name}.tmp")
    tmp_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    tmp_path.replace(filepath)


def _read_config() -> dict[str, Any]:
    defaults = _defaults()
    persisted = _read_env_file_values()
    result: dict[str, Any] = {}
    for key in CONFIG_KEYS:
        value = os.getenv(key)
        if value is not None:
            result[key] = _coerce_env_value(value)
        elif key in persisted:
            result[key] = _coerce_env_value(persisted[key])
        elif key in defaults:
            result[key] = defaults[key]
    return result


def _cookie_path() -> Path:
    return cfg.COOKIE_DIR / DEFAULT_COOKIE_FILE


@router.get("")
def get_config(_current_user: CurrentUser) -> dict:
    return success(data=_read_config())


@router.put("")
def update_config(body: ConfigUpdate, _current_user: CurrentUser) -> dict:
    updated = body.model_dump(exclude_none=True)
    for key, value in updated.items():
        os.environ[key] = str(value)
    _write_env_file_values(updated)
    return success(data=_read_config())


@router.get("/cookies")
def get_cookies_config(_current_user: CurrentUser) -> dict:
    filepath = _cookie_path()
    if not filepath.exists():
        return success(data=CookiesConfig(cookies=[]).model_dump())

    try:
        with filepath.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return success(data=CookiesConfig(cookies=[]).model_dump())

    if isinstance(data, list):
        return success(data=CookiesConfig(cookies=data).model_dump())

    if isinstance(data, dict):
        cookies_list = [
            {"name": key, "value": value, "domain": "javdb.com", "path": "/"}
            for key, value in data.items()
        ]
        return success(data=CookiesConfig(cookies=cookies_list).model_dump())

    return success(data=CookiesConfig(cookies=[]).model_dump())


@router.put("/cookies")
def update_cookies_config(body: CookiesConfig, _current_user: CurrentUser) -> dict:
    filepath = _cookie_path()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    cookies_list = [cookie.model_dump() for cookie in body.cookies]
    with filepath.open("w", encoding="utf-8") as file:
        json.dump(cookies_list, file, ensure_ascii=False, indent=2)
    return success(data=body.model_dump())
```

- [ ] **Step 4: Run crawler config tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py -v
```

Expected: PASS. Existing cookie tests still pass, and the new env-file persistence test passes.

- [ ] **Step 5: Commit config persistence**

Run:

```bash
git add backend/app/modules/crawler/config/router.py backend/tests/test_crawler_config_api.py
git commit -m "fix(backend): persist crawler config parameters"
```

Expected: one commit containing only crawler config persistence changes and tests.

---

### Task 2: Support Keyword Filtering in the Crawler Task API

**Files:**
- Modify: `backend/tests/test_crawl_tasks_api.py`
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `frontend/src/api/crawlTask/index.ts`

- [ ] **Step 1: Add a backend keyword filter test**

Append this test method inside `class TestCrawlTasksApi` in `backend/tests/test_crawl_tasks_api.py`:

```python
    def test_canonical_route_filters_tasks_by_keyword(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        daily_payload = task_payload()
        daily_payload["name"] = "每日媒体索引"
        archive_payload = task_payload()
        archive_payload["name"] = "归档清理任务"

        client.post("/api/crawler/tasks", json=daily_payload, headers=headers)
        client.post("/api/crawler/tasks", json=archive_payload, headers=headers)

        response = client.get(
            "/api/crawler/tasks?keyword=每日",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        rows = body["data"]["rows"] if "data" in body else body["rows"]
        total = body["data"]["total"] if "data" in body else body["total"]
        assert total == 1
        assert [item["name"] for item in rows] == ["每日媒体索引"]
```

- [ ] **Step 2: Run the failing backend keyword test**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_canonical_route_filters_tasks_by_keyword -v
```

Expected: FAIL because `/api/crawler/tasks` does not accept or apply `keyword`.

- [ ] **Step 3: Add repository filtering methods**

Modify `backend/app/repositories/crawl_task.py` so `get_by_owner` and `count_by_owner` accept `keyword`:

```python
    def _owner_query(self, owner_id: uuid.UUID, keyword: str | None = None):
        query = self.session.query(CrawlTask).filter(CrawlTask.owner_id == owner_id)
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            query = query.filter(CrawlTask.name.ilike(f"%{normalized_keyword}%"))
        return query

    def get_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
        keyword: str | None = None,
    ) -> list[CrawlTask]:
        return (
            self._owner_query(owner_id, keyword)
            .order_by(CrawlTask.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_owner(self, owner_id: uuid.UUID, keyword: str | None = None) -> int:
        return (
            self._owner_query(owner_id, keyword)
            .with_entities(func.count(CrawlTask.id))
            .scalar()
            or 0
        )
```

Keep the existing `get_by_task_id` and `get_owned` methods unchanged.

- [ ] **Step 4: Pass keyword through the route**

Modify `list_tasks` in `backend/app/modules/crawler/tasks/router.py` to this function:

```python
@router.get("")
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    repo = CrawlTaskRepository(db)
    rows = repo.get_by_owner(current_user.id, skip=skip, limit=limit, keyword=keyword)
    total = repo.count_by_owner(current_user.id, keyword=keyword)
    return paginated(rows=rows, total=total)
```

- [ ] **Step 5: Pass keyword from the frontend API helper**

Modify `getCrawlTasks` in `frontend/src/api/crawlTask/index.ts` to this complete function:

```ts
export function getCrawlTasks(params?: {
  skip?: number
  limit?: number
  keyword?: string
}): Promise<PaginatedResponse<CrawlTask>> {
  return request.get<PaginatedResponse<CrawlTask>>(BASE_URL, params)
}
```

- [ ] **Step 6: Run backend keyword tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit keyword filtering**

Run:

```bash
git add backend/app/repositories/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawl_tasks_api.py frontend/src/api/crawlTask/index.ts
git commit -m "fix(crawler): filter tasks by search keyword"
```

Expected: one commit containing API keyword filtering changes.

---

### Task 3: Preserve Task List Query State Across Page Switches

**Files:**
- Create: `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawlTasks/components/TaskListTable.tsx`
- Create: `frontend/tests/task-list-query-state.ui.test.tsx`

- [ ] **Step 1: Write the failing frontend state-retention test**

Create `frontend/tests/task-list-query-state.ui.test.tsx` with this complete content:

```tsx
import { Outlet, createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider, useNavigate } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { useTaskListQueryStore } from '../src/pages/crawler/tasks/useTaskListQueryStore'
import { getCrawlTasks } from '../src/api/crawlTask'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  deleteCrawlTask: vi.fn(),
}))

function TestShell() {
  const navigate = useNavigate()
  return (
    <div>
      <button type="button" onClick={() => void navigate({ to: '/crawler/tasks' })}>
        tasks
      </button>
      <button type="button" onClick={() => void navigate({ to: '/crawler/config' })}>
        config
      </button>
      <Outlet />
    </div>
  )
}

function renderTaskRoutes() {
  const rootRoute = createRootRoute({ component: TestShell })
  const taskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: TaskListPage,
  })
  const configRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/config',
    component: () => <div>config page</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([taskRoute, configRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/tasks'] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('TaskListPage query state', () => {
  beforeEach(() => {
    useTaskListQueryStore.getState().reset()
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [],
      total: 0,
      page: 1,
      page_size: 20,
    })
  })

  it('keeps the search condition after switching away and back', async () => {
    renderTaskRoutes()

    const searchInput = await screen.findByPlaceholderText('搜索任务名称')
    await userEvent.type(searchInput, '每日')

    await waitFor(() => {
      expect(getCrawlTasks).toHaveBeenLastCalledWith({
        skip: 0,
        limit: 20,
        keyword: '每日',
      })
    })

    await userEvent.click(screen.getByRole('button', { name: 'config' }))
    expect(await screen.findByText('config page')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'tasks' }))
    expect(await screen.findByPlaceholderText('搜索任务名称')).toHaveValue('每日')
  })
})
```

- [ ] **Step 2: Run the failing frontend state test**

Run:

```bash
cd frontend
npm test -- tests/task-list-query-state.ui.test.tsx -- --run
```

Expected: FAIL because `useTaskListQueryStore` does not exist and the search input is uncontrolled.

- [ ] **Step 3: Create the task-list query store**

Create `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts` with this complete content:

```ts
import { create } from 'zustand'

type TaskListQueryState = {
  keyword: string
  current: number
  setKeyword: (keyword: string) => void
  setCurrent: (current: number) => void
  reset: () => void
}

export const useTaskListQueryStore = create<TaskListQueryState>()((set) => ({
  keyword: '',
  current: 1,
  setKeyword: (keyword) => set({ keyword, current: 1 }),
  setCurrent: (current) => set({ current }),
  reset: () => set({ keyword: '', current: 1 }),
}))
```

- [ ] **Step 4: Make TaskListTable search controlled**

Modify `TaskListTableProps` in `frontend/src/pages/crawlTasks/components/TaskListTable.tsx`:

```ts
type TaskListTableProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  current: number
  pageSize: number
  keyword: string
  onKeywordChange: (keyword: string) => void
  onPageChange: (page: number, pageSize: number) => void
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onSearch: (keyword: string) => void
}
```

Update the destructuring in `TaskListTable`:

```ts
function TaskListTable({
  tasks,
  loading,
  total,
  current,
  pageSize,
  keyword,
  onKeywordChange,
  onPageChange,
  onEdit,
  onDelete,
  onSearch,
}: TaskListTableProps) {
```

Replace the `Input.Search` with this controlled version:

```tsx
        <Input.Search
          placeholder="搜索任务名称"
          allowClear
          enterButton={<SearchOutlined />}
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          onSearch={onSearch}
          style={{ maxWidth: 320 }}
        />
```

- [ ] **Step 5: Read/write query state in TaskListPage**

Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`:

Add this import:

```ts
import { useTaskListQueryStore } from './useTaskListQueryStore'
```

Replace the `current` state with Zustand selectors:

```ts
  const keyword = useTaskListQueryStore((state) => state.keyword)
  const current = useTaskListQueryStore((state) => state.current)
  const setKeyword = useTaskListQueryStore((state) => state.setKeyword)
  const setCurrent = useTaskListQueryStore((state) => state.setCurrent)
```

Replace `fetchTasks` with:

```ts
  const fetchTasks = useCallback(async (page: number, nextKeyword: string) => {
    setLoading(true)
    try {
      const skip = (page - 1) * PAGE_SIZE
      const normalizedKeyword = nextKeyword.trim()
      const data = await getCrawlTasks({
        skip,
        limit: PAGE_SIZE,
        keyword: normalizedKeyword || undefined,
      })
      setTasks(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])
```

Replace the initial `useEffect` with:

```ts
  useEffect(() => {
    void fetchTasks(current, keyword)
  }, [current, fetchTasks, keyword])
```

Replace `handlePageChange` with:

```ts
  const handlePageChange = useCallback(
    (page: number) => {
      setCurrent(page)
    },
    [setCurrent],
  )
```

Update delete refresh:

```ts
          void fetchTasks(current, keyword)
```

Add this search callback:

```ts
  const handleSearch = useCallback(
    (nextKeyword: string) => {
      setKeyword(nextKeyword)
    },
    [setKeyword],
  )
```

Pass the controlled props into `TaskListTable`:

```tsx
          keyword={keyword}
          onKeywordChange={setKeyword}
          onSearch={handleSearch}
```

- [ ] **Step 6: Run the frontend state-retention test**

Run:

```bash
cd frontend
npm test -- tests/task-list-query-state.ui.test.tsx -- --run
```

Expected: PASS. The search input keeps `每日` after navigating to `/crawler/config` and back to `/crawler/tasks`.

- [ ] **Step 7: Commit task query state**

Run:

```bash
git add frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawlTasks/components/TaskListTable.tsx frontend/tests/task-list-query-state.ui.test.tsx
git commit -m "fix(frontend): preserve task query state"
```

Expected: one commit containing the task-list state store, controlled input, and regression test.

---

### Task 4: Harden Route KeepAlive Regression Coverage

**Files:**
- Modify: `frontend/tests/route-keepalive.ui.test.tsx`
- Modify: `frontend/src/layout/routeCache.tsx`

- [ ] **Step 1: Add a real state-retention route-cache test**

Append this test to `frontend/tests/route-keepalive.ui.test.tsx`. Do not remove the existing prop tests.

```tsx
it('keeps keyed outlet content mounted for route cache keys', async () => {
  const user = userEvent.setup()
  function CachedInputPage() {
    const [value, setValue] = useState('')
    return (
      <input
        aria-label="cached input"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
    )
  }

  const rootRoute = createRootRoute({
    component: () => (
      <RouteKeepAliveProvider>
        <nav>
          <RouterLink to="/crawler/tasks">tasks</RouterLink>
          <RouterLink to="/crawler/config">config</RouterLink>
        </nav>
        <RouteKeepAliveOutlet />
      </RouteKeepAliveProvider>
    ),
  })
  const taskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: CachedInputPage,
  })
  const configRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/config',
    component: () => <div>config page</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([taskRoute, configRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/tasks'] }),
  })

  render(<RouterProvider router={router} />)

  await user.type(await screen.findByLabelText('cached input'), 'stored')
  await user.click(screen.getByText('config'))
  expect(await screen.findByText('config page')).toBeInTheDocument()
  await user.click(screen.getByText('tasks'))

  expect(await screen.findByLabelText('cached input')).toHaveValue('stored')
})
```

At the top of `frontend/tests/route-keepalive.ui.test.tsx`, update imports:

```tsx
import { useState, type PropsWithChildren } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  Link as RouterLink,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
```

- [ ] **Step 2: Run the route-cache regression test**

Run:

```bash
cd frontend
npm test -- tests/route-keepalive.ui.test.tsx -- --run
```

Expected: If it fails, the current `<Outlet />` cache wrapper is not preserving the actual routed page instance.

- [ ] **Step 3: Key the outlet content by active cache key**

If Step 2 fails, replace the children inside `KeepAlive` in `frontend/src/layout/routeCache.tsx`:

```tsx
    <KeepAlive
      activeCacheKey={activeCacheKey}
      aliveRef={aliveRef}
      exclude={ROUTE_CACHE_EXCLUDE_PATHS}
      max={18}
    >
      <Outlet key={activeCacheKey} />
    </KeepAlive>
```

- [ ] **Step 4: Run route-cache tests again**

Run:

```bash
cd frontend
npm test -- tests/route-keepalive.ui.test.tsx -- --run
```

Expected: PASS. If it still fails, do not keep stacking route-cache changes; keep Task 3 as the direct symptom fix and document that TanStack Router outlet caching needs a larger adapter design.

- [ ] **Step 5: Commit route-cache regression coverage**

Run:

```bash
git add frontend/src/layout/routeCache.tsx frontend/tests/route-keepalive.ui.test.tsx
git commit -m "test(frontend): cover route cache state retention"
```

Expected: one commit containing the route-cache regression test and the outlet keying change only if needed.

---

### Task 5: Final Verification

**Files:**
- Verify: `backend/app/modules/crawler/config/router.py`
- Verify: `backend/app/modules/crawler/tasks/router.py`
- Verify: `backend/app/repositories/crawl_task.py`
- Verify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Verify: `frontend/src/pages/crawlTasks/components/TaskListTable.tsx`
- Verify: `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_config_api.py backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend
npm test -- tests/task-list-query-state.ui.test.tsx tests/route-keepalive.ui.test.tsx tests/tags-view.ui.test.tsx -- --run
```

Expected: PASS.

- [ ] **Step 3: Run frontend lint and build**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: both commands PASS.

- [ ] **Step 4: Run full test suites that are configured**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests -v
cd frontend
npm test -- --run
```

Expected: PASS, except for unrelated pre-existing failures. If unrelated failures appear, capture the failing test names and error messages before deciding whether to expand scope.

- [ ] **Step 5: Inspect changed files**

Run:

```bash
git status --short
git diff --stat
```

Expected: only files from this plan are changed by this implementation pass.

---

## Self-Review

- Spec coverage: The plan fixes task query state loss after page switching and crawler config parameter reset after restart.
- Root cause coverage: The plan addresses both missing explicit frontend query state and backend in-memory-only config mutation.
- Placeholder scan: No placeholder implementation steps remain. Every code-changing step gives exact code or a precise replacement block.
- Type consistency: `keyword` is consistently a string in frontend state and an optional query parameter in frontend/backend API calls. Crawler config persistence consistently uses `CONFIG_KEYS`.
