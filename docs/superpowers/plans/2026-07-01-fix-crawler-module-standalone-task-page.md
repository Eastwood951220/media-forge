# Crawler Module Standalone Task Page Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the current `crawl_tasks` database error, move crawler tasks under a parent “爬虫” module, and replace the modal-based new task flow with an original-style standalone task page.

**Architecture:** Treat the pasted log as a schema-registration and migration failure: the running backend reaches `backend/app/modules/crawl_tasks/router.py`, but PostgreSQL has no `crawl_tasks` table. Consolidate the current generic `/crawl-tasks` work into a canonical crawler module: backend routes live under `backend/app/modules/crawler/tasks`, frontend routes live under `/crawler/tasks`, and the sidebar has a parent “爬虫” menu with “任务列表” as a child. Keep a temporary `/api/crawl-tasks` backend compatibility router during the transition so stale frontend calls no longer produce 500 errors.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pytest, React 19, TypeScript 6, TanStack Router, Ant Design 6, Vitest, React Testing Library.

---

## Root Cause From Log

Observed request:

```text
GET /api/crawl-tasks?skip=0&limit=20 -> 500 Internal Server Error
```

Observed exception:

```text
psycopg.errors.UndefinedTable: relation "crawl_tasks" does not exist
```

Trace source:

```text
backend/app/modules/crawl_tasks/router.py:29 list_tasks
backend/app/repositories/crawl_task.py:32 get_by_owner
```

Root cause:

- The current app has `backend/app/models/crawl_task.py`, `backend/app/repositories/crawl_task.py`, and `backend/app/modules/crawl_tasks/router.py`.
- `backend/alembic/versions/` only contains `a04675645d56_initial_user_schema.py`.
- `backend/alembic/env.py` imports only `User`, so crawler models are not registered for migration metadata.
- The active PostgreSQL database has `users` but not `crawl_tasks`.

Design correction requested by user:

- Add a parent crawler module, displayed as `爬虫`.
- Put task list under that parent module, displayed as `任务列表`.
- Make `新建任务` a standalone page like the original source project, not an Ant Design modal.

## File Structure

- Create `backend/app/modules/crawler/__init__.py` for the backend parent module.
- Create `backend/app/modules/crawler/tasks/__init__.py` for the canonical task module package.
- Create `backend/app/modules/crawler/tasks/router.py` as the canonical `/api/crawler/tasks` router.
- Modify `backend/app/modules/crawl_tasks/router.py` into a compatibility `/api/crawl-tasks` router that uses the same repository/model and no longer crashes.
- Modify `backend/app/models/crawl_task.py` only if needed for SQLite test compatibility.
- Modify `backend/app/repositories/crawl_task.py` to support canonical list/create/update/delete operations.
- Modify `backend/app/main.py` to include both canonical and compatibility routers.
- Modify `backend/alembic/env.py` to import `CrawlTask`.
- Create `backend/alembic/versions/b17e4f6d9c01_add_crawl_tasks.py` to create the missing table.
- Create `backend/tests/test_crawl_tasks_api.py` to reproduce the pasted log and verify both route prefixes.
- Create `frontend/src/pages/crawler/tasks/TaskListPage.tsx` for `/crawler/tasks`.
- Create `frontend/src/pages/crawler/tasks/TaskFormPage.tsx` for `/crawler/tasks/new` and `/crawler/tasks/$id/edit`.
- Create `frontend/src/pages/crawler/tasks/TaskPages.module.less` for page-level task styles.
- Modify `frontend/src/api/crawlTask/index.ts` to use `/api/crawler/tasks`.
- Modify `frontend/src/routes/index.tsx` to add `/crawler/tasks`, `/crawler/tasks/new`, `/crawler/tasks/$id/edit`, and a legacy `/crawl-tasks` redirect.
- Modify `frontend/src/layout/Sidebar/index.tsx` to add the parent `爬虫` menu.
- Modify or remove modal usage from `frontend/src/pages/crawlTasks/CrawlTasksPage.tsx`.
- Delete `frontend/src/pages/crawlTasks/components/TaskFormModal.tsx` after the standalone form page is wired.
- Add frontend tests for route/sidebar/form behavior.

---

### Task 1: Reproduce The Backend Failure And Add The Missing Migration

**Files:**
- Create: `backend/tests/test_crawl_tasks_api.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/b17e4f6d9c01_add_crawl_tasks.py`

- [ ] **Step 1: Write the failing backend regression test**

Create `backend/tests/test_crawl_tasks_api.py`:

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
    def test_legacy_route_returns_empty_list_instead_of_500(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        response = client.get(
            "/api/crawl-tasks?skip=0&limit=20",
            headers=auth_headers(client, admin_user),
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json() == []

    def test_canonical_route_creates_and_lists_task(
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
        created = created_response.json()
        assert created["name"] == "每日媒体索引"
        assert created["owner_id"] == str(admin_user.id)
        assert created["status"] == "pending"

        list_response = client.get("/api/crawler/tasks", headers=headers)
        assert list_response.status_code == HTTPStatus.OK
        assert [item["name"] for item in list_response.json()] == ["每日媒体索引"]

    def test_legacy_route_uses_same_data_as_canonical_route(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        client.post("/api/crawler/tasks", json=task_payload(), headers=headers)

        response = client.get("/api/crawl-tasks?skip=0&limit=20", headers=headers)

        assert response.status_code == HTTPStatus.OK
        assert [item["name"] for item in response.json()] == ["每日媒体索引"]
```

- [ ] **Step 2: Run the backend test to verify the current failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: FAIL before the router/migration changes. In the running PostgreSQL app, the equivalent manual request currently fails with `relation "crawl_tasks" does not exist`.

- [ ] **Step 3: Register CrawlTask in Alembic metadata**

Modify `backend/alembic/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.models.crawl_task import CrawlTask  # noqa: F401
from backend.app.models.user import User  # noqa: F401
from shared.database.models.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Add the missing crawl_tasks migration**

Create `backend/alembic/versions/b17e4f6d9c01_add_crawl_tasks.py`:

```python
"""add_crawl_tasks

Revision ID: b17e4f6d9c01
Revises: a04675645d56
Create Date: 2026-07-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b17e4f6d9c01"
down_revision: Union[str, None] = "a04675645d56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("target_websites", sa.JSON(), nullable=False),
        sa.Column("schedule", sa.String(length=100), nullable=True),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("crawl_depth", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=True),
        sa.Column("celery_id", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_found", sa.Integer(), nullable=False),
        sa.Column("total_qualified", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_crawl_tasks_owner_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crawl_tasks")),
        sa.UniqueConstraint("task_id", name=op.f("uq_crawl_tasks_task_id")),
    )
    op.create_index(op.f("ix_crawl_tasks_owner_id"), "crawl_tasks", ["owner_id"], unique=False)
    op.create_index(op.f("ix_crawl_tasks_status"), "crawl_tasks", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_crawl_tasks_status"), table_name="crawl_tasks")
    op.drop_index(op.f("ix_crawl_tasks_owner_id"), table_name="crawl_tasks")
    op.drop_table("crawl_tasks")
```

- [ ] **Step 5: Verify migration history sees the new revision**

Run:

```bash
source .venv/bin/activate
cd backend
alembic history --verbose | grep b17e4f6d9c01
```

Expected: output includes `b17e4f6d9c01 -> add_crawl_tasks`.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add backend/tests/test_crawl_tasks_api.py backend/alembic/env.py backend/alembic/versions/b17e4f6d9c01_add_crawl_tasks.py
git commit -m "fix: add crawl tasks migration"
```

Expected: Commit succeeds.

---

### Task 2: Add Canonical Backend Parent Module And Compatibility Route

**Files:**
- Create: `backend/app/modules/crawler/__init__.py`
- Create: `backend/app/modules/crawler/tasks/__init__.py`
- Create: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/app/modules/crawl_tasks/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/repositories/crawl_task.py`

- [ ] **Step 1: Add repository methods used by both route prefixes**

Modify `backend/app/repositories/crawl_task.py`:

```python
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from backend.app.repositories.base import BaseRepository


class CrawlTaskRepository(BaseRepository):
    """Repository for CrawlTask model operations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlTask)

    def get_by_task_id(self, task_id: str) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .filter(CrawlTask.task_id == task_id)
            .first()
        )

    def get_by_owner(
        self, owner_id: uuid.UUID, *, skip: int = 0, limit: int = 20
    ) -> list[CrawlTask]:
        return (
            self.session.query(CrawlTask)
            .filter(CrawlTask.owner_id == owner_id)
            .order_by(CrawlTask.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_owner(self, owner_id: uuid.UUID) -> int:
        return (
            self.session.query(func.count(CrawlTask.id))
            .filter(CrawlTask.owner_id == owner_id)
            .scalar()
            or 0
        )

    def get_owned(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id)
            .first()
        )
```

- [ ] **Step 2: Create backend parent module packages**

Create `backend/app/modules/crawler/__init__.py`:

```python
"""Crawler parent module."""
```

Create `backend/app/modules/crawler/tasks/__init__.py`:

```python
"""Crawler task routes."""
```

- [ ] **Step 3: Create canonical crawler task router**

Create `backend/app/modules/crawler/tasks/router.py`:

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

router = APIRouter(prefix="/api/crawler/tasks", tags=["crawler-tasks"])


@router.get("", response_model=list[CrawlTaskRead])
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[CrawlTask]:
    repo = CrawlTaskRepository(db)
    return repo.get_by_owner(current_user.id, skip=skip, limit=limit)


@router.get("/stats")
def get_stats(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    repo = CrawlTaskRepository(db)
    return {"total": repo.count_by_owner(current_user.id)}


@router.get("/{task_id}", response_model=CrawlTaskRead)
def get_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> CrawlTask:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("", response_model=CrawlTaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    data: CrawlTaskCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> CrawlTask:
    task = CrawlTask(**data.model_dump(), owner_id=current_user.id)
    repo = CrawlTaskRepository(db)
    return repo.create(task)


@router.put("/{task_id}", response_model=CrawlTaskRead)
def update_task(
    task_id: uuid.UUID,
    data: CrawlTaskUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> CrawlTask:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    return repo.update(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    repo.delete(task)
```

- [ ] **Step 4: Turn the old crawl_tasks router into a compatibility alias**

Modify `backend/app/modules/crawl_tasks/router.py`:

```python
"""Compatibility routes for the old /api/crawl-tasks prefix.

New frontend code uses /api/crawler/tasks. Keep this prefix temporarily so a
stale browser tab or cached bundle cannot reproduce the pasted 500 error.
"""

from fastapi import APIRouter

from backend.app.modules.crawler.tasks.router import (
    create_task,
    delete_task,
    get_stats,
    get_task,
    list_tasks,
    update_task,
)

router = APIRouter(prefix="/api/crawl-tasks", tags=["crawl-tasks-compat"])

router.add_api_route("", list_tasks, methods=["GET"])
router.add_api_route("/stats", get_stats, methods=["GET"])
router.add_api_route("/{task_id}", get_task, methods=["GET"])
router.add_api_route("", create_task, methods=["POST"], status_code=201)
router.add_api_route("/{task_id}", update_task, methods=["PUT"])
router.add_api_route("/{task_id}", delete_task, methods=["DELETE"], status_code=204)
```

- [ ] **Step 5: Register canonical and compatibility routers**

Modify imports and router registration in `backend/app/main.py`:

```python
from backend.app.modules.crawl_tasks.router import router as crawl_tasks_compat_router
from backend.app.modules.crawler.tasks.router import router as crawler_tasks_router
```

Then make the router section include both:

```python
app.include_router(init_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(crawler_tasks_router)
app.include_router(crawl_tasks_compat_router)
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS. Both `/api/crawler/tasks` and legacy `/api/crawl-tasks` return valid responses in the test database.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git add backend/app/modules/crawler backend/app/modules/crawl_tasks/router.py backend/app/main.py backend/app/repositories/crawl_task.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat: add canonical crawler task routes"
```

Expected: Commit succeeds.

---

### Task 3: Add Parent Crawler Route And Sidebar Module

**Files:**
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Modify: `frontend/src/api/crawlTask/index.ts`
- Test: `frontend/tests/layout.ui.test.tsx`
- Test: `frontend/tests/App.test.tsx`

- [ ] **Step 1: Update frontend API prefix**

Modify `frontend/src/api/crawlTask/index.ts`:

```ts
import { request } from '@/request'
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
}): Promise<CrawlTask[]> {
  return request.get<CrawlTask[]>(BASE_URL, params)
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

- [ ] **Step 2: Update route tests**

In `frontend/tests/layout.ui.test.tsx`, assert the parent and child labels:

```tsx
expect(screen.getByText('爬虫')).toBeInTheDocument()
expect(screen.getByText('任务列表')).toBeInTheDocument()
```

In `frontend/tests/App.test.tsx`, add an authenticated route test:

```tsx
it('shows crawler task list for authenticated user', async () => {
  useAuthStore.setState({ token: 'test-token', isAuthenticated: true })

  renderApp('/crawler/tasks')

  await waitFor(() => {
    expect(screen.getByRole('heading', { name: '爬取任务' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run route tests to verify they fail**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx App.test.tsx
```

Expected: FAIL because `/crawler/tasks` and the parent menu do not exist yet.

- [ ] **Step 4: Register parent crawler routes**

Modify `frontend/src/routes/index.tsx`:

```tsx
import { createRootRoute, createRoute, createRouter, Outlet, redirect } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, theme } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { redirectIfAuthenticated, requireAuth, requireInit } from './-guards'
import LoginPage from '@/pages/login/LoginPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'
import InitPage from '@/pages/init/InitPage'
import CrawlTasksPage from '@/pages/crawler/tasks/TaskListPage'
import TaskFormPage from '@/pages/crawler/tasks/TaskFormPage'
import AppLayout from '@/layout'

const rootRoute = createRootRoute({
  component: function RootLayout() {
    const darkMode = useThemeStore((state) => state.darkMode)
    const primaryColor = useThemeStore((state) => state.primaryColor)

    return (
      <ConfigProvider
        theme={{
          algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            colorPrimary: primaryColor,
            borderRadius: 8,
          },
        }}
      >
        <AntApp>
          <Outlet />
        </AntApp>
      </ConfigProvider>
    )
  },
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  beforeLoad: redirectIfAuthenticated,
  component: LoginPage,
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
})

const initRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/init',
  component: InitPage,
})

const layoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'layout',
  beforeLoad: async () => {
    await requireInit()
    requireAuth()
  },
  component: AppLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/',
  component: DashboardPage,
})

const crawlerIndexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler',
  beforeLoad: () => {
    throw redirect({ to: '/crawler/tasks' })
  },
})

const crawlerTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks',
  component: CrawlTasksPage,
})

const crawlerTaskNewRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks/new',
  component: TaskFormPage,
})

const crawlerTaskEditRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawler/tasks/$id/edit',
  component: TaskFormPage,
})

const legacyCrawlTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/crawl-tasks',
  beforeLoad: () => {
    throw redirect({ to: '/crawler/tasks' })
  },
})

const routeTree = rootRoute.addChildren([
  initRoute,
  loginRoute,
  layoutRoute.addChildren([
    indexRoute,
    crawlerIndexRoute,
    crawlerTasksRoute,
    crawlerTaskNewRoute,
    crawlerTaskEditRoute,
    legacyCrawlTasksRoute,
  ]),
])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
})
```

- [ ] **Step 5: Add the parent sidebar module**

Modify `frontend/src/layout/Sidebar/index.tsx`:

```tsx
import { useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { DashboardOutlined, SearchOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './Sidebar.module.less'

const { Sider } = Layout

const menuItems: MenuProps['items'] = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: '仪表盘',
  },
  {
    key: 'crawler',
    icon: <SearchOutlined />,
    label: '爬虫',
    children: [
      {
        key: '/crawler/tasks',
        icon: <UnorderedListOutlined />,
        label: '任务列表',
      },
    ],
  },
]

type SideMenuProps = {
  collapsed: boolean
}

export function SideMenu({ collapsed }: SideMenuProps) {
  const navigate = useNavigate()
  const darkMode = useThemeStore((state) => state.darkMode)
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const selectedKey = pathname.startsWith('/crawler/tasks') ? '/crawler/tasks' : pathname
  const selectedKeys = useMemo(() => [selectedKey === '/' ? '/' : selectedKey], [selectedKey])
  const openKeys = useMemo(() => (pathname.startsWith('/crawler') ? ['crawler'] : []), [pathname])

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const nextPath = String(key)
    if (nextPath.startsWith('/') && nextPath !== pathname) {
      void navigate({ to: nextPath })
    }
  }

  return (
    <Sider
      collapsed={collapsed}
      width={232}
      collapsedWidth={80}
      collapsible={false}
      className={[
        styles.sider,
        darkMode ? styles.dark : '',
        collapsed ? styles.collapsed : '',
      ].filter(Boolean).join(' ')}
    >
      <div className={styles.logo}>
        <span className={styles.logoMark}>MF</span>
        {!collapsed && <span className={styles.logoText}>Media Forge</span>}
      </div>

      <div className={styles.menuWrapper}>
        <Menu
          className={styles.menu}
          mode="inline"
          theme={darkMode ? 'dark' : 'light'}
          inlineCollapsed={collapsed}
          selectedKeys={selectedKeys}
          defaultOpenKeys={openKeys}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </div>
    </Sider>
  )
}
```

- [ ] **Step 6: Run route tests**

Run:

```bash
cd frontend && npm test -- layout.ui.test.tsx App.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
git add frontend/src/api/crawlTask/index.ts frontend/src/routes/index.tsx frontend/src/layout/Sidebar/index.tsx frontend/tests/layout.ui.test.tsx frontend/tests/App.test.tsx
git commit -m "feat: add crawler parent module routes"
```

Expected: Commit succeeds.

---

### Task 4: Replace New Task Modal With Standalone Page

**Files:**
- Create: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Create: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Create: `frontend/src/pages/crawler/tasks/TaskPages.module.less`
- Delete: `frontend/src/pages/crawlTasks/components/TaskFormModal.tsx`
- Modify: `frontend/src/pages/crawlTasks/CrawlTasksPage.tsx`
- Test: `frontend/tests/crawler-task-pages.ui.test.tsx`

- [ ] **Step 1: Write standalone page tests**

Create `frontend/tests/crawler-task-pages.ui.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TaskFormPage from '../src/pages/crawler/tasks/TaskFormPage'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'

const navigateMock = vi.fn()

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useParams: () => ({}),
  }
})

vi.mock('../src/api/crawlTask', () => ({
  createCrawlTask: vi.fn().mockResolvedValue({ id: 'task-1' }),
  deleteCrawlTask: vi.fn().mockResolvedValue(undefined),
  getCrawlTask: vi.fn(),
  getCrawlTasks: vi.fn().mockResolvedValue([
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
      created_at: '2026-07-01T00:00:00Z',
      updated_at: null,
    },
  ]),
  updateCrawlTask: vi.fn().mockResolvedValue({ id: 'task-1' }),
}))

function renderWithApp(ui: React.ReactElement) {
  return render(<AntApp>{ui}</AntApp>)
}

describe('crawler task standalone pages', () => {
  beforeEach(() => {
    navigateMock.mockReset()
  })

  it('renders task list and navigates to the standalone new page', async () => {
    renderWithApp(<TaskListPage />)

    expect(await screen.findByRole('heading', { name: '爬取任务' })).toBeInTheDocument()
    expect(await screen.findByText('每日媒体索引')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '新建任务' }))

    expect(navigateMock).toHaveBeenCalledWith({ to: '/crawler/tasks/new' })
  })

  it('renders the original-style standalone task form', async () => {
    renderWithApp(<TaskFormPage />)

    expect(screen.getByRole('heading', { name: '新建爬取任务' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByLabelText('任务名称')).toBeInTheDocument()
    expect(screen.getByLabelText('关键词')).toBeInTheDocument()
    expect(screen.getByLabelText('目标网站')).toBeInTheDocument()
  })

  it('submits a new task from the standalone form', async () => {
    const api = await import('../src/api/crawlTask')
    const createCrawlTask = vi.mocked(api.createCrawlTask)

    renderWithApp(<TaskFormPage />)

    await userEvent.type(screen.getByLabelText('任务名称'), '每日媒体索引')
    await userEvent.type(screen.getByLabelText('任务描述'), '跟踪测试资源')
    await userEvent.type(screen.getByLabelText('关键词'), 'media{enter}forge{enter}')
    await userEvent.type(screen.getByLabelText('目标网站'), 'https://example.com{enter}')
    await userEvent.click(screen.getByRole('button', { name: '创建任务' }))

    await waitFor(() => {
      expect(createCrawlTask).toHaveBeenCalledWith({
        name: '每日媒体索引',
        description: '跟踪测试资源',
        keywords: ['media', 'forge'],
        target_websites: ['https://example.com'],
        schedule: undefined,
        max_pages: 100,
        crawl_depth: 3,
      })
      expect(navigateMock).toHaveBeenCalledWith({ to: '/crawler/tasks' })
    })
  })
})
```

- [ ] **Step 2: Run standalone page tests to verify they fail**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx
```

Expected: FAIL because `frontend/src/pages/crawler/tasks/TaskListPage.tsx` and `TaskFormPage.tsx` do not exist yet.

- [ ] **Step 3: Add standalone page styles**

Create `frontend/src/pages/crawler/tasks/TaskPages.module.less`:

```less
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.title {
  margin: 0;
  color: #111827;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
}

.subtitle {
  margin: 6px 0 0;
  color: rgba(15, 23, 42, 0.64);
  font-size: 14px;
}

.panel {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: #fff;
}

.formPanel {
  padding: 18px;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 24px;
}

@media (max-width: 768px) {
  .header {
    align-items: stretch;
    flex-direction: column;
  }
}
```

- [ ] **Step 4: Create task list page that links to standalone new/edit routes**

Create `frontend/src/pages/crawler/tasks/TaskListPage.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Modal, message } from 'antd'
import {
  deleteCrawlTask,
  getCrawlTasks,
} from '@/api/crawlTask'
import type { CrawlTask } from '@/api/crawlTask/types'
import TaskListTable from '@/pages/crawlTasks/components/TaskListTable'
import styles from './TaskPages.module.less'

const PAGE_SIZE = 20

function TaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<CrawlTask[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [current, setCurrent] = useState(1)

  const fetchTasks = useCallback(async (page: number) => {
    setLoading(true)
    try {
      const skip = (page - 1) * PAGE_SIZE
      const data = await getCrawlTasks({ skip, limit: PAGE_SIZE })
      setTasks(data)
      setTotal(data.length < PAGE_SIZE ? skip + data.length : skip + PAGE_SIZE + 1)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchTasks(1)
  }, [fetchTasks])

  const handlePageChange = useCallback(
    (page: number) => {
      setCurrent(page)
      void fetchTasks(page)
    },
    [fetchTasks],
  )

  const handleDelete = useCallback(
    (task: CrawlTask) => {
      Modal.confirm({
        title: '确认删除',
        content: `确定删除任务「${task.name}」？此操作不可撤销。`,
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: async () => {
          await deleteCrawlTask(task.id)
          message.success('删除成功')
          void fetchTasks(current)
        },
      })
    },
    [current, fetchTasks],
  )

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>爬取任务</h1>
          <p className={styles.subtitle}>管理媒体资源爬取任务</p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate({ to: '/crawler/tasks/new' })}
        >
          新建任务
        </Button>
      </div>

      <section className={styles.panel}>
        <TaskListTable
          tasks={tasks}
          loading={loading}
          total={total}
          current={current}
          pageSize={PAGE_SIZE}
          onPageChange={handlePageChange}
          onEdit={(task) => navigate({ to: '/crawler/tasks/$id/edit', params: { id: task.id } })}
          onDelete={handleDelete}
          onSearch={() => { void fetchTasks(1) }}
        />
      </section>
    </div>
  )
}

export default TaskListPage
```

- [ ] **Step 5: Create standalone task form page**

Create `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { Button, Form, Input, InputNumber, Select, message } from 'antd'
import {
  createCrawlTask,
  getCrawlTask,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTaskCreateParams } from '@/api/crawlTask/types'
import styles from './TaskPages.module.less'

const SCHEDULE_OPTIONS = [
  { value: 'once', label: '单次执行' },
  { value: 'hourly', label: '每小时' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
]

function TaskFormPage() {
  const navigate = useNavigate()
  const params = useParams({ strict: false }) as { id?: string }
  const taskId = params.id
  const isEdit = Boolean(taskId)
  const [form] = Form.useForm<CrawlTaskCreateParams>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const title = useMemo(() => (isEdit ? '编辑爬取任务' : '新建爬取任务'), [isEdit])

  useEffect(() => {
    if (!taskId) return

    setLoading(true)
    getCrawlTask(taskId)
      .then((task) => {
        form.setFieldsValue({
          name: task.name,
          description: task.description ?? undefined,
          keywords: task.keywords,
          target_websites: task.target_websites,
          schedule: task.schedule ?? undefined,
          max_pages: task.max_pages,
          crawl_depth: task.crawl_depth,
        })
      })
      .catch(() => {
        message.error('任务详情加载失败')
      })
      .finally(() => setLoading(false))
  }, [form, taskId])

  const handleSubmit = async (values: CrawlTaskCreateParams) => {
    setSubmitting(true)
    try {
      const payload: CrawlTaskCreateParams = {
        name: values.name,
        description: values.description,
        keywords: values.keywords,
        target_websites: values.target_websites,
        schedule: values.schedule,
        max_pages: values.max_pages ?? 100,
        crawl_depth: values.crawl_depth ?? 3,
      }

      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('更新成功')
      } else {
        await createCrawlTask(payload)
        message.success('创建成功')
      }
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.subtitle}>使用独立页面配置任务名称、关键词、目标网站和执行限制。</p>
        </div>
      </div>

      <section className={`${styles.panel} ${styles.formPanel}`}>
        <Form<CrawlTaskCreateParams>
          form={form}
          layout="vertical"
          disabled={loading}
          initialValues={{ max_pages: 100, crawl_depth: 3 }}
          onFinish={(values) => { void handleSubmit(values) }}
        >
          <Form.Item
            name="name"
            label="任务名称"
            rules={[
              { required: true, message: '请输入任务名称' },
              { max: 200, message: '名称最多 200 个字符' },
            ]}
          >
            <Input placeholder="输入任务名称" />
          </Form.Item>

          <Form.Item name="description" label="任务描述">
            <Input.TextArea rows={3} placeholder="描述任务目的" />
          </Form.Item>

          <Form.Item
            name="keywords"
            label="关键词"
            rules={[{ required: true, message: '请至少输入一个关键词' }]}
          >
            <Select mode="tags" placeholder="输入关键词后按回车" />
          </Form.Item>

          <Form.Item
            name="target_websites"
            label="目标网站"
            rules={[{ required: true, message: '请至少输入一个目标网站' }]}
          >
            <Select mode="tags" placeholder="输入网站 URL 后按回车" />
          </Form.Item>

          <Form.Item name="schedule" label="执行计划">
            <Select allowClear placeholder="选择执行频率" options={SCHEDULE_OPTIONS} />
          </Form.Item>

          <Form.Item name="max_pages" label="最大页数">
            <InputNumber min={1} max={10000} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="crawl_depth" label="爬取深度">
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>

          <div className={styles.actions}>
            <Button type="primary" htmlType="submit" loading={submitting}>
              {isEdit ? '更新任务' : '创建任务'}
            </Button>
            <Button onClick={() => navigate({ to: '/crawler/tasks' })}>
              取消
            </Button>
          </div>
        </Form>
      </section>
    </div>
  )
}

export default TaskFormPage
```

- [ ] **Step 6: Keep old page as a re-export during transition**

Modify `frontend/src/pages/crawlTasks/CrawlTasksPage.tsx`:

```tsx
export { default } from '@/pages/crawler/tasks/TaskListPage'
```

- [ ] **Step 7: Delete the modal form**

Delete `frontend/src/pages/crawlTasks/components/TaskFormModal.tsx`.

- [ ] **Step 8: Run standalone page tests**

Run:

```bash
cd frontend && npm test -- crawler-task-pages.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

Run:

```bash
git add frontend/src/pages/crawler/tasks frontend/src/pages/crawlTasks/CrawlTasksPage.tsx frontend/tests/crawler-task-pages.ui.test.tsx
git rm frontend/src/pages/crawlTasks/components/TaskFormModal.tsx
git commit -m "feat: use standalone crawler task pages"
```

Expected: Commit succeeds.

---

### Task 5: Verify Against The Pasted Log In The Real Dev Database

**Files:**
- Verify only.

- [ ] **Step 1: Apply migrations to the local development database**

Run:

```bash
source .venv/bin/activate
cd backend
alembic upgrade head
```

Expected: migration applies and creates `crawl_tasks`.

- [ ] **Step 2: Restart backend**

Run:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Expected: backend starts without import errors.

- [ ] **Step 3: Create a local auth token for manual API checks**

In another terminal, run:

```bash
TOKEN=$(curl -s 'http://127.0.0.1:8000/api/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')
echo "${TOKEN:0:12}"
```

Expected: prints the first 12 characters of a JWT.

- [ ] **Step 4: Verify old API no longer produces the pasted 500**

Run:

```bash
curl -i 'http://127.0.0.1:8000/api/crawl-tasks?skip=0&limit=20' \
  -H "Authorization: Bearer ${TOKEN}"
```

Expected: `HTTP/1.1 200 OK` and JSON array response. The log must not contain `relation "crawl_tasks" does not exist`.

- [ ] **Step 5: Verify canonical API works**

Run:

```bash
curl -i 'http://127.0.0.1:8000/api/crawler/tasks?skip=0&limit=20' \
  -H "Authorization: Bearer ${TOKEN}"
```

Expected: `HTTP/1.1 200 OK` and JSON array response.

- [ ] **Step 6: Run backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: PASS.

- [ ] **Step 7: Run frontend tests**

Run:

```bash
cd frontend && npm test
```

Expected: PASS.

- [ ] **Step 8: Run frontend lint and build**

Run:

```bash
cd frontend && npm run lint && npm run build
```

Expected: PASS with no lint errors and successful production build.

---

## Self-Review

**Spec coverage:** The plan fixes the pasted `crawl_tasks` missing-table failure, registers the crawler model in Alembic, creates the missing migration, adds a canonical backend parent module at `/api/crawler/tasks`, preserves the old `/api/crawl-tasks` route so stale calls stop crashing, adds a frontend parent `爬虫` module, routes task list to `/crawler/tasks`, and replaces the modal new-task flow with a standalone `/crawler/tasks/new` page.

**Placeholder scan:** No incomplete markers remain. The word `placeholder` appears only as a real Ant Design input prop inside code examples.

**Type consistency:** Backend route names, frontend route paths, API prefix, `CrawlTaskCreateParams`, and `CrawlTaskRead` remain aligned with the current generic crawl task model already present in the repository.
