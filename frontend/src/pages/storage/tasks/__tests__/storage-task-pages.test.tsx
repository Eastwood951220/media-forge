import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageTaskListPage from '../StorageTaskListPage'
import StorageTaskDetailPage from '../StorageTaskDetailPage'
import { deleteStorageMainTask, listStorageMainTasks } from '@/api/storage/storageTasks'

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
    vi.mocked(listStorageMainTasks).mockResolvedValue({ rows: [], page: 1, size: 20, has_more: false } as any)
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
      } as any)
      .mockResolvedValueOnce({ rows: [], page: 1, size: 20, has_more: false } as any)

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
    } as any)

    render(<StorageTaskListPage />, { wrapper })

    expect(await screen.findByText('任务列表')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('云存储_列表测试')).toBeInTheDocument()
    })
    // Check for the progress column header
    expect(screen.getByRole('columnheader', { name: '处理进度' })).toBeInTheDocument()
  })
})
