import { App as AntApp } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../TaskListPage'
import TaskDetailPage from '../TaskDetailPage'
import * as api from '@/api/scraping/scrapingTasks'

vi.mock('@/api/scraping/scrapingTasks', () => ({
  listScrapingTasks: vi.fn(),
  getScrapingTask: vi.fn(),
  createScrapingTask: vi.fn(),
  cancelScrapingTask: vi.fn(),
  retryScrapingTask: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  subscribeRealtime: vi.fn(() => vi.fn()),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
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
})
