import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DashboardOverview } from '../src/api/dashboard/types'
import DashboardPage from '../src/pages/dashboard/DashboardPage'

const refreshMock = vi.fn()

const overview: DashboardOverview = {
  system_status: 'healthy',
  refreshed_at: '2026-07-14T00:00:00Z',
  crawler: {
    task_stats: { total: 2, enabled: 1, disabled: 1 },
    runtime_stats: { total: 2, idle: 1, running: 1, queued: 0, stopped: 0 },
    queue: { queue_size: 0, is_running: true, current_run_id: 'run-1', stop_requested: false },
  },
  runs: {
    status_distribution: [{ status: 'completed', count: 2 }],
    daily_trend: [{ date: '2026-07-14', completed: 2, failed: 0 }],
    recent: [],
  },
  content: {
    movie_total: 10,
    storage_status: { stored: 6, storing: 1, not_stored: 3 },
    rankings: {
      total: {
        actors: [{ name: '演员A', count: 6 }],
        makers: [{ name: '片商A', count: 4 }],
        tags: [{ name: '标签A', count: 5 }],
        series: [{ name: '系列A', count: 3 }],
      },
      recent_storage: {
        actors: [{ name: '演员B', count: 2 }],
        makers: [{ name: '片商B', count: 2 }],
        tags: [{ name: '标签B', count: 2 }],
        series: [{ name: '系列B', count: 1 }],
      },
      recent_created: {
        actors: [{ name: '演员C', count: 3 }],
        makers: [{ name: '片商C', count: 2 }],
        tags: [{ name: '标签C', count: 3 }],
        series: [{ name: '系列C', count: 1 }],
      },
    },
  },
  storage: {
    task_status_distribution: [{ status: 'completed', count: 1 }],
    recent_tasks: [],
    index: {
      target_folder: '/media',
      status: 'completed',
      category_count: 2,
      code_folder_count: 10,
      video_count: 10,
      completed_at: '2026-07-14T00:00:00Z',
      errors: [],
    },
  },
  alerts: [],
  partial_errors: [],
}

let hookState: {
  data: DashboardOverview | null
  loading: boolean
  error: Error | null
  refreshing: boolean
  fetchOverview: ReturnType<typeof vi.fn>
  refresh: ReturnType<typeof vi.fn>
} = {
  data: overview,
  loading: false,
  error: null,
  refreshing: false,
  fetchOverview: vi.fn(),
  refresh: refreshMock,
}

vi.mock('../src/pages/dashboard/hooks/useDashboardOverview', () => ({
  useDashboardOverview: () => hookState,
}))

vi.mock('../src/pages/dashboard/components/DashboardCharts', () => ({
  DashboardCharts: () => <div data-testid="dashboard-charts">charts</div>,
}))

describe('DashboardPage runtime overview', () => {
  beforeEach(() => {
    refreshMock.mockClear()
    hookState = {
      data: overview,
      loading: false,
      error: null,
      refreshing: false,
      fetchOverview: vi.fn(),
      refresh: refreshMock,
    }
  })

  it('renders runtime overview metrics from data', () => {
    render(<DashboardPage />)

    expect(screen.getByRole('heading', { name: '运行态总览' })).toBeInTheDocument()
    expect(screen.getByText('采集队列')).toBeInTheDocument()
    expect(screen.getByText('任务配置')).toBeInTheDocument()
    expect(screen.getByText('影片库')).toBeInTheDocument()
    expect(screen.getByText('存储索引')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '内容排名' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: '总排名' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: '最近存储' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: '最近入库' })).toBeInTheDocument()
    expect(screen.getByText('演员A')).toBeInTheDocument()
    expect(screen.getByText('暂无需要关注的问题')).toBeInTheDocument()
    expect(screen.queryByText('Operations Console')).not.toBeInTheDocument()
  })

  it('renders request failure and retries', () => {
    hookState = {
      ...hookState,
      data: null,
      error: new Error('dashboard failed'),
    }

    render(<DashboardPage />)

    expect(screen.getByText('首页数据加载失败')).toBeInTheDocument()
    const retryButton = screen.getByRole('button', { name: /重.*试/ })
    fireEvent.click(retryButton)
    expect(refreshMock).toHaveBeenCalledTimes(1)
  })
})
