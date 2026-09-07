import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
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
  tags: [
    { id: 'tag-vr', name: 'VR' },
    { id: 'tag-actor', name: '演员' },
  ],
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

const idleRuntime = {
  task_id: 'task-1',
  runtime_status: 'idle' as const,
  latest_run_id: null,
  state_updated_at: '2026-09-04T00:00:00Z',
  last_run_at: null,
}

function renderCards(overrides: Partial<ComponentProps<typeof TaskListCards>> = {}) {
  return render(
    <TaskListCards
      tasks={[baseTask as never]}
      loading={false}
      total={1}
      runtimeByTaskId={{ 'task-1': idleRuntime } as never}
      runtimeReady={true}
      tagOptions={[{ id: 'tag-vr', name: 'VR' }]}
      selectedTagNames={[]}
      onTagFilterChange={vi.fn()}
      keyword=""
      onKeywordChange={vi.fn()}
      selectedTaskIds={[]}
      onSelectedTaskIdsChange={vi.fn()}
      onBatchRunClick={vi.fn()}
      batchRunLoading={false}
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
      {...overrides}
    />,
  )
}

describe('TaskListCards action alignment', () => {
  beforeEach(() => {
    useCrawlerRuntimeStore.getState().reset()
  })

  it('renders primary and maintenance action groups for task cards', () => {
    const { container } = renderCards()

    expect(screen.getAllByRole('button', { name: /爬取/ }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('button', { name: 'play-circle 爬取' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /URL 爬取/ })).toBeInTheDocument()
    expect(container.querySelector('[class*="taskCardPrimaryActions"]')).toBeTruthy()
    expect(container.querySelector('[class*="taskCardMaintenanceActions"]')).toBeTruthy()
  })

  it('shows task tags on the card', () => {
    renderCards()

    expect(screen.getByText('VR')).toBeInTheDocument()
    expect(screen.getByText('演员')).toBeInTheDocument()
  })

  it('shows sync tag and disables actions when runtime is not ready', () => {
    render(
      <TaskListCards
        tasks={[baseTask as never]}
        loading={false}
        total={1}
        runtimeByTaskId={{}}
        runtimeReady={false}
        tagOptions={[]}
        selectedTagNames={[]}
        onTagFilterChange={vi.fn()}
        keyword=""
        onKeywordChange={vi.fn()}
        selectedTaskIds={[]}
        onSelectedTaskIdsChange={vi.fn()}
        onBatchRunClick={vi.fn()}
        batchRunLoading={false}
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
    expect(screen.queryByRole('button', { name: 'play-circle 爬取' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /URL 爬取/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /编辑/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /删除/ })).not.toBeInTheDocument()
  })

  it('calls batch create handler from the toolbar', () => {
    const onBatchTaskClick = vi.fn()
    const { container } = renderCards({ onBatchTaskClick })

    expect(container.querySelector('[class*="taskListToolbarFilters"]')).toBeTruthy()
    expect(container.querySelector('[class*="taskListToolbarActions"]')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /批量新建/ }))

    expect(onBatchTaskClick).toHaveBeenCalledTimes(1)
  })

  it('calls tag filter change from the toolbar', async () => {
    const onTagFilterChange = vi.fn()
    renderCards({ onTagFilterChange })

    const filterInput = screen.getByLabelText('标签筛选') as HTMLInputElement
    fireEvent.mouseDown(filterInput)
    expect(await screen.findByRole('option', { name: 'VR' })).toBeInTheDocument()
    fireEvent.keyDown(filterInput, { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, which: 40 })
    fireEvent.keyDown(filterInput, { key: 'Enter', code: 'Enter', keyCode: 13, which: 13 })

    await waitFor(() => {
      expect(onTagFilterChange).toHaveBeenCalledWith(['VR'], expect.anything())
    })
  })

  it('renders the crawler task search input in the toolbar and reports keyword changes', () => {
    const onKeywordChange = vi.fn()
    const { container } = renderCards({ onKeywordChange })

    const searchInput = screen.getByPlaceholderText('搜索任务名称 / URL 名称 / URL') as HTMLInputElement
    expect(searchInput).toBeInTheDocument()
    expect(searchInput).toHaveAttribute('aria-label', '搜索任务名称、URL 名称或 URL')
    expect(container.querySelector('[class*="taskListToolbarFilters"]')).toBeTruthy()
    expect(container.querySelector('[class*="taskSearchInput"]')).toBeTruthy()

    fireEvent.change(searchInput, { target: { value: 'prestige' } })

    expect(onKeywordChange).toHaveBeenCalledWith('prestige')
  })

  it('shows the keyword from props inside the search input', () => {
    renderCards({ keyword: 'prestige' })

    const searchInput = screen.getByPlaceholderText('搜索任务名称 / URL 名称 / URL') as HTMLInputElement
    expect(searchInput.value).toBe('prestige')
  })

  it('shows a dash for the latest run row when the task has no latest run', () => {
    renderCards()

    const row = screen.getByText('上次运行').parentElement as HTMLElement
    expect(row.textContent).toBe('上次运行-')
  })

  it('shows failed and total counts from the latest run summary', () => {
    renderCards({
      tasks: [
        {
          ...baseTask,
          last_run_at: '2026-09-05T10:00:00Z',
          last_run_status: 'completed',
          last_run_total: 63,
          last_run_failed: 3,
        },
      ] as never,
    })

    expect(screen.getByText('失败 3 / 总 63')).toBeInTheDocument()
  })

  it('tracks card selection and disables batch run without selection', async () => {
    const onSelectedTaskIdsChange = vi.fn()
    const onBatchRunClick = vi.fn()
    renderCards({ onSelectedTaskIdsChange, onBatchRunClick })

    expect(screen.getByRole('button', { name: /批量爬取/ })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /选择 Aligned Task/ }))

    await waitFor(() => {
      expect(onSelectedTaskIdsChange).toHaveBeenCalledWith(['task-1'])
    })
    expect(onBatchRunClick).not.toHaveBeenCalled()
  })

  it('calls batch run handler when tasks are selected', async () => {
    const onBatchRunClick = vi.fn()
    renderCards({ selectedTaskIds: ['task-1'], onBatchRunClick })

    expect(screen.getByText('已选 1 个')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /批量爬取/ }))

    expect(onBatchRunClick).toHaveBeenCalledTimes(1)
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
          tags: [],
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
