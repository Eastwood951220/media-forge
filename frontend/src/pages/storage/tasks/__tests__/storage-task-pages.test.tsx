import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import StorageTaskListPage from '../StorageTaskListPage'

vi.mock('@/api/storage/storageTasks', () => ({
  listStorageMainTasks: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
  stopStorageMainTask: vi.fn(),
  restartStorageMainTask: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: vi.fn().mockReturnValue(() => {}),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: vi.fn().mockReturnValue(vi.fn()),
}))

describe('StorageTaskListPage', () => {
  it('renders storage task list heading', () => {
    render(<StorageTaskListPage />)
    expect(screen.getByText('存储任务')).toBeInTheDocument()
  })
})
