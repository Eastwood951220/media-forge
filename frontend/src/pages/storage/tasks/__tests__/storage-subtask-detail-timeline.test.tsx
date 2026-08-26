import { act, render, screen, waitFor } from '@testing-library/react'
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
    moved_files: [
      {
        name: 'ACZD-165.mp4',
        path: '/Downloads/storage_sub-1/attempt_01_m1/ACZD-165.mp4',
        renamed_name: 'ACZD-165-C.mp4',
        renamed_path: '/Downloads/storage_sub-1/attempt_01_m1/ACZD-165-C.mp4',
        moved_path: '/Movies/巨乳/ACZD-165-C/ACZD-165-C.mp4',
        copied_paths: ['/Movies/中文字幕/ACZD-165-C/ACZD-165-C.mp4'],
      },
    ],
    skipped_files: [
      {
        name: 'sample.mp4',
        path: '/Downloads/storage_sub-1/sample.mp4',
        skip_reason: 'rename_failed',
      },
    ],
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
    {
      timestamp: '2026-07-04T03:42:01.000000',
      level: 'INFO',
      message: '重命名: first.mp4 → ACZD-165-CD1.mp4',
      context: {},
      step: 'rename_files',
      step_label: '重命名',
    },
    {
      timestamp: '2026-07-04T03:42:02.000000',
      level: 'INFO',
      message: '重命名: second.mp4 → ACZD-165-CD2.mp4',
      context: {},
      step: 'rename_files',
      step_label: '重命名',
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
    expect(screen.getByText(/11:41:43 执行步骤: prepare/)).toBeInTheDocument()
    expect(screen.getByText(/11:42:01 重命名: first\.mp4 → ACZD-165-CD1\.mp4/)).toBeInTheDocument()
    expect(screen.getByText(/11:42:02 重命名: second\.mp4 → ACZD-165-CD2\.mp4/)).toBeInTheDocument()
    expect(screen.getByText('11:41:43')).toBeInTheDocument()
    expect(screen.getByText('ACZD-165-C.mp4')).toBeInTheDocument()
    expect(screen.getByText('/Movies/巨乳/ACZD-165-C/ACZD-165-C.mp4')).toBeInTheDocument()
    expect(screen.getByText('/Movies/中文字幕/ACZD-165-C/ACZD-165-C.mp4')).toBeInTheDocument()
    expect(screen.getByText('重命名失败')).toBeInTheDocument()
    expect(screen.queryByText(/"moved_path"/)).not.toBeInTheDocument()

    const logHandler = subscribeRealtime.mock.calls.find((call) => call[0] === 'storage.sub.log.appended')?.[1]
    expect(logHandler).toBeTypeOf('function')

    act(() => {
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
    })

    await waitFor(() => {
      expect(screen.queryByText('不应该显示')).not.toBeInTheDocument()
      expect(screen.getByText('磁力链接已提交')).toBeInTheDocument()
    })
  })
})
