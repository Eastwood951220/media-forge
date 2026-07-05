import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageTaskListPage from '../StorageTaskListPage'
import { deleteStorageMainTask, listStorageMainTasks } from '@/api/storage/storageTasks'

vi.mock('@/api/storage/storageTasks', () => ({
  listStorageMainTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
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
}))

describe('StorageTaskListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders storage task list heading', () => {
    render(<StorageTaskListPage />)
    expect(screen.getByText('存储任务')).toBeInTheDocument()
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
        total: 1,
      })
      .mockResolvedValueOnce({ rows: [], total: 0 })

    render(<StorageTaskListPage />)

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
})
