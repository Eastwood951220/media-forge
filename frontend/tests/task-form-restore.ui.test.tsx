import { App as AntApp } from 'antd'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskFormPage from '../src/pages/crawler/tasks/TaskFormPage'
import { createCrawlTask, extractTaskName, getCrawlTask, updateCrawlTask } from '../src/api/crawlTask'

vi.mock('../src/api/crawlTask', () => ({
  createCrawlTask: vi.fn(),
  extractTaskName: vi.fn(),
  getCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

function renderForm() {
  const rootRoute = createRootRoute({
    component: () => (
      <AntApp>
        <TaskFormPage />
      </AntApp>
    ),
  })
  const formRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([formRoute]),
    history: createMemoryHistory({ initialEntries: ['/crawler/tasks/new'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('TaskFormPage restored crawler task form', () => {
  beforeEach(() => {
    vi.mocked(createCrawlTask).mockResolvedValue({} as never)
    vi.mocked(updateCrawlTask).mockResolvedValue({} as never)
    vi.mocked(getCrawlTask).mockResolvedValue({} as never)
    vi.mocked(extractTaskName).mockResolvedValue({ name: '演员 A' })
  })

  it('creates a task with restored url entry payload', async () => {
    renderForm()

    await userEvent.type(await screen.findByLabelText('任务名称'), '每日演员任务')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/abc')
    await userEvent.click(screen.getByRole('switch', { name: '含磁力链接' }))

    // Find the submit button by its htmlType
    const submitButton = document.querySelector('button[type="submit"]')
    expect(submitButton).toBeTruthy()
    await userEvent.click(submitButton!)

    await waitFor(() => {
      expect(createCrawlTask).toHaveBeenCalledWith({
        name: '每日演员任务',
        is_skip: false,
        urls: [
          {
            url: 'https://javdb.com/actors/abc',
            url_type: 'actors',
            has_magnet: false,
            has_chinese_sub: false,
            sort_type: 0,
            url_name: '演员 A',
          },
        ],
      })
    })
  })

  it('stores manually extracted url_name in create payload', async () => {
    renderForm()

    await userEvent.type(await screen.findByLabelText('任务名称'), '巨乳')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/QV49G')

    // Wait for URL type to be detected and button to appear
    const extractButton = await screen.findByText('获取名称')
    await waitFor(() => {
      expect(extractButton).not.toBeDisabled()
    })
    await userEvent.click(extractButton)

    await waitFor(() => {
      expect(extractTaskName).toHaveBeenCalledWith('https://javdb.com/actors/QV49G', 'actors')
    })

    const submitButton = document.querySelector('button[type="submit"]')
    expect(submitButton).toBeTruthy()
    await userEvent.click(submitButton!)

    await waitFor(() => {
      expect(createCrawlTask).toHaveBeenCalledWith({
        name: '巨乳',
        is_skip: false,
        urls: [
          {
            url: 'https://javdb.com/actors/QV49G',
            url_type: 'actors',
            has_magnet: true,
            has_chinese_sub: false,
            sort_type: 0,
            url_name: '演员 A',
          },
        ],
      })
    })
  })

  it('auto extracts missing url_name before creating a task', async () => {
    renderForm()

    await userEvent.type(await screen.findByLabelText('任务名称'), '巨乳')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/QV49G')

    // Wait for URL type to be detected
    const extractButton = await screen.findByText('获取名称')
    await waitFor(() => {
      expect(extractButton).not.toBeDisabled()
    })

    const submitButton = document.querySelector('button[type="submit"]')
    expect(submitButton).toBeTruthy()
    await userEvent.click(submitButton!)

    await waitFor(() => {
      expect(extractTaskName).toHaveBeenCalledWith('https://javdb.com/actors/QV49G', 'actors')
      expect(createCrawlTask).toHaveBeenCalledWith({
        name: '巨乳',
        is_skip: false,
        urls: [
          {
            url: 'https://javdb.com/actors/QV49G',
            url_type: 'actors',
            has_magnet: true,
            has_chinese_sub: false,
            sort_type: 0,
            url_name: '演员 A',
          },
        ],
      })
    })
  })
})
