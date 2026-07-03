import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskListPage from '../src/pages/crawler/tasks/TaskListPage'
import { getCrawlTaskStats, getCrawlTasks } from '../src/api/crawlTask'
import { runCrawlTask } from '../src/api/crawlerRun'
import { useTaskListQueryStore } from '../src/pages/crawler/tasks/useTaskListQueryStore'

vi.mock('../src/api/crawlTask', () => ({
  getCrawlTasks: vi.fn(),
  getCrawlTaskStats: vi.fn(),
  deleteCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('../src/api/crawlerRun', () => ({
  runCrawlTask: vi.fn(),
}))

function renderPage() {
  const rootRoute = createRootRoute({ component: () => <TaskListPage /> })
  const runsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/crawler/runs', component: () => <div>runs page</div> })
  const router = createRouter({
    routeTree: rootRoute.addChildren([runsRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('crawler task run controls', () => {
  beforeEach(() => {
    useTaskListQueryStore.getState().reset()
    vi.mocked(getCrawlTaskStats).mockResolvedValue({ total: 1, enabled: 1, disabled: 0 })
    vi.mocked(getCrawlTasks).mockResolvedValue({
      rows: [{
        id: 'task-1',
        name: '任务A',
        storage_location: 'A',
        urls: [],
        is_skip: false,
        status: 'pending',
        task_id: null,
        error_message: null,
        total_found: 0,
        total_qualified: 0,
        owner_id: 'user-1',
        created_at: '2026-07-02T00:00:00',
        updated_at: null,
        last_run_at: null,
        last_run_status: null,
      }],
      total: 1,
    })
    vi.mocked(runCrawlTask).mockResolvedValue({ id: 'run-1' } as never)
  })

  it('starts an incremental run from the crawl dropdown', async () => {
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: '爬取' }))
    await userEvent.click(await screen.findByText('增量爬取'))

    await waitFor(() => {
      expect(runCrawlTask).toHaveBeenCalledWith('task-1', 'incremental')
    })
  })
})
