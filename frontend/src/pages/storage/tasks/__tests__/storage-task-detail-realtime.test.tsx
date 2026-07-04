import { render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageTaskDetailPage from '../StorageTaskDetailPage'
import type { RealtimeEventName, RealtimeHandler } from '@/realtime/types'

const realtimeHandlers = new Map<string, Set<RealtimeHandler>>()

vi.mock('@/api/storage/storageTasks', () => ({
  getStorageMainTask: vi.fn().mockResolvedValue({
    id: 'main-1',
    alias: 'task-alias',
    display_name: 'task-alias',
    source: 'single',
    storage_mode: 'single',
    status: 'queued',
    total_count: 2,
    success_count: 0,
    failed_count: 0,
    skipped_count: 0,
    created_at: '2026-07-04T00:00:00Z',
    started_at: null,
    finished_at: null,
    error_message: null,
  }),
  listStorageSubTasks: vi.fn().mockResolvedValue({
    rows: [
      {
        id: 'sub-1',
        main_task_id: 'main-1',
        movie_id: 'movie-1',
        movie_code: 'ABC-001',
        movie_title: 'Movie 1',
        status: 'queued',
        step: 'prepare',
        storage_mode: 'single',
        selected_storage_location: null,
        target_locations: ['A'],
        download_path: '',
        target_paths: [],
        magnet_attempts: [],
        current_magnet_id: null,
        current_magnet_url: '',
        renamed_files: [],
        moved_files: [],
        skipped_files: [],
        result: {},
      },
      {
        id: 'sub-2',
        main_task_id: 'main-1',
        movie_id: 'movie-2',
        movie_code: 'ABC-002',
        movie_title: 'Movie 2',
        status: 'queued',
        step: 'prepare',
        storage_mode: 'single',
        selected_storage_location: null,
        target_locations: ['A'],
        download_path: '',
        target_paths: [],
        magnet_attempts: [],
        current_magnet_id: null,
        current_magnet_url: '',
        renamed_files: [],
        moved_files: [],
        skipped_files: [],
        result: {},
      },
    ],
    total: 2,
  }),
  stopStorageMainTask: vi.fn(),
  restartStorageMainTask: vi.fn(),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(() => null),
  subscribeRealtime: vi.fn((eventName: RealtimeEventName, handler: RealtimeHandler) => {
    const handlers = realtimeHandlers.get(eventName) ?? new Set()
    handlers.add(handler)
    realtimeHandlers.set(eventName, handlers)
    return () => handlers.delete(handler)
  }),
}))

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ id: 'main-1' }),
  useNavigate: vi.fn().mockReturnValue(vi.fn()),
}))

function emit(eventName: RealtimeEventName, payload: Record<string, unknown>, resourceId: string | null = 'main-1') {
  for (const handler of realtimeHandlers.get(eventName) ?? []) {
    handler({
      id: `event-${Date.now()}`,
      event: eventName,
      scope: eventName.startsWith('storage.sub') ? 'storage.sub' : 'storage.main',
      resource_id: resourceId,
      owner_id: 'user-1',
      payload,
      created_at: '2026-07-04T00:00:00Z',
    })
  }
}

function descriptionValue(label: string): HTMLElement {
  const labelNodes = screen.getAllByText(label)
  const labelNode = labelNodes.find((node) => (node as HTMLElement).closest('.ant-descriptions-item'))
  if (!labelNode) throw new Error(`Missing description item for ${label}`)
  const item = (labelNode as HTMLElement).closest('.ant-descriptions-item')
  if (!item) throw new Error(`Missing description item for ${label}`)
  return item as HTMLElement
}

describe('StorageTaskDetailPage realtime updates', () => {
  beforeEach(() => {
    realtimeHandlers.clear()
  })

  it('updates header counts and subtask row from realtime events', async () => {
    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('存储任务详情 - task-alias')).toBeInTheDocument()
    expect(screen.getByText('ABC-001')).toBeInTheDocument()

    emit('storage.main.updated', {
      id: 'main-1',
      status: 'running',
      total_count: 2,
      success_count: 1,
      failed_count: 0,
      skipped_count: 1,
    })

    emit('storage.sub.updated', {
      id: 'sub-1',
      main_task_id: 'main-1',
      movie_id: 'movie-1',
      status: 'completed',
      step: 'done',
      error_message: null,
    }, 'sub-1')

    await waitFor(() => {
      expect(within(descriptionValue('状态')).getByText('运行中')).toBeInTheDocument()
      expect(within(descriptionValue('成功')).getByText('1')).toBeInTheDocument()
      expect(within(descriptionValue('跳过')).getByText('1')).toBeInTheDocument()
      const row = screen.getByText('ABC-001').closest('tr')
      if (!row) throw new Error('Missing ABC-001 row')
      expect(within(row).getByText('已完成')).toBeInTheDocument()
      expect(within(row).getByText('done')).toBeInTheDocument()
    })
  })

  it('ignores subtask events for other main tasks', async () => {
    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('ABC-002')).toBeInTheDocument()

    emit('storage.sub.updated', {
      id: 'sub-other',
      main_task_id: 'other-main',
      movie_id: 'movie-other',
      status: 'completed',
      step: 'done',
      error_message: null,
    }, 'sub-other')

    await waitFor(() => {
      expect(screen.queryByText('sub-other')).not.toBeInTheDocument()
      const row = screen.getByText('ABC-002').closest('tr')
      if (!row) throw new Error('Missing ABC-002 row')
      expect(within(row).getByText('排队中')).toBeInTheDocument()
    })
  })
})
