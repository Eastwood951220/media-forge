import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageSubTaskDetailPage from '../StorageSubTaskDetailPage'

const subscribeRealtime = vi.fn()

vi.mock('@/api/storage/storageTasks', () => ({
  getStorageSubTask: vi.fn().mockResolvedValue({
    id: 'sub-1',
    main_task_id: 'main-1',
    movie_id: 'movie-1',
    movie_code: 'ABC-001',
    movie_title: 'Movie',
    status: 'running',
    step: 'prepare',
    storage_mode: 'single',
    selected_storage_location: '巨乳',
    target_locations: ['巨乳'],
    download_path: '/云下载/storage_sub-1',
    target_paths: [],
    magnet_attempts: [],
    current_magnet_id: null,
    current_magnet_url: '',
    renamed_files: [],
    moved_files: [],
    skipped_files: [],
    result: {},
  }),
  getStorageSubTaskLogs: vi.fn().mockResolvedValue([
    {
      timestamp: '2026-07-04T03:41:43.132033',
      level: 'INFO',
      message: '执行步骤: prepare',
      context: {},
      step: 'prepare',
      step_label: '准备任务',
      event: 'step_started',
    },
  ]),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: (eventName: string, handler: unknown) => {
    subscribeRealtime(eventName, handler)
    return () => {}
  },
}))

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ id: 'sub-1' }),
}))

describe('StorageSubTaskDetailPage timeline', () => {
  beforeEach(() => {
    subscribeRealtime.mockClear()
  })

  it('renders step timeline and appends only logs for the current subtask', async () => {
    render(<StorageSubTaskDetailPage />)

    expect(await screen.findByText('步骤时间线')).toBeInTheDocument()
    expect(screen.getByText('准备任务')).toBeInTheDocument()

    const logHandler = subscribeRealtime.mock.calls.find((call) => call[0] === 'storage.sub.log.appended')?.[1]
    expect(logHandler).toBeTypeOf('function')

    logHandler({
      resource_id: 'other-sub',
      payload: {
        timestamp: '2026-07-04T03:41:44.000000',
        level: 'INFO',
        message: '不应该显示',
        context: {},
        step: 'submit_magnet',
        step_label: '提交磁力',
      },
    })
    logHandler({
      resource_id: 'sub-1',
      payload: {
        timestamp: '2026-07-04T03:41:45.000000',
        level: 'INFO',
        message: '磁力链接已提交',
        context: {},
        step: 'submit_magnet',
        step_label: '提交磁力',
      },
    })

    await waitFor(() => {
      expect(screen.queryByText('不应该显示')).not.toBeInTheDocument()
      expect(screen.getByText('磁力链接已提交')).toBeInTheDocument()
    })
  })
})
