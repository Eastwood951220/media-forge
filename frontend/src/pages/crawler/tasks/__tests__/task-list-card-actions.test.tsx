import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListCards from '../components/TaskListCards'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

const baseTask = {
  id: 'task-1',
  name: 'Aligned Task',
  storage_location: 'Aligned Task',
  urls: [{ id: 'url-1', url: 'https://javdb.com/actors/a', url_type: 'actors', url_name: 'A' }],
  is_skip: false,
  status: 'idle',
  task_id: null,
  error_message: null,
  total_found: 0,
  total_qualified: 0,
  owner_id: 'owner-1',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
  last_run_at: null,
  last_run_status: null,
}

describe('TaskListCards action alignment', () => {
  beforeEach(() => {
    useCrawlerRuntimeStore.getState().reset()
  })

  it('renders primary and maintenance action groups for task cards', () => {
    const { container } = render(
      <TaskListCards
        tasks={[baseTask as any]}
        loading={false}
        total={1}
        runtimeByTaskId={{ 'task-1': { task_id: 'task-1', runtime_status: 'idle', latest_run_id: null, latest_run_status: null, last_run_at: null } } as any}
        runtimeReady={true}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleSkip={vi.fn()}
        onRun={vi.fn()}
        onStop={vi.fn()}
        onRestart={vi.fn()}
        onUrlRun={vi.fn()}
        onTemporaryTaskClick={vi.fn()}
        current={1}
        pageSize={20}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    )

    expect(screen.getAllByRole('button', { name: /爬取/ }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('button', { name: /URL 爬取/ })).toBeInTheDocument()
    expect(container.querySelector('[class*="taskCardPrimaryActions"]')).toBeTruthy()
    expect(container.querySelector('[class*="taskCardMaintenanceActions"]')).toBeTruthy()
  })

  it('shows sync tag and disables actions when runtime is not ready', () => {
    render(
      <TaskListCards
        tasks={[baseTask as any]}
        loading={false}
        total={1}
        runtimeByTaskId={{}}
        runtimeReady={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onToggleSkip={vi.fn()}
        onRun={vi.fn()}
        onStop={vi.fn()}
        onRestart={vi.fn()}
        onUrlRun={vi.fn()}
        onTemporaryTaskClick={vi.fn()}
        current={1}
        pageSize={20}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    )

    expect(screen.getByText('同步中')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /爬取/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /URL 爬取/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /编辑/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /删除/ })).not.toBeInTheDocument()
  })
})