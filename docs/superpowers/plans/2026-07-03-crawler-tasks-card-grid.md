# Crawler Tasks Card Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crawler task table with a four-column card grid that loads and displays all matching tasks without pagination.

**Architecture:** The backend task list endpoint will allow an unpaginated read when the frontend omits `skip` and `limit`, while still returning the existing `{ rows, total }` envelope. Task rows include latest run metadata, and `/api/crawler/tasks/stats` returns total/running/waiting counts. The frontend keeps the existing search condition store, removes pagination state entirely, renders all rows in a responsive card grid, and uses dropdown-style controls for crawl mode and delete mode.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pytest, React 19, TypeScript 6, Ant Design 6, Zustand 5, Vitest 3, React Testing Library.

---

## File Structure

- Modify `backend/app/repositories/crawl_task.py`: support unpaginated owner query, add latest-run lookup, and add summary stats.
- Modify `backend/app/schemas/crawl_task.py`: add `last_run_at`, `last_run_status`, and expanded stats fields.
- Modify `backend/app/modules/crawler/tasks/router.py`: make `skip`/`limit` optional, return all matching rows when omitted, include latest run metadata, and expand `/stats`.
- Modify `backend/tests/test_crawl_tasks_api.py`: cover unpaginated list behavior, task stats, and latest run metadata.
- Modify `frontend/src/api/crawlTask/types.ts`: add `last_run_at`, `last_run_status`, and stats fields.
- Modify `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts`: keep only keyword state; remove current-page concepts.
- Create `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`: card grid replacement for the table, without pagination.
- Delete `frontend/src/pages/crawler/tasks/components/TaskListTable.tsx`: remove the old table implementation.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`: fetch stats, fetch all matching tasks, render summary counters, card grid, crawl dropdown, and delete-mode select.
- Modify `frontend/src/pages/crawler/tasks/TaskPages.module.less`: add stat bar, grid, card, metadata, action, and delete modal styles.
- Modify `frontend/tests/task-list-query-state.ui.test.tsx`: assert search condition remains and the frontend does not send pagination params.
- Modify `frontend/tests/crawler-run-controls.ui.test.tsx`: assert run mode dropdown behavior.
- Create `frontend/tests/crawler-task-card-grid.ui.test.tsx`: assert card layout content, stats, no table, no pagination, and delete-mode select behavior.

---

### Task 1: Backend All-Task List Metadata And Stats

**Files:**
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/tests/test_crawl_tasks_api.py`

- [ ] **Step 1: Write failing backend API tests**

Append these imports to `backend/tests/test_crawl_tasks_api.py`:

```python
from datetime import datetime

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.tests.conftest import TestingSessionLocal
```

Append these tests inside `class TestCrawlTasksApi`:

```python
    def test_list_tasks_without_pagination_returns_all_matching_rows(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        session.add_all(
            [
                CrawlTask(name=f"任务{i:02d}", storage_location=f"P{i:02d}"[:10], owner_id=admin_user.id)
                for i in range(25)
            ]
        )
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks", headers=headers)

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body["total"] == 25
        assert len(body["rows"]) == 25

    def test_stats_returns_total_running_and_waiting_counts(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        session.add_all(
            [
                CrawlTask(name="待处理任务", storage_location="PENDING", owner_id=admin_user.id, status="pending"),
                CrawlTask(name="运行中任务", storage_location="RUNNING", owner_id=admin_user.id, status="running"),
                CrawlTask(name="成功任务", storage_location="SUCCESS", owner_id=admin_user.id, status="success"),
            ]
        )
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks/stats", headers=headers)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["data"] == {
            "total": 3,
            "running": 1,
            "waiting": 1,
        }

    def test_list_tasks_returns_latest_run_metadata(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        session = TestingSessionLocal()
        task = CrawlTask(name="有码任务", storage_location="AV", owner_id=admin_user.id, status="success")
        session.add(task)
        session.flush()
        session.add_all(
            [
                CrawlRun(
                    task_id=task.id,
                    task_name=task.name,
                    status="failed",
                    crawl_mode="incremental",
                    created_at=datetime(2026, 7, 2, 8, 0, 0),
                ),
                CrawlRun(
                    task_id=task.id,
                    task_name=task.name,
                    status="completed",
                    crawl_mode="full",
                    created_at=datetime(2026, 7, 3, 8, 0, 0),
                ),
            ]
        )
        session.commit()
        session.close()

        response = client.get("/api/crawler/tasks", headers=headers)

        assert response.status_code == HTTPStatus.OK
        row = response.json()["rows"][0]
        assert row["name"] == "有码任务"
        assert row["last_run_status"] == "completed"
        assert row["last_run_at"].startswith("2026-07-03T08:00:00")
```

- [ ] **Step 2: Run backend tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_list_tasks_without_pagination_returns_all_matching_rows backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_stats_returns_total_running_and_waiting_counts backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_list_tasks_returns_latest_run_metadata -v
```

Expected: FAIL because the default list is limited, `/stats` returns only `total`, and list rows do not include latest run fields.

- [ ] **Step 3: Add repository helpers**

Modify imports in `backend/app/repositories/crawl_task.py`:

```python
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.enums import TaskStatus
```

Change the `get_by_owner` signature and body:

```python
    def get_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        skip: int | None = None,
        limit: int | None = None,
        keyword: str | None = None,
    ) -> list[CrawlTask]:
        query = self._owner_query(owner_id, keyword).order_by(CrawlTask.created_at.desc())
        if skip is not None:
          query = query.offset(skip)
        if limit is not None:
          query = query.limit(limit)
        return query.all()
```

Use four spaces in the actual file:

```python
        if skip is not None:
            query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
```

Add these methods after `count_by_owner`:

```python
    def get_summary_stats(self, owner_id: uuid.UUID) -> dict[str, int]:
        rows = (
            self.session.query(CrawlTask.status, func.count(CrawlTask.id))
            .filter(CrawlTask.owner_id == owner_id)
            .group_by(CrawlTask.status)
            .all()
        )
        counts = {str(status): int(count) for status, count in rows}
        return {
            "total": sum(counts.values()),
            "running": counts.get(TaskStatus.RUNNING.value, 0),
            "waiting": counts.get(TaskStatus.PENDING.value, 0),
        }

    def get_latest_runs_by_task_ids(self, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, CrawlRun]:
        if not task_ids:
            return {}

        rows = (
            self.session.query(CrawlRun)
            .filter(CrawlRun.task_id.in_(task_ids))
            .order_by(CrawlRun.task_id.asc(), CrawlRun.created_at.desc())
            .all()
        )
        latest: dict[uuid.UUID, CrawlRun] = {}
        for row in rows:
            if row.task_id is not None and row.task_id not in latest:
                latest[row.task_id] = row
        return latest

    def get_latest_run(self, task_id: uuid.UUID) -> CrawlRun | None:
        return (
            self.session.query(CrawlRun)
            .filter(CrawlRun.task_id == task_id)
            .order_by(CrawlRun.created_at.desc())
            .first()
        )

    def get_latest_runs(
        self,
        owner_id: uuid.UUID,
        *,
        task_id: uuid.UUID,
        limit: int = 10,
    ) -> list[CrawlRun]:
        return (
            self.session.query(CrawlRun)
            .join(CrawlTask, CrawlTask.id == CrawlRun.task_id)
            .filter(CrawlTask.owner_id == owner_id, CrawlRun.task_id == task_id)
            .order_by(CrawlRun.created_at.desc())
            .limit(limit)
            .all()
        )
```

- [ ] **Step 4: Update task schemas**

Modify `CrawlTaskRead` in `backend/app/schemas/crawl_task.py` by adding fields after `updated_at`:

```python
    last_run_at: datetime | None = None
    last_run_status: str | None = None
```

Add this schema after `ExtractNameResponse`:

```python
class CrawlTaskStats(BaseModel):
    total: int
    running: int
    waiting: int
```

- [ ] **Step 5: Serialize latest run metadata and expanded stats**

Modify imports in `backend/app/modules/crawler/tasks/router.py`:

```python
from backend.app.models.crawl_run import CrawlRun
```

Change the schema import block to include `CrawlTaskStats`:

```python
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskRead,
    CrawlTaskStats,
    CrawlTaskUpdate,
    ExtractNameRequest,
)
```

Replace `_serialize` with:

```python
def _serialize(task, latest_run: CrawlRun | None = None) -> CrawlTaskRead:
    data = CrawlTaskRead.model_validate(task)
    data._id = data.id
    if latest_run is not None:
        data.last_run_at = latest_run.created_at
        data.last_run_status = latest_run.status
    return data
```

Change list query parameters:

```python
    skip: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=1000),
```

Replace `list_tasks` body:

```python
    repo = CrawlTaskRepository(db)
    rows = repo.get_by_owner(current_user.id, skip=skip, limit=limit, keyword=keyword)
    total = repo.count_by_owner(current_user.id, keyword=keyword)
    latest_runs = repo.get_latest_runs_by_task_ids([row.id for row in rows])
    return paginated(
        rows=[
            _serialize(row, latest_runs.get(row.id)).model_dump(mode="json")
            for row in rows
        ],
        total=total,
    )
```

Replace `get_stats` body:

```python
    repo = CrawlTaskRepository(db)
    return success(data=CrawlTaskStats(**repo.get_summary_stats(current_user.id)).model_dump())
```

- [ ] **Step 6: Run backend tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/repositories/crawl_task.py backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat: return all crawler tasks with stats"
```

---

### Task 2: Frontend Types And Query State

**Files:**
- Modify: `frontend/src/api/crawlTask/types.ts`
- Modify: `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts`
- Modify: `frontend/tests/task-list-query-state.ui.test.tsx`

- [ ] **Step 1: Write failing query-state expectations**

Modify the mocked response in `frontend/tests/task-list-query-state.ui.test.tsx`:

```ts
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [],
      total: 0,
      page: 1,
      page_size: undefined,
    })
```

Modify the `getCrawlTasks` assertion:

```ts
      expect(getCrawlTasks).toHaveBeenLastCalledWith({
        keyword: '每日',
      })
```

Add this assertion at the end of `keeps the search condition after switching away and back`:

```ts
    expect(screen.queryByText(/条\/页/)).not.toBeInTheDocument()
```

- [ ] **Step 2: Run the query state test and verify it fails**

Run:

```bash
cd frontend
npm test -- task-list-query-state.ui.test.tsx
```

Expected: FAIL because the page still sends `skip` and `limit`.

- [ ] **Step 3: Update frontend API types**

Modify `frontend/src/api/crawlTask/types.ts`.

Add fields to `CrawlTask` after `updated_at`:

```ts
  last_run_at: string | null
  last_run_status: string | null
```

Replace `CrawlTaskStats`:

```ts
export interface CrawlTaskStats {
  total: number
  running: number
  waiting: number
}
```

- [ ] **Step 4: Keep only keyword in task list query store**

Replace `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts` with:

```ts
import { create } from 'zustand'

type TaskListQueryState = {
  keyword: string
  setKeyword: (keyword: string) => void
  reset: () => void
}

export const useTaskListQueryStore = create<TaskListQueryState>()((set) => ({
  keyword: '',
  setKeyword: (keyword) => set({ keyword }),
  reset: () => set({ keyword: '' }),
}))
```

- [ ] **Step 5: Run the query state test and verify expected remaining failure**

Run:

```bash
cd frontend
npm test -- task-list-query-state.ui.test.tsx
```

Expected: FAIL only because `TaskListPage` still renders the table and still wires pagination state.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/crawlTask/types.ts frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts frontend/tests/task-list-query-state.ui.test.tsx
git commit -m "feat: simplify task list query state"
```

---

### Task 3: Task Card Grid Component

**Files:**
- Create: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Delete: `frontend/src/pages/crawler/tasks/components/TaskListTable.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskPages.module.less`
- Create: `frontend/tests/crawler-task-card-grid.ui.test.tsx`

- [ ] **Step 1: Write failing card grid UI tests**

Create `frontend/tests/crawler-task-card-grid.ui.test.tsx`:

```tsx
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { deleteCrawlTask, getCrawlTaskStats, getCrawlTasks, updateCrawlTask } from '../src/api/crawlTask'
import { runCrawlTask } from '../src/api/crawlerRun'
import { useTaskListQueryStore } from '../src/pages/crawler/tasks/useTaskListQueryStore'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getCrawlTaskStats: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('../src/api/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
}))

const taskRows = [
  {
    id: 'task-1',
    name: 'JavDB VR 女优列表',
    storage_location: 'VR',
    urls: [
      {
        id: 'url-1',
        position: 0,
        url: 'https://javdb.com/actors/vr',
        url_type: 'actors',
        has_magnet: true,
        has_chinese_sub: false,
        sort_type: 0,
        source: 'javdb',
        final_url: 'https://javdb.com/actors/vr?page=1',
        url_name: 'VR 女优',
      },
    ],
    is_skip: false,
    status: 'running',
    task_id: null,
    error_message: null,
    total_found: 12,
    total_qualified: 8,
    owner_id: 'user-1',
    created_at: '2026-07-03T00:00:00',
    updated_at: null,
    last_run_at: '2026-07-03T08:00:00',
    last_run_status: 'completed',
  },
]

function renderPage() {
  const rootRoute = createRootRoute({ component: () => <TaskListPage /> })
  const taskEditRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/$id/edit',
    component: () => <div>edit page</div>,
  })
  const taskNewRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => <div>new page</div>,
  })
  const runsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/runs',
    component: () => <div>runs page</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([taskEditRoute, taskNewRoute, runsRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })

  return render(<RouterProvider router={router} />)
}

describe('crawler task card grid', () => {
  beforeEach(() => {
    useTaskListQueryStore.getState().reset()
    vi.mocked(getCrawlTaskStats).mockResolvedValue({ total: 3, running: 1, waiting: 2 })
    vi.mocked(getCrawlTasks).mockResolvedValue({ rows: taskRows, total: 1 })
    vi.mocked(updateCrawlTask).mockResolvedValue(taskRows[0])
    vi.mocked(deleteCrawlTask).mockResolvedValue({
      deleted_task: true,
      deleted_runs: 0,
      deleted_detail_tasks: 0,
      updated_movies: 0,
      deleted_movies: 0,
      deleted_magnets: 0,
      cloud_delete: 'not_requested',
    })
    vi.mocked(runCrawlTask).mockResolvedValue({ id: 'run-1' } as never)
  })

  it('renders task stats and card content without the old table or pagination', async () => {
    renderPage()

    expect(await screen.findByText('总数')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('爬取中')).toBeInTheDocument()
    expect(screen.getByText('等待中')).toBeInTheDocument()
    expect(await screen.findByText('JavDB VR 女优列表')).toBeInTheDocument()
    expect(screen.getByText('VR')).toBeInTheDocument()
    expect(screen.getByText('VR 女优')).toBeInTheDocument()
    expect(screen.getByText(/2026/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: /pagination/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/条\/页/)).not.toBeInTheDocument()
  })

  it('requests all tasks without skip and limit', async () => {
    renderPage()

    await waitFor(() => {
      expect(getCrawlTasks).toHaveBeenLastCalledWith({
        keyword: undefined,
      })
    })
  })

  it('uses a run mode dropdown for incremental and full crawl actions', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '爬取' }))
    await userEvent.click(await screen.findByText('全量爬取'))

    await waitFor(() => {
      expect(runCrawlTask).toHaveBeenCalledWith('task-1', 'full')
    })
  })

  it('uses a delete mode select in the confirmation dialog', async () => {
    renderPage()

    await userEvent.click(await screen.findByLabelText('删除 JavDB VR 女优列表'))
    await userEvent.click(await screen.findByLabelText('删除模式'))
    await userEvent.click(await screen.findByText('删除任务和关联影片'))
    await userEvent.click(screen.getByRole('button', { name: '删除' }))

    await waitFor(() => {
      expect(deleteCrawlTask).toHaveBeenCalledWith('task-1', 'task_and_movies')
    })
  })
})
```

- [ ] **Step 2: Run the card grid test and verify it fails**

Run:

```bash
cd frontend
npm test -- crawler-task-card-grid.ui.test.tsx
```

Expected: FAIL because `getCrawlTaskStats` is not called, the table still exists, and the card controls do not exist.

- [ ] **Step 3: Create the card grid component**

Create `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`:

```tsx
import {
  DeleteOutlined,
  EditOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, Empty, Input, Space, Spin, Switch, Tag, Tooltip, Typography } from 'antd'
import type { MenuProps } from 'antd'
import type { CrawlTask } from '@/api/crawlTask/types'
import type { CrawlMode } from '@/api/crawlerRun/types'
import styles from '../TaskPages.module.less'

type TaskListCardsProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  keyword: string
  onKeywordChange: (keyword: string) => void
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onSearch: (keyword: string) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
}

const taskStatusLabels: Record<string, { text: string; color: string }> = {
  pending: { text: '等待中', color: 'default' },
  running: { text: '爬取中', color: 'processing' },
  success: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
}

const runStatusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
}

function formatDateTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function getUrlNames(task: CrawlTask) {
  return task.urls
    .map((url) => url.url_name?.trim())
    .filter((name): name is string => Boolean(name))
}

function statusTag(status: string) {
  const statusConfig = taskStatusLabels[status] ?? { text: status, color: 'default' }
  return <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
}

function runStatusTag(status: string | null) {
  if (!status) return <Typography.Text type="secondary">-</Typography.Text>
  const statusConfig = runStatusLabels[status] ?? { text: status, color: 'default' }
  return <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
}

function TaskCard({
  task,
  onEdit,
  onDelete,
  onToggleSkip,
  onRun,
}: {
  task: CrawlTask
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
}) {
  const urlNames = getUrlNames(task)
  const runItems: MenuProps['items'] = [
    { key: 'incremental', label: '增量爬取', icon: <PlayCircleOutlined /> },
    { key: 'full', label: '全量爬取', icon: <PlayCircleOutlined /> },
  ]

  return (
    <article className={task.is_skip ? `${styles.taskCard} ${styles.taskCardDisabled}` : styles.taskCard}>
      <div className={styles.taskCardHead}>
        <Tooltip title={task.name}>
          <Typography.Text strong className={styles.taskCardTitle}>
            {task.name}
          </Typography.Text>
        </Tooltip>
        {statusTag(task.status)}
      </div>

      <div className={styles.taskCardBody}>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>网盘路径</span>
          <Typography.Text className={styles.taskMetaValue}>{task.storage_location || '-'}</Typography.Text>
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>URL 名称</span>
          <div className={styles.urlNameList}>
            {urlNames.length > 0
              ? urlNames.map((name, index) => <Tag key={`${name}-${index}`}>{name}</Tag>)
              : <Typography.Text type="secondary">-</Typography.Text>}
          </div>
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>最后爬取时间</span>
          <Typography.Text className={styles.taskMetaValue}>{formatDateTime(task.last_run_at)}</Typography.Text>
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>状态</span>
          <Space size={8}>
            <Switch
              checked={!task.is_skip}
              onChange={() => onToggleSkip(task)}
              checkedChildren="启用"
              unCheckedChildren="禁用"
              size="small"
            />
            {runStatusTag(task.last_run_status)}
          </Space>
        </div>
      </div>

      <div className={styles.taskCardFooter}>
        <Dropdown
          menu={{
            items: runItems,
            onClick: ({ key }) => onRun(task, key as CrawlMode),
          }}
          trigger={['click']}
          disabled={task.is_skip}
        >
          <Button type="primary" size="small" icon={<PlayCircleOutlined />} disabled={task.is_skip}>
            爬取
          </Button>
        </Dropdown>
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
      </div>
    </article>
  )
}

function TaskListCards({
  tasks,
  loading,
  total,
  keyword,
  onKeywordChange,
  onEdit,
  onDelete,
  onToggleSkip,
  onSearch,
  onRun,
}: TaskListCardsProps) {
  return (
    <div className={styles.taskListShell}>
      <div className={styles.taskListToolbar}>
        <Input.Search
          placeholder="搜索任务名称"
          allowClear
          enterButton={<SearchOutlined />}
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          onSearch={onSearch}
          className={styles.taskSearch}
        />
        <Typography.Text type="secondary">共 {total} 条</Typography.Text>
      </div>

      <Spin spinning={loading}>
        {tasks.length > 0 ? (
          <div className={styles.taskGrid}>
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onEdit={onEdit}
                onDelete={onDelete}
                onToggleSkip={onToggleSkip}
                onRun={onRun}
              />
            ))}
          </div>
        ) : (
          <Empty description="暂无任务" className={styles.emptyState} />
        )}
      </Spin>
    </div>
  )
}

export default TaskListCards
```

- [ ] **Step 4: Delete the old table component**

Delete `frontend/src/pages/crawler/tasks/components/TaskListTable.tsx`.

- [ ] **Step 5: Add card grid styles**

Append to `frontend/src/pages/crawler/tasks/TaskPages.module.less`:

```less
.statsBar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.statCard {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 72px;
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: var(--app-surface-color);
}

.statLabel {
  color: var(--app-muted-color);
  font-size: 13px;
}

.statValue {
  color: var(--app-text-color);
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
}

.taskListShell {
  padding: 16px;
}

.taskListToolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.taskSearch {
  max-width: 340px;
}

.taskGrid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.taskCard {
  display: flex;
  flex-direction: column;
  min-height: 260px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  background: var(--app-surface-color);
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;

  &:hover {
    border-color: rgba(0, 106, 255, 0.42);
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
    transform: translateY(-1px);
  }
}

.taskCardDisabled {
  opacity: 0.68;
}

.taskCardHead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  min-height: 54px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.taskCardTitle {
  min-width: 0;
  overflow: hidden;
  font-size: 15px;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.taskCardBody {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
}

.taskMetaRow {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.taskMetaLabel {
  color: var(--app-muted-color);
  font-size: 12px;
  line-height: 22px;
  white-space: nowrap;
}

.taskMetaValue {
  min-width: 0;
  overflow: hidden;
  color: var(--app-text-color);
  font-size: 13px;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.urlNameList {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.taskCardFooter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px 14px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
}

.emptyState {
  padding: 42px 0;
}

@media (max-width: 1400px) {
  .taskGrid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .taskGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .statsBar {
    grid-template-columns: 1fr;
  }

  .taskListToolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .taskSearch {
    width: 100%;
    max-width: none;
  }

  .taskGrid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: Run card grid test and verify expected remaining failure**

Run:

```bash
cd frontend
npm test -- crawler-task-card-grid.ui.test.tsx
```

Expected: FAIL only because `TaskListPage` still imports the old table and does not fetch stats.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/components/TaskListTable.tsx frontend/src/pages/crawler/tasks/TaskPages.module.less frontend/tests/crawler-task-card-grid.ui.test.tsx
git commit -m "feat: add crawler task card grid"
```

---

### Task 4: Task List Page Wiring And Dropdown Delete Mode

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/tests/crawler-run-controls.ui.test.tsx`
- Modify: `frontend/tests/task-list-query-state.ui.test.tsx`
- Modify: `frontend/tests/crawler-task-card-grid.ui.test.tsx`

- [ ] **Step 1: Update run-control test for dropdown behavior**

Replace `frontend/tests/crawler-run-controls.ui.test.tsx` with:

```tsx
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { getCrawlTaskStats, getCrawlTasks } from '../src/api/crawlTask'
import { runCrawlTask } from '../src/api/crawlerRun'
import { useTaskListQueryStore } from '../src/pages/crawler/tasks/useTaskListQueryStore'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getCrawlTaskStats: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('../src/api/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
}))

function renderPage() {
  const rootRoute = createRootRoute({ component: () => <TaskListPage /> })
  const runsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/crawler/runs', component: () => <div>runs page</div> })
  const router = createRouter({
    routeTree: rootRoute.addChildren([runsRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('crawler task run controls', () => {
  beforeEach(() => {
    useTaskListQueryStore.getState().reset()
    vi.mocked(getCrawlTaskStats).mockResolvedValue({ total: 1, running: 0, waiting: 1 })
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        name: '任务A',
        storage_location: 'A',
        urls: [],
        is_skip: false,
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
      }],
      total: 1,
    })
    vi.mocked(runCrawlTask).mockResolvedValue({ id: 'run-1' } as never)
  })

  it('starts an incremental run from the crawl dropdown', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '爬取' }))
    await userEvent.click(await screen.findByText('增量爬取'))

    await waitFor(() => {
      expect(runCrawlTask).toHaveBeenCalledWith('task-1', 'incremental')
    })
  })
})
```

- [ ] **Step 2: Run focused frontend tests and verify they fail**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx task-list-query-state.ui.test.tsx crawler-task-card-grid.ui.test.tsx
```

Expected: FAIL because `TaskListPage` does not fetch stats, still uses the table, still sends pagination params, and delete mode is still a radio group.

- [ ] **Step 3: Replace TaskListPage wiring**

Replace `frontend/src/pages/crawler/tasks/TaskListPage.tsx` with:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Modal, Select, Typography, message } from 'antd'
import {
  deleteCrawlTask,
  getCrawlTaskStats,
  getCrawlTasks,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTask, CrawlTaskStats, DeleteMode } from '@/api/crawlTask/types'
import { runCrawlTask } from '@/api/crawlerRun'
import type { CrawlMode } from '@/api/crawlerRun/types'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import { useTaskListQueryStore } from './useTaskListQueryStore'
import styles from './TaskPages.module.less'

const initialStats: CrawlTaskStats = {
  total: 0,
  running: 0,
  waiting: 0,
}

const deleteModeOptions: Array<{ value: DeleteMode; label: string }> = [
  { value: 'task_only', label: '仅删除任务' },
  { value: 'task_and_movies', label: '删除任务和关联影片' },
  { value: 'task_movies_and_cloud', label: '删除任务、关联影片和云存储' },
]

function TaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<CrawlTask[]>([])
  const [stats, setStats] = useState<CrawlTaskStats>(initialStats)
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)

  const keyword = useTaskListQueryStore((state) => state.keyword)
  const setKeyword = useTaskListQueryStore((state) => state.setKeyword)

  const fetchStats = useCallback(async () => {
    const data = await getCrawlTaskStats()
    setStats(data)
  }, [])

  const fetchTasks = useCallback(async (nextKeyword: string) => {
    setLoading(true)
    try {
      const normalizedKeyword = nextKeyword.trim()
      const data = await getCrawlTasks({
        keyword: normalizedKeyword || undefined,
      })
      setTasks(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshList = useCallback(() => {
    void fetchTasks(keyword)
    void fetchStats()
  }, [fetchStats, fetchTasks, keyword])

  useEffect(() => {
    refreshList()
  }, [refreshList])

  const handleDelete = useCallback(
    (task: CrawlTask) => {
      let selectedMode: DeleteMode = 'task_only'

      Modal.confirm({
        title: '确认删除',
        content: (
          <div>
            <p>确定删除任务「{task.name}」？</p>
            <div className={styles.deleteModeRow}>
              <Typography.Text className={styles.deleteModeLabel}>删除模式</Typography.Text>
              <Select<DeleteMode>
                aria-label="删除模式"
                defaultValue="task_only"
                options={deleteModeOptions}
                onChange={(value) => {
                  selectedMode = value
                }}
                style={{ width: '100%' }}
              />
            </div>
            <Typography.Text type="danger" className={styles.deleteWarning}>
              删除任务和关联影片将永久删除该任务独占的影片数据，且不可撤销。
            </Typography.Text>
          </div>
        ),
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        width: 500,
        onOk: async () => {
          const result = await deleteCrawlTask(task.id, selectedMode)
          const msg = selectedMode === 'task_and_movies'
            ? `，已删除 ${result?.deleted_movies ?? 0} 部关联影片`
            : ''
          message.success(`删除成功${msg}`)
          refreshList()
        },
      })
    },
    [refreshList],
  )

  const handleSearch = useCallback(
    (nextKeyword: string) => {
      setKeyword(nextKeyword)
    },
    [setKeyword],
  )

  const handleToggleSkip = useCallback(
    async (task: CrawlTask) => {
      await updateCrawlTask(task.id, { is_skip: !task.is_skip })
      message.success(task.is_skip ? '任务已启用' : '任务已禁用')
      refreshList()
    },
    [refreshList],
  )

  const handleRun = useCallback(
    async (task: CrawlTask, mode: CrawlMode) => {
      try {
        await runCrawlTask(task.id, mode)
        message.success(`已提交${mode === 'incremental' ? '增量' : '全量'}爬取任务`)
        void navigate({ to: '/crawler/runs' })
      } catch {
        message.error('启动爬取任务失败')
      }
    },
    [navigate],
  )

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>爬取任务</h1>
          <p className={styles.subtitle}>管理 JavDB 媒体资源的爬取任务</p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate({ to: '/crawler/tasks/new' })}
        >
          新建任务
        </Button>
      </div>

      <section className={styles.statsBar} aria-label="任务统计">
        <div className={styles.statCard}>
          <span className={styles.statLabel}>总数</span>
          <span className={styles.statValue}>{stats.total}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>爬取中</span>
          <span className={styles.statValue}>{stats.running}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>等待中</span>
          <span className={styles.statValue}>{stats.waiting}</span>
        </div>
      </section>

      <section className={styles.panel}>
        <TaskListCards
          tasks={tasks}
          loading={loading}
          total={total}
          keyword={keyword}
          onKeywordChange={setKeyword}
          onEdit={(task) => navigate({ to: '/crawler/tasks/$id/edit', params: { id: task.id } })}
          onDelete={handleDelete}
          onToggleSkip={handleToggleSkip}
          onSearch={handleSearch}
          onRun={handleRun}
        />
      </section>
    </div>
  )
}

export default TaskListPage
```

- [ ] **Step 4: Add delete modal styles**

Append to `frontend/src/pages/crawler/tasks/TaskPages.module.less`:

```less
.deleteModeRow {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0;
}

.deleteModeLabel {
  font-size: 13px;
}

.deleteWarning {
  display: block;
  font-size: 12px;
  line-height: 20px;
}
```

- [ ] **Step 5: Run focused frontend tests and verify they pass**

Run:

```bash
cd frontend
npm test -- crawler-run-controls.ui.test.tsx task-list-query-state.ui.test.tsx crawler-task-card-grid.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/TaskPages.module.less frontend/tests/crawler-run-controls.ui.test.tsx frontend/tests/task-list-query-state.ui.test.tsx frontend/tests/crawler-task-card-grid.ui.test.tsx
git commit -m "feat: render all crawler tasks as cards"
```

---

### Task 5: Full Verification

**Files:**
- No source changes.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd frontend
npm test -- task-list-query-state.ui.test.tsx crawler-run-controls.ui.test.tsx crawler-task-card-grid.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual UI verification**

Run backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Run frontend:

```bash
cd frontend
npm run dev
```

Open:

```text
/crawler/tasks
```

Expected:

- Existing search condition remains visible and usable after navigating away and returning.
- The frontend request to `/api/crawler/tasks` does not include `skip` or `limit`.
- The old table is absent.
- No pagination component or page-size selector is shown.
- All matching tasks are displayed in the grid.
- Desktop width shows four cards per row.
- Page top shows `总数`, `爬取中`, and `等待中`.
- Card top shows task name and current task status.
- Card middle shows `网盘路径`, `URL 名称`, `最后爬取时间`, and enable/disable status.
- Card bottom shows crawl dropdown, edit button, delete button, and more menu.
- Crawl dropdown contains `增量爬取` and `全量爬取`.
- Delete confirmation uses a dropdown select for delete mode.

---

## Self-Review

- Spec coverage:
  - Existing query condition remains through `useTaskListQueryStore.keyword`.
  - The frontend does not use pagination params and the UI has no pagination.
  - Old table is deleted and replaced by `TaskListCards`.
  - Card grid uses CSS `repeat(4, minmax(0, 1fr))` on desktop.
  - Incremental/full crawl actions are inside one Ant Design `Dropdown`.
  - Delete mode is inside one Ant Design `Select`.
  - Card top, middle, footer content matches the requested sections.
  - Page top stats show total, running, and waiting counts from `/api/crawler/tasks/stats`.
- Red-flag scan:
  - The plan includes exact file paths, commands, expected results, and source/test snippets.
- Type consistency:
  - `CrawlTask.last_run_at` and `last_run_status` are added in backend schema and frontend type.
  - `CrawlTaskStats` has `total`, `running`, and `waiting` in backend response and frontend type.
  - `TaskListCards` receives only all-task list props and has no pagination props.
