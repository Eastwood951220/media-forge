# Storage Task And Movie List UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the storage task detail page and movie list page presentation with a denser, clearer `ui-ux-pro-max`-style operational UI, and remove the movie list timed refresh.

**Architecture:** Keep the work frontend-only and scoped to the existing React/Ant Design pages. Reuse current API hooks and realtime subscriptions; replace only the movie list polling interval with manual refresh and existing realtime item updates. Improve presentation through focused component and LESS changes without changing backend contracts.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Ant Design 6, LESS modules, Vitest 3, React Testing Library.

## Global Constraints

- Project scope remains the Media Forge refactor and optimization of `/Users/eastwood/Code/PycharmProjects/jav-scrapling`.
- Do not add speculative features, product expansions, or unrelated modules.
- Frontend work stays in `frontend/` and uses the existing React 19 + Vite 8 + TypeScript 6 + Ant Design 6 stack.
- Do not remove manual refresh buttons or realtime event subscriptions unless a task explicitly says so.
- Remove timed refresh only from the movie list hook at `frontend/src/pages/content/movies/hooks/useMovieList.ts`.
- UI must stay operational and scan-friendly: compact controls, restrained visual styling, no marketing hero, no nested cards.

---

## File Structure

- Modify `frontend/src/pages/content/movies/hooks/useMovieList.ts`: remove `setInterval` polling and the ref indirection used only by polling.
- Modify `frontend/tests/movie-list.ui.test.tsx`: add regression coverage proving the movie list does not register a timed refresh interval.
- Modify `frontend/src/pages/storage/tasks/components/StorageMainSummaryCard.tsx`: replace the basic `Descriptions` block with a scan-friendly task header, progress summary, KPI tiles, and compact metadata.
- Modify `frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx`: improve subtask table density and scanability without changing navigation behavior.
- Modify `frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx`: improve the storage task list table header, progress display, actions, and empty/scroll behavior.
- Modify `frontend/src/pages/storage/tasks/StorageTasks.module.less`: add the layout and responsive styles needed by the storage task pages.
- Modify `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`: add assertions for the improved detail and list presentation.
- Modify `frontend/src/pages/content/movies/MovieListPage.module.less`: add compact list page spacing for the movie list.
- Modify `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`: group search actions and make controls easier to scan while preserving config-driven visibility.

### Task 1: Remove Movie List Timed Refresh

**Files:**
- Modify: `frontend/src/pages/content/movies/hooks/useMovieList.ts`
- Modify: `frontend/tests/movie-list.ui.test.tsx`

**Interfaces:**
- Consumes: `useMovieList(filterParams, initialSort?)` current return shape.
- Produces: Same `MovieList` return type; no exported `POLL_INTERVAL_MS`; `reload()` remains the manual refresh path.

- [ ] **Step 1: Write the failing test**

Add `afterEach` to the Vitest imports and add timer cleanup around the suite:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
```

Add this inside `describe('MovieListPage', () => { ... })`:

```ts
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })
```

Add this test after `loads configured filters and movie list after filter config completes`:

```tsx
  it('does not register a timed movie list refresh interval', async () => {
    vi.useFakeTimers()
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval')

    renderPage()

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenCalledTimes(1)
    })

    expect(setIntervalSpy).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(30_000)
    expect(fetchMovies).toHaveBeenCalledTimes(1)
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- tests/movie-list.ui.test.tsx -t "does not register a timed movie list refresh interval"
```

Expected: FAIL because `setInterval` is called by `useMovieList`.

- [ ] **Step 3: Remove polling implementation**

In `frontend/src/pages/content/movies/hooks/useMovieList.ts`, replace the import:

```ts
import {useCallback, useEffect, useState} from "react";
```

Delete:

```ts
const POLL_INTERVAL_MS = 10_000;
```

Delete the `loadMoviesRef` block and polling effect:

```ts
    const loadMoviesRef = useRef(loadMovies);
    loadMoviesRef.current = loadMovies;

    useEffect(() => {
        const id = setInterval(() => {
            void loadMoviesRef.current();
        }, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, []);
```

Keep the initial load effect unchanged:

```ts
    useEffect(() => {
        void loadMovies();
    }, [loadMovies]);
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && npm test -- tests/movie-list.ui.test.tsx -t "does not register a timed movie list refresh interval"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/content/movies/hooks/useMovieList.ts frontend/tests/movie-list.ui.test.tsx
git commit -m "fix: remove movie list polling refresh"
```

### Task 2: Redesign Storage Task Detail Summary

**Files:**
- Modify: `frontend/src/pages/storage/tasks/components/StorageMainSummaryCard.tsx`
- Modify: `frontend/src/pages/storage/tasks/StorageTasks.module.less`
- Modify: `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

**Interfaces:**
- Consumes: `StorageMainTask` fields already used by the page: `alias`, `id`, `status`, `storage_mode`, `total_count`, `success_count`, `failed_count`, `skipped_count`, `created_at`, `finished_at`, `error_message`.
- Produces: Same `StorageMainSummaryCardProps`; visible labels `任务进度`, `成功`, `失败`, `跳过`, `任务编号`, `创建时间`, `完成时间`.

- [ ] **Step 1: Write the failing detail presentation test**

Update the router mock in `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`:

```ts
vi.mock('@tanstack/react-router', () => ({
  useNavigate: vi.fn().mockReturnValue(vi.fn()),
  useParams: vi.fn().mockReturnValue({ id: 'task-detail-1' }),
}))
```

Update the storage API mock:

```ts
vi.mock('@/api/storage/storageTasks', () => ({
  getStorageMainTask: vi.fn().mockResolvedValue({
    id: 'task-detail-1',
    alias: '云存储_详情测试',
    display_name: '云存储_详情测试',
    source: 'batch',
    storage_mode: 'batch',
    status: 'running',
    total_count: 10,
    success_count: 6,
    failed_count: 1,
    skipped_count: 2,
    created_at: '2026-07-10T01:00:00Z',
    finished_at: null,
  }),
  listStorageSubTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  listStorageMainTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  stopStorageMainTask: vi.fn(),
  restartStorageMainTask: vi.fn(),
  deleteStorageMainTask: vi.fn().mockResolvedValue(undefined),
}))
```

Import the detail page:

```ts
import StorageTaskDetailPage from '../StorageTaskDetailPage'
```

Add this test:

```tsx
  it('renders redesigned storage task detail summary metrics', async () => {
    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('云存储_详情测试')).toBeInTheDocument()
    expect(screen.getByText('任务进度')).toBeInTheDocument()
    expect(screen.getByText('任务编号')).toBeInTheDocument()
    expect(screen.getByText('task-detail-1')).toBeInTheDocument()
    expect(screen.getByText('成功')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getByText('跳过')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx -t "renders redesigned storage task detail summary metrics"
```

Expected: FAIL because the current summary does not render `任务进度` or the redesigned metric layout.

- [ ] **Step 3: Implement summary card layout**

Replace `frontend/src/pages/storage/tasks/components/StorageMainSummaryCard.tsx` with:

```tsx
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Progress, Space, Statistic, Tag, Typography } from 'antd'
import type { StorageMainTask } from '@/api/storage/storageTasks/types'
import styles from '../StorageTasks.module.less'
import { modeLabels, statusLabels } from '../utils/status'

interface StorageMainSummaryCardProps {
  task: StorageMainTask | null
  loading: boolean
  actionLoading: 'stop' | 'restart' | null
  onStop: () => void
  onRestart: () => void
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : '-'
}

function getProgressPercent(task: StorageMainTask) {
  if (!task.total_count) return 0
  const finished = task.success_count + task.failed_count + task.skipped_count
  return Math.min(100, Math.round((finished / task.total_count) * 100))
}

export function StorageMainSummaryCard({
  task,
  loading,
  actionLoading,
  onStop,
  onRestart,
}: StorageMainSummaryCardProps) {
  if (!task) return null

  const status = statusLabels[task.status] || { text: task.status, color: 'default' }
  const progressPercent = getProgressPercent(task)

  return (
    <Card
      className={styles.summaryCard}
      loading={loading}
      title={(
        <div className={styles.summaryTitle}>
          <div className={styles.summaryHeading}>
            <Typography.Title level={4}>{task.alias || task.id}</Typography.Title>
            <Space size={8} wrap>
              <Tag color={status.color}>{status.text}</Tag>
              <Tag>{modeLabels[task.storage_mode] || task.storage_mode}</Tag>
            </Space>
          </div>
          <Space>
            {(task.status === 'queued' || task.status === 'running') && (
              <Button
                danger
                icon={<StopOutlined />}
                loading={actionLoading === 'stop'}
                onClick={() => void onStop()}
              >
                停止
              </Button>
            )}
            {(task.status === 'stopped' || task.status === 'failed') && (
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                loading={actionLoading === 'restart'}
                onClick={() => void onRestart()}
              >
                重启
              </Button>
            )}
          </Space>
        </div>
      )}
    >
      <div className={styles.summaryGrid}>
        <section className={styles.progressPanel}>
          <div className={styles.panelLabel}>任务进度</div>
          <Progress
            percent={progressPercent}
            status={task.failed_count > 0 ? 'exception' : undefined}
            strokeColor={task.failed_count > 0 ? undefined : '#1677ff'}
          />
          <div className={styles.progressMeta}>
            <span>总数 {task.total_count}</span>
            <span>已处理 {task.success_count + task.failed_count + task.skipped_count}</span>
          </div>
        </section>

        <div className={styles.metricGrid}>
          <Statistic title="成功" value={task.success_count} valueStyle={{ color: '#389e0d' }} />
          <Statistic title="失败" value={task.failed_count} valueStyle={{ color: task.failed_count > 0 ? '#cf1322' : undefined }} />
          <Statistic title="跳过" value={task.skipped_count} />
        </div>
      </div>

      <Descriptions className={styles.summaryDescriptions} column={{ xs: 1, sm: 2, lg: 3 }} size="small">
        <Descriptions.Item label="任务编号">{task.id}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatDateTime(task.created_at)}</Descriptions.Item>
        <Descriptions.Item label="完成时间">{formatDateTime(task.finished_at)}</Descriptions.Item>
      </Descriptions>

      {task.error_message && (
        <Alert className={styles.summaryError} type="error" showIcon message="错误信息" description={task.error_message} />
      )}
    </Card>
  )
}
```

Add these styles to `frontend/src/pages/storage/tasks/StorageTasks.module.less`:

```less
.summaryCard {
  margin-bottom: 16px;
}

.summaryTitle {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.summaryHeading {
  min-width: 0;

  :global(.ant-typography) {
    margin: 0 0 8px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.summaryGrid {
  display: grid;
  grid-template-columns: minmax(320px, 1.4fr) minmax(280px, 1fr);
  gap: 20px;
  align-items: stretch;
}

.progressPanel {
  min-width: 0;
  padding: 16px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fafafa;
}

.panelLabel {
  margin-bottom: 12px;
  color: rgba(0, 0, 0, 0.65);
  font-size: 13px;
}

.progressMeta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  color: rgba(0, 0, 0, 0.65);
  font-size: 12px;
}

.metricGrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.metricGrid :global(.ant-statistic) {
  min-width: 0;
  padding: 16px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fff;
}

.summaryDescriptions {
  margin-top: 16px;
}

.summaryError {
  margin-top: 16px;
}

@media (max-width: 960px) {
  .summaryTitle,
  .summaryGrid {
    grid-template-columns: 1fr;
  }

  .summaryTitle {
    flex-direction: column;
  }
}
```

- [ ] **Step 4: Run detail tests**

Run:

```bash
cd frontend && npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx -t "renders redesigned storage task detail summary metrics"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/storage/tasks/components/StorageMainSummaryCard.tsx frontend/src/pages/storage/tasks/StorageTasks.module.less frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
git commit -m "feat: polish storage task detail summary"
```

### Task 3: Improve Storage Task Tables

**Files:**
- Modify: `frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx`
- Modify: `frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx`
- Modify: `frontend/src/pages/storage/tasks/StorageTasks.module.less`
- Modify: `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

**Interfaces:**
- Consumes: existing props for `StorageMainTaskTable` and `StorageSubTaskTable`.
- Produces: Same props and navigation callbacks; adds visible labels `任务列表`, `处理进度`, and `子任务明细`.

- [ ] **Step 1: Write failing presentation tests**

Add this list page test:

```tsx
  it('renders storage task list with progress-focused table copy', async () => {
    vi.mocked(listStorageMainTasks).mockResolvedValueOnce({
      rows: [
        {
          id: 'task-list-1',
          alias: '云存储_列表测试',
          display_name: '云存储_列表测试',
          source: 'batch',
          storage_mode: 'batch',
          status: 'running',
          total_count: 4,
          success_count: 2,
          failed_count: 1,
          skipped_count: 0,
          created_at: '2026-07-10T01:00:00Z',
        },
      ],
      total: 1,
    })

    render(<StorageTaskListPage />)

    expect(await screen.findByText('任务列表')).toBeInTheDocument()
    expect(screen.getByText('云存储_列表测试')).toBeInTheDocument()
    expect(screen.getByText('处理进度')).toBeInTheDocument()
  })
```

Update the detail test from Task 2 to also assert:

```tsx
    expect(screen.getByText('子任务明细')).toBeInTheDocument()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend && npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx -t "storage task list with progress-focused table copy|redesigned storage task detail summary"
```

Expected: FAIL because current cards are titled `存储任务` and `子任务列表`, and the main table has separate count columns instead of `处理进度`.

- [ ] **Step 3: Update storage main task table**

In `frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx`, add `Progress` and `Typography` imports:

```tsx
import { Button, Card, Popconfirm, Progress, Space, Table, Tag, Typography } from 'antd'
```

Add this helper before the component:

```tsx
function getProgressPercent(task: StorageMainTask) {
  if (!task.total_count) return 0
  const finished = task.success_count + task.failed_count + task.skipped_count
  return Math.min(100, Math.round((finished / task.total_count) * 100))
}
```

Replace the separate `总数`, `成功`, `失败`, and `跳过` columns with:

```tsx
    {
      title: '处理进度',
      key: 'progress',
      width: 220,
      render: (_, record) => (
        <div className={styles.tableProgressCell}>
          <Progress
            percent={getProgressPercent(record)}
            size="small"
            status={record.failed_count > 0 ? 'exception' : undefined}
          />
          <div className={styles.tableProgressMeta}>
            <span>总 {record.total_count}</span>
            <span>成功 {record.success_count}</span>
            <span>失败 {record.failed_count}</span>
            <span>跳过 {record.skipped_count}</span>
          </div>
        </div>
      ),
    },
```

Change the `别名` column render to:

```tsx
      render: (alias: string | null, record) => (
        <Typography.Text ellipsis title={alias || record.id}>
          {alias || record.id}
        </Typography.Text>
      ),
```

Change the card title from:

```tsx
title="存储任务"
```

to:

```tsx
title="任务列表"
```

Add table scroll:

```tsx
        scroll={{ x: 980 }}
```

Import styles:

```tsx
import styles from '../StorageTasks.module.less'
```

- [ ] **Step 4: Update storage subtask table**

In `frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx`, change the card title:

```tsx
<Card title="子任务明细" className={styles.subtaskTableCard}>
```

Import styles:

```tsx
import styles from '../StorageTasks.module.less'
```

Add table size and scroll:

```tsx
        size="middle"
        scroll={{ x: 520 }}
```

- [ ] **Step 5: Add table styles**

Append to `frontend/src/pages/storage/tasks/StorageTasks.module.less`:

```less
.tableProgressCell {
  min-width: 0;
}

.tableProgressMeta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  color: rgba(0, 0, 0, 0.65);
  font-size: 12px;
  line-height: 18px;
}

.subtaskTableCard {
  min-width: 0;
}
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd frontend && npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx frontend/src/pages/storage/tasks/StorageTasks.module.less frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
git commit -m "feat: improve storage task tables"
```

### Task 4: Polish Movie List Filter Presentation

**Files:**
- Modify: `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`
- Modify: `frontend/src/pages/content/movies/MovieListPage.module.less`
- Modify: `frontend/tests/movie-list.ui.test.tsx`

**Interfaces:**
- Consumes: existing `MovieFilterBarProps`.
- Produces: Same props and behavior; keeps visible buttons `搜索`, `刷新`, `配置`; adds a compact filter layout class.

- [ ] **Step 1: Write failing UI test**

Add this assertion to `renders filters with settings button and opens read-only detail` after the search input assertion:

```tsx
    expect(screen.getByTestId('movie-filter-bar')).toHaveClass('filterBar')
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- tests/movie-list.ui.test.tsx -t "renders filters with settings button"
```

Expected: FAIL because `MovieFilterBar` has no `data-testid` or CSS module class.

- [ ] **Step 3: Add filter bar styling**

In `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`, import styles:

```tsx
import styles from "../MovieListPage.module.less";
```

Change the outer `Space` to:

```tsx
        <Space vertical className={styles.filterBar} data-testid="movie-filter-bar" size={8}>
```

Change the inner `Space` to:

```tsx
            <Space wrap size={[8, 8]} className={styles.filterControls}>
```

Wrap action buttons with:

```tsx
                <Space size={6} className={styles.filterActions}>
                    <Button type="primary" icon={<SearchOutlined/>} onClick={onSearch}>搜索</Button>
                    <Button icon={<ReloadOutlined/>} onClick={onReset}>刷新</Button>
                    {onConfigClick && <Button icon={<SettingOutlined/>} onClick={onConfigClick}>配置</Button>}
                </Space>
```

Remove the old three standalone action buttons:

```tsx
                <Button type="primary" onClick={onSearch}>搜索</Button>
                <Button icon={<ReloadOutlined/>} onClick={onReset}>刷新</Button>
                {onConfigClick && <Button icon={<SettingOutlined/>} onClick={onConfigClick}>配置</Button>}
```

Add styles to `frontend/src/pages/content/movies/MovieListPage.module.less`:

```less
.filterBar {
  width: 100%;
}

.filterControls {
  width: 100%;
}

.filterActions {
  margin-left: auto;
}

@media (max-width: 768px) {
  .filterActions {
    width: 100%;
    margin-left: 0;
  }
}
```

- [ ] **Step 4: Run movie list tests**

Run:

```bash
cd frontend && npm test -- tests/movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/content/movies/components/MovieFilterBar.tsx frontend/src/pages/content/movies/MovieListPage.module.less frontend/tests/movie-list.ui.test.tsx
git commit -m "feat: polish movie list filters"
```

### Task 5: Full Frontend Verification

**Files:**
- No new files.
- Verify all files changed by Tasks 1-4.

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: verified frontend build and test result.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
cd frontend && npm test -- tests/movie-list.ui.test.tsx src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS. If lint fails on formatting introduced by these tasks, fix only the touched lines.

- [ ] **Step 3: Run build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit verification fixes if any**

If Step 2 or Step 3 required code changes:

```bash
git add frontend/src/pages/content/movies frontend/src/pages/storage/tasks frontend/tests/movie-list.ui.test.tsx
git commit -m "fix: resolve frontend verification issues"
```

If no changes were needed, do not create an empty commit.

## Self-Review

- Spec coverage: Task 2 and Task 3 optimize the task detail/list display; Task 4 optimizes the movie list page display; Task 1 removes the movie list timed refresh.
- Placeholder scan: No forbidden placeholder wording or open-ended error handling instructions remain.
- Type consistency: Existing component props and hook return types are preserved; new helpers are local-only and do not create cross-task API dependencies.
