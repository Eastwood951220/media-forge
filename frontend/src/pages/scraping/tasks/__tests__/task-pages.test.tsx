import { App as AntApp } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../TaskListPage'
import TaskDetailPage from '../TaskDetailPage'
import * as api from '@/api/scraping/scrapingTasks'
import * as realtime from '@/realtime/eventSourceClient'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@/api/scraping/scrapingTasks', () => ({
  listScrapingTasks: vi.fn(),
  getScrapingTask: vi.fn(),
  createScrapingTask: vi.fn(),
  cancelScrapingTask: vi.fn(),
  retryScrapingTask: vi.fn(),
  getScrapingItem: vi.fn(),
  getScrapingItemLogs: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  useParams: () => ({ id: 'task-1' }),
}))

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AntApp>{ui}</AntApp>
    </QueryClientProvider>,
  )
}

describe('scraping task pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listScrapingTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        status: 'success',
        total_count: 2,
        success_count: 2,
        failed_count: 0,
        skipped_count: 0,
        cancel_requested: false,
        created_by: 'user-1',
      }],
      total: 1,
      page: 1,
      size: 20,
    })
    vi.mocked(api.getScrapingTask).mockResolvedValue({
      id: 'task-1',
      status: 'partial_failed',
      total_count: 2,
      success_count: 1,
      failed_count: 1,
      skipped_count: 0,
      cancel_requested: false,
      created_by: 'user-1',
      items: [{
        id: 'item-1',
        task_id: 'task-1',
        movie_id: 'movie-1',
        movie_code: 'ADN-784',
        movie_title: 'ADN-784',
        status: 'failed',
        source: '',
        folder: '',
        duration_ms: 10,
        error_message: 'boom',
      }],
    })
    vi.mocked(api.retryScrapingTask).mockResolvedValue({
      id: 'task-2',
      status: 'queued',
      total_count: 1,
      success_count: 0,
      failed_count: 0,
      skipped_count: 0,
      cancel_requested: false,
      created_by: 'user-1',
    })
    vi.mocked(api.getScrapingItem).mockResolvedValue({
      id: 'item-1', task_id: 'task-1', movie_id: 'movie-1', movie_code: 'ADN-784',
      movie_title: 'ADN-784', status: 'failed', step: 'write_artwork', source: 'fanza',
      folder: '/media/ADN-784', duration_ms: 10, error_message: 'boom',
    })
    vi.mocked(api.getScrapingItemLogs).mockResolvedValue([
      { timestamp: '2026-10-22T13:00:00+00:00', level: 'INFO', message: '开始刮削', step: 'prepare' },
      { timestamp: '2026-10-22T13:00:01+00:00', level: 'ERROR', message: '图片下载失败', step: 'write_artwork' },
    ])
  })

  it('renders the task list with a status tag, title, and refresh button', async () => {
    renderPage(<TaskListPage />)
    expect(await screen.findByText('2/2 成功，失败 0，跳过 0')).toBeInTheDocument()
    expect(screen.getByText('成功')).toBeInTheDocument()
    expect(screen.getByText('刮削任务')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /刷新/ }))

    await waitFor(() => expect(api.listScrapingTasks).toHaveBeenCalledTimes(2))
  })

  it('renders the task detail items', async () => {
    renderPage(<TaskDetailPage />)
    expect(await screen.findAllByText('ADN-784')).not.toHaveLength(0)
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('opens an item drawer with steps and logs', async () => {
    renderPage(<TaskDetailPage />)
    fireEvent.click(await screen.findByRole('button', { name: '详情' }))

    expect(await screen.findByText('步骤时间线')).toBeInTheDocument()
    expect(screen.getByText('任务日志')).toBeInTheDocument()
    expect(screen.getAllByText('下载并筛选图片').length).toBeGreaterThan(0)
    expect(screen.getAllByText('图片下载失败').length).toBeGreaterThan(0)
    expect(api.getScrapingItem).toHaveBeenCalledWith('item-1')
    expect(api.getScrapingItemLogs).toHaveBeenCalledWith('item-1')
  })

  it('refreshes only the open item after its log event', async () => {
    renderPage(<TaskDetailPage />)
    fireEvent.click(await screen.findByRole('button', { name: '详情' }))
    await screen.findByText('步骤时间线')
    await waitFor(() => expect(api.getScrapingItemLogs).toHaveBeenCalledTimes(1))
    const handler = vi.mocked(realtime.subscribeRealtime).mock.calls.find(([name]) => name === 'scraping.item.log.appended')?.[1]
    expect(handler).toBeTypeOf('function')

    act(() => handler?.({ resource_id: 'other-item', payload: {} } as never))
    expect(api.getScrapingItemLogs).toHaveBeenCalledTimes(1)

    act(() => handler?.({ resource_id: 'item-1', payload: {} } as never))
    await waitFor(() => expect(api.getScrapingItemLogs).toHaveBeenCalledTimes(2))

    const itemHandler = vi.mocked(realtime.subscribeRealtime).mock.calls.filter(([name]) => name === 'scraping.item.updated').at(-1)?.[1]
    const before = vi.mocked(api.getScrapingItem).mock.calls.length
    act(() => itemHandler?.({ resource_id: 'other-item', payload: {} } as never))
    expect(api.getScrapingItem).toHaveBeenCalledTimes(before)
    act(() => itemHandler?.({ resource_id: 'item-1', payload: {} } as never))
    await waitFor(() => expect(api.getScrapingItem).toHaveBeenCalledTimes(before + 1))
  })

  it('shows an empty log state for older items', async () => {
    vi.mocked(api.getScrapingItemLogs).mockResolvedValue([])
    renderPage(<TaskDetailPage />)
    fireEvent.click(await screen.findByRole('button', { name: '详情' }))

    expect(await screen.findByText('无日志')).toBeInTheDocument()
  })

  it('shows a log loading error separately from an empty history', async () => {
    vi.mocked(api.getScrapingItemLogs).mockRejectedValue(new Error('offline'))
    renderPage(<TaskDetailPage />)
    fireEvent.click(await screen.findByRole('button', { name: '详情' }))

    expect(await screen.findByText('日志加载失败')).toBeInTheDocument()
    expect(screen.queryByText('无日志')).not.toBeInTheDocument()
  })

  it('does not keep the previous item logs after switching items', async () => {
    const original = await api.getScrapingTask('task-1')
    const second = { ...original.items[0], id: 'item-2', movie_code: 'BBB-001' }
    vi.mocked(api.getScrapingTask).mockResolvedValue({ ...original, items: [...original.items, second] })
    vi.mocked(api.getScrapingItem).mockImplementation(async (id) => id === 'item-2' ? second : original.items[0])
    vi.mocked(api.getScrapingItemLogs).mockImplementation(async (id) => [
      { timestamp: '2026-10-22T13:00:00+00:00', level: 'INFO', message: id === 'item-2' ? '第二项日志' : '第一项日志', step: 'prepare' },
    ])
    renderPage(<TaskDetailPage />)
    fireEvent.click((await screen.findAllByRole('button', { name: '详情' }))[0])
    expect(await screen.findAllByText('第一项日志')).not.toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.click(screen.getAllByRole('button', { name: '详情' })[1])

    expect(await screen.findAllByText('第二项日志')).not.toHaveLength(0)
    expect(screen.queryByText('第一项日志')).not.toBeInTheDocument()
  })

  it('subscribes to task and item updates on the detail page', async () => {
    renderPage(<TaskDetailPage />)
    await screen.findAllByText('ADN-784')
    expect(realtime.subscribeRealtime).toHaveBeenCalledWith(
      'scraping.task.updated',
      expect.any(Function),
    )
    expect(realtime.subscribeRealtime).toHaveBeenCalledWith(
      'scraping.item.updated',
      expect.any(Function),
    )
  })

  it('follows the retried task after clicking 重试失败项', async () => {
    renderPage(<TaskDetailPage />)
    fireEvent.click(await screen.findByRole('button', { name: '重试失败项' }))

    await waitFor(() => expect(api.retryScrapingTask).toHaveBeenCalledWith('task-1'))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({
      to: '/scraping/tasks/$id',
      params: { id: 'task-2' },
    }))
    await waitFor(() => expect(vi.mocked(api.getScrapingTask).mock.calls.length).toBeGreaterThan(1))
  })
})
