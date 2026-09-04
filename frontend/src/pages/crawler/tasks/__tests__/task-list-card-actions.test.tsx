import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListCards from '../components/TaskListCards'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/api/crawler/crawlTask', () => ({
  createTaskUrlRun: vi.fn(),
  deleteCrawlTask: vi.fn(),
  getCrawlTasks: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('@/api/crawler/crawlerRun', () => ({
  restartCrawlerRun: vi.fn(),
  runCrawlTask: vi.fn(),
  stopCrawlerRun: vi.fn(),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { createTaskUrlRun, getCrawlTasks } from '@/api/crawler/crawlTask'
import { runCrawlTask } from '@/api/crawler/crawlerRun'
import type { CrawlTask } from '@/api/crawler/crawlTask/types'
import type { CrawlMode } from '@/api/crawler/crawlerRun/types'
import { useTaskListData } from '../hooks/useTaskListData'
import { useTaskUrlRun } from '../hooks/useTaskUrlRun'

const baseTask = {
  id: 'task-1',
  name: 'Aligned Task',
  storage_location: 'Aligned Task',
  urls: [{ id: 'url-1', url: 'https://javdb.com/actors/a', url_type: 'actors', url_name: 'A' }],
  is_skip: false,
  status: 'idle',
  task_id: null,
  error_message: null,
  total_found: 0,
  total_qualified: 0,
  owner_id: 'owner-1',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
  last_run_at: null,
  last_run_status: null,
}

describe('TaskListCards action alignment', () => {
  beforeEach(() => {
    useCrawlerRuntimeStore.getState().reset()
  })

  it('renders primary and maintenance action groups for task cards', () => {
    const { container } = render(
      <TaskListCards
        tasks={[baseTask as never]}
        loading={false}
        total={1}
        runtimeByTaskId={{ 'task-1': { task_id: 'task-1', runtime_status: 'idle', latest_run_id: null, latest_run_status: null, last_run_at: null } } as never}
        runtimeReady={true}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleSkip={vi.fn()}
        onRun={vi.fn()}
        onStop={vi.fn()}
        onRestart={vi.fn()}
        onUrlRun={vi.fn()}
        onTemporaryTaskClick={vi.fn()}
        onBatchTaskClick={vi.fn()}
        current={1}
        pageSize={20}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    )

    expect(screen.getAllByRole('button', { name: /爬取/ }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('button', { name: /URL 爬取/ })).toBeInTheDocument()
    expect(container.querySelector('[class*="taskCardPrimaryActions"]')).toBeTruthy()
    expect(container.querySelector('[class*="taskCardMaintenanceActions"]')).toBeTruthy()
  })

  it('shows sync tag and disables actions when runtime is not ready', () => {
    render(
      <TaskListCards
        tasks={[baseTask as never]}
        loading={false}
        total={1}
        runtimeByTaskId={{}}
        runtimeReady={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleSkip={vi.fn()}
        onRun={vi.fn()}
        onStop={vi.fn()}
        onRestart={vi.fn()}
        onUrlRun={vi.fn()}
        onTemporaryTaskClick={vi.fn()}
        onBatchTaskClick={vi.fn()}
        current={1}
        pageSize={20}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    )

    expect(screen.getByText('同步中')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /爬取/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /URL 爬取/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /编辑/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /删除/ })).not.toBeInTheDocument()
  })

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
})

describe('optimistic queued runtime updates after run submission', () => {
  it('marks a task queued right after a normal run is accepted', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [
        {
          id: 'task-1',
          name: 'Aligned Task',
          storage_location: 'Aligned Task',
          is_skip: false,
          urls: [],
        },
      ],
      total: 1,
      page: 1,
      size: 20,
    } as never)
    vi.mocked(runCrawlTask).mockResolvedValue({ accepted: true, run_id: 'run-1' } as never)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useTaskListData(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.handleRun(baseTask as never as CrawlTask, 'incremental' as CrawlMode)
    })

    expect(useCrawlerRuntimeStore.getState().taskRuntimeById['task-1']).toEqual(
      expect.objectContaining({
        task_id: 'task-1',
        runtime_status: 'queued',
        latest_run_id: 'run-1',
      }),
    )
  })

  it('marks a task queued right after a URL subset run is accepted', async () => {
    vi.mocked(createTaskUrlRun).mockResolvedValue({ accepted: true, run_id: 'url-run-9' } as never)

    const onSubmitted = vi.fn()
    const appWrapper = ({ children }: PropsWithChildren) => <App>{children}</App>

    const { result } = renderHook(() => useTaskUrlRun({ onSubmitted }), { wrapper: appWrapper })

    await act(async () => {
      result.current.openTaskUrlRun(baseTask as never as CrawlTask)
    })

    await act(async () => {
      await result.current.submitTaskUrlRun({ url_ids: ['url-1'], crawl_mode: 'incremental' })
    })

    expect(onSubmitted).toHaveBeenCalledTimes(1)
    expect(useCrawlerRuntimeStore.getState().taskRuntimeById['task-1']).toEqual(
      expect.objectContaining({
        task_id: 'task-1',
        runtime_status: 'queued',
        latest_run_id: 'url-run-9',
      }),
    )
  })
})