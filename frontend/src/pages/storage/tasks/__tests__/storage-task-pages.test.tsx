import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageTaskListPage from '../StorageTaskListPage'
import StorageTaskDetailPage from '../StorageTaskDetailPage'
import { StorageMainTaskTable } from '../components/StorageMainTaskTable'
import { countStorageMainTasks, deleteStorageMainTask, getStorageMainTask, listStorageMainTasks, listStorageSubTasks, retryStorageSubTask } from '@/api/storage/storageTasks'

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

vi.mock('@/api/storage/storageTasks', () => ({
  listStorageMainTasks: vi.fn().mockResolvedValue({ rows: [], page: 1, size: 20, has_more: false }),
  countStorageMainTasks: vi.fn().mockResolvedValue({ total: 0 }),
  getStorageMainTask: vi.fn().mockResolvedValue({
    id: 'task-detail-1',
    alias: '云存储_详情测试',
    display_name: '云存储_详情测试',
    source: 'batch',
    storage_mode: 'multiple',
    status: 'running',
    total_count: 10,
    success_count: 6,
    failed_count: 1,
    skipped_count: 2,
    created_at: '2026-07-10T01:00:00Z',
    finished_at: null,
  }),
  listStorageSubTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  stopStorageMainTask: vi.fn(),
  restartStorageMainTask: vi.fn(),
  retryStorageSubTask: vi.fn(),
  deleteStorageMainTask: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn().mockReturnValue(() => {}),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: vi.fn().mockReturnValue(vi.fn()),
  useParams: vi.fn().mockReturnValue({ id: 'task-detail-1' }),
}))

describe('StorageTaskListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    vi.mocked(listStorageMainTasks).mockResolvedValue({ rows: [], page: 1, size: 20, has_more: false } as never)
    vi.mocked(countStorageMainTasks).mockResolvedValue({ total: 0 } as never)
  })

  it('renders storage task list heading', () => {
    render(<StorageTaskListPage />, { wrapper })
    expect(screen.getByText('任务列表')).toBeInTheDocument()
  })

  it('deletes a completed storage task after confirmation', async () => {
    vi.mocked(listStorageMainTasks)
      .mockResolvedValueOnce({
        rows: [
          {
            id: 'task-delete-1',
            alias: '云存储_删除测试',
            display_name: '云存储_删除测试',
            source: 'single',
            storage_mode: 'single',
            status: 'completed',
            total_count: 1,
            success_count: 1,
            failed_count: 0,
            skipped_count: 0,
            created_at: '2026-07-05T00:00:00Z',
          },
        ],
        page: 1,
        size: 20,
        has_more: false,
      } as never)
      .mockResolvedValueOnce({ rows: [], page: 1, size: 20, has_more: false } as never)

    render(<StorageTaskListPage />, { wrapper })

    expect(await screen.findByText('云存储_删除测试')).toBeInTheDocument()
    const deleteButton = screen.getByText('删除')
    fireEvent.click(deleteButton)

    // Wait for Popconfirm to appear and click OK
    await waitFor(() => {
      const okButton = document.querySelector('.ant-popconfirm-buttons .ant-btn-primary')
      if (okButton) {
        fireEvent.click(okButton)
      }
    })

    await waitFor(() => {
      expect(deleteStorageMainTask).toHaveBeenCalledWith('task-delete-1')
    })
    await waitFor(() => {
      expect(listStorageMainTasks).toHaveBeenCalledTimes(2)
    })
  })

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

  it('renders storage task list with progress-focused table copy', async () => {
    vi.mocked(listStorageMainTasks).mockResolvedValue({
      rows: [
        {
          id: 'task-list-1',
          alias: '云存储_列表测试',
          display_name: '云存储_列表测试',
          source: 'batch',
          storage_mode: 'multiple',
          status: 'running',
          total_count: 4,
          success_count: 2,
          failed_count: 1,
          skipped_count: 0,
          created_at: '2026-07-10T01:00:00Z',
        },
      ],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

    render(<StorageTaskListPage />, { wrapper })

    expect(await screen.findByText('任务列表')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('云存储_列表测试')).toBeInTheDocument()
    })
    // Check for the progress column header
    expect(screen.getByRole('columnheader', { name: '处理进度' })).toBeInTheDocument()
  })

  it('keeps pagination and refreshes that page when the storage task list is mounted again', async () => {
    vi.mocked(countStorageMainTasks).mockResolvedValue({ total: 120 } as never)
    vi.mocked(listStorageMainTasks).mockResolvedValue({
      rows: [{
        id: 'task-page-1',
        alias: '云存储_分页测试',
        display_name: '云存储_分页测试',
        source: 'batch',
        storage_mode: 'single',
        status: 'completed',
        total_count: 1,
        success_count: 1,
        failed_count: 0,
        skipped_count: 0,
        created_at: '2026-09-08T00:00:00Z',
      }],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

    const { unmount } = render(<StorageTaskListPage />, { wrapper })

    await screen.findByText('云存储_分页测试')
    fireEvent.click(screen.getByTitle('2'))
    await waitFor(() => expect(listStorageMainTasks).toHaveBeenCalledWith({ page: 2, size: 20 }))

    unmount()
    render(<StorageTaskListPage />, { wrapper })

    await waitFor(() => expect(listStorageMainTasks).toHaveBeenLastCalledWith({ page: 2, size: 20 }))
  })

  it('allocates enough progress column space for long storage counts', () => {
    const { container } = render(
      <StorageMainTaskTable
        tasks={[{
          id: 'task-wide-progress',
          alias: '云存储_长进度',
          display_name: '云存储_长进度',
          source: 'batch',
          storage_mode: 'single',
          status: 'completed',
          total_count: 12345,
          success_count: 12344,
          failed_count: 1,
          skipped_count: 0,
          created_at: '2026-09-07T00:00:00Z',
        }]}
        loading={false}
        total={1}
        current={1}
        pageSize={20}
        onStop={vi.fn()}
        onRestart={vi.fn()}
        onDelete={vi.fn()}
        onRefresh={vi.fn()}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
      { wrapper },
    )

    expect(screen.getByText('成功 12344')).toBeInTheDocument()
    expect(container.querySelector('col[style*="width: 340px"]')).toBeInTheDocument()
  })

  it('does not mark mixed completed storage progress as exception', async () => {
    vi.mocked(listStorageMainTasks).mockResolvedValue({
      rows: [{
        id: 'task-mixed-1',
        alias: '云存储_部分失败',
        display_name: '云存储_部分失败',
        source: 'batch',
        storage_mode: 'single',
        status: 'completed',
        total_count: 27,
        success_count: 26,
        failed_count: 1,
        skipped_count: 0,
        created_at: '2026-09-07T00:00:00Z',
      }],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

    render(<StorageTaskListPage />, { wrapper })

    expect(await screen.findByText('云存储_部分失败')).toBeInTheDocument()
    expect(document.querySelector('.ant-progress-status-exception')).not.toBeInTheDocument()
    expect(screen.getByText('失败 1').className).toContain('tableProgressErrorMeta')
  })

  it('shows retry only for failed storage subtasks and retries that subtask', async () => {
    vi.mocked(listStorageSubTasks).mockResolvedValue({
      rows: [
        { id: 'sub-failed', main_task_id: 'task-detail-1', movie_id: 'movie-1', movie_code: 'AAA-001', movie_title: 'A', status: 'failed', step: 'waiting_download' },
        { id: 'sub-ok', main_task_id: 'task-detail-1', movie_id: 'movie-2', movie_code: 'BBB-002', movie_title: 'B', status: 'completed', step: 'done' },
      ],
      total: 2,
    } as never)
    vi.mocked(retryStorageSubTask).mockResolvedValue({ id: 'sub-failed', status: 'queued' } as never)

    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    const retryButtons = screen.getAllByRole('button', { name: /重试/ })
    expect(retryButtons).toHaveLength(1)
    fireEvent.click(retryButtons[0])

    await waitFor(() => expect(retryStorageSubTask).toHaveBeenCalledWith('sub-failed'))
  })

  it('does not mark completed mixed storage detail progress as exception', async () => {
    vi.mocked(getStorageMainTask).mockResolvedValue({
      id: 'task-detail-mixed-1',
      alias: '云存储_详情部分失败',
      display_name: '云存储_详情部分失败',
      source: 'batch',
      storage_mode: 'single',
      status: 'completed',
      total_count: 27,
      success_count: 26,
      failed_count: 1,
      skipped_count: 0,
      created_at: '2026-09-07T00:00:00Z',
      finished_at: '2026-09-07T01:00:00Z',
    } as never)

    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('云存储_详情部分失败')).toBeInTheDocument()
    expect(document.querySelector('.ant-progress-status-exception')).not.toBeInTheDocument()
  })
})
