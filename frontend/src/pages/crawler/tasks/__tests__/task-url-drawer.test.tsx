import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { PropsWithChildren } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TaskFormPage from '../TaskFormPage'
import {
  createCrawlTask,
  extractTaskName,
  getCrawlTask,
  updateCrawlTask,
} from '@/api/crawler/crawlTask'

const navigateMock = vi.fn()
let paramsMock: { id?: string } = {}

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
    select({ location: { pathname: paramsMock.id ? `/crawler/tasks/${paramsMock.id}/edit` : '/crawler/tasks/new', searchStr: '' } }),
}))

vi.mock('@/api/crawler/crawlTask', () => ({
  createCrawlTask: vi.fn(),
  extractTaskName: vi.fn(),
  getCrawlTask: vi.fn(),
  updateCrawlTask: vi.fn(),
}))

vi.mock('@/api/queryInvalidation', () => ({
  invalidateCrawlerTaskLists: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/layout/routeCache', () => ({
  useRouteCacheControl: () => ({ destroy: vi.fn().mockResolvedValue(undefined) }),
}))

vi.mock('@/stores/useTagsViewStore', () => ({
  useTagsViewStore: Object.assign(
    vi.fn((selector: (state: unknown) => unknown) => selector({ removeSelectedView: vi.fn(), visitedViews: [] })),
    {
      getState: () => ({ visitedViews: [], removeSelectedView: vi.fn() }),
    },
  ),
}))

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <App>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </App>
  )
}

const existingTask = {
  id: 'task-1',
  name: 'Existing Task',
  storage_location: 'Existing Task',
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
  urls: [
    {
      id: 'url-1',
      url: 'https://javdb.com/actors/alpha',
      url_type: 'actors',
      has_magnet: true,
      has_chinese_sub: false,
      sort_type: 0,
      url_name: 'Alpha',
    },
    {
      id: 'url-2',
      url: 'https://javdb.com/series/beta',
      url_type: 'series',
      has_magnet: false,
      has_chinese_sub: true,
      sort_type: 0,
      url_name: 'Beta',
    },
  ],
}

const emptyUrlTask = {
  id: 'task-empty',
  name: 'Empty URL Task',
  storage_location: 'Empty URL Task',
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
  urls: [],
}

async function renderEditPage(task: typeof existingTask = existingTask) {
  paramsMock = { id: 'task-1' }
  vi.mocked(getCrawlTask).mockResolvedValue(task as never)
  render(<TaskFormPage />, { wrapper })
  await screen.findByLabelText('任务名称')
}

async function switchToTableMode() {
  fireEvent.click(screen.getByRole('button', { name: /列表/ }))
  await screen.findByRole('columnheader', { name: '最终 URL' })
}

describe('TaskFormPage URL table drawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    paramsMock = {}
    navigateMock.mockResolvedValue(undefined)
    vi.mocked(createCrawlTask).mockResolvedValue({ id: 'created-task' } as never)
    vi.mocked(updateCrawlTask).mockResolvedValue({ id: 'task-1' } as never)
    vi.mocked(extractTaskName).mockResolvedValue({ name: 'Fetched Name' })
  })

  it('opens a drawer from table-mode add and appends the saved URL row with an auto-fetched name', async () => {
    await renderEditPage()
    await switchToTableMode()

    fireEvent.click(screen.getByRole('button', { name: /添加 URL/ }))
    const drawer = await screen.findByRole('dialog', { name: '添加 URL' })

    await userEvent.type(within(drawer).getByLabelText('URL'), 'https://javdb.com/actors/new-person')
    fireEvent.click(await screen.findByText('保 存'))

    await waitFor(() => {
      expect(extractTaskName).toHaveBeenCalledWith('https://javdb.com/actors/new-person', 'actors')
    })
    expect(await screen.findByText('Fetched Name')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '添加 URL' })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: '最终 URL' })).toBeInTheDocument()
  })

  it('edits a table row through the drawer without switching out of table mode', async () => {
    await renderEditPage()
    await switchToTableMode()

    const firstRow = screen.getByRole('row', { name: /Alpha/ })
    fireEvent.click(within(firstRow).getByRole('button', { name: /编辑/ }))
    const drawer = await screen.findByRole('dialog', { name: '编辑 URL' })

    const input = within(drawer).getByLabelText('URL')
    await userEvent.clear(input)
    await userEvent.type(input, 'https://javdb.com/series/changed')
    fireEvent.click(await screen.findByText('保 存'))

    expect(await screen.findByText('https://javdb.com/series/changed')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: '最终 URL' })).toBeInTheDocument()
  })

  it('keeps table-mode delete visible and disables deletion for the final URL', async () => {
    await renderEditPage()
    await switchToTableMode()

    expect(screen.getAllByRole('button', { name: /删除/ })).toHaveLength(2)
    fireEvent.click(screen.getAllByRole('button', { name: /删除/ })[0])

    await waitFor(() => {
      expect(screen.queryByText('Alpha')).not.toBeInTheDocument()
    })
    const finalDelete = screen.getByRole('button', { name: /删除/ })
    expect(finalDelete).toBeDisabled()
  })

  it('auto-fetches missing URL names during whole-task create submit in card mode', async () => {
    paramsMock = {}
    vi.mocked(extractTaskName).mockResolvedValue({ name: 'Created Actor' })

    render(<TaskFormPage />, { wrapper })

    await userEvent.type(screen.getByLabelText('任务名称'), 'Manual Task')
    await userEvent.type(screen.getByLabelText('网盘路径'), 'Manual Task')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/create-person')
    fireEvent.click(await screen.findByText('创 建'))

    await waitFor(() => {
      expect(extractTaskName).toHaveBeenCalledWith('https://javdb.com/actors/create-person', 'actors')
    })
    await waitFor(() => {
      expect(createCrawlTask).toHaveBeenCalledWith(expect.objectContaining({
        urls: [expect.objectContaining({ url_name: 'Created Actor' })],
      }))
    })
  })

  it('submits existing table-mode URLs instead of clearing task URL rows', async () => {
    await renderEditPage()
    await switchToTableMode()

    fireEvent.click(await screen.findByText('更 新'))

    await waitFor(() => {
      expect(updateCrawlTask).toHaveBeenCalledWith(
        'task-1',
        expect.objectContaining({
          urls: [
            expect.objectContaining({
              id: 'url-1',
              url: 'https://javdb.com/actors/alpha',
              url_type: 'actors',
              has_magnet: true,
              has_chinese_sub: false,
              sort_type: 0,
              url_name: 'Alpha',
            }),
            expect.objectContaining({
              id: 'url-2',
              url: 'https://javdb.com/series/beta',
              url_type: 'series',
              has_magnet: false,
              has_chinese_sub: true,
              sort_type: 0,
              url_name: 'Beta',
            }),
          ],
        }),
      )
    })
  })

  it('blocks edit submit when normalized URL list is empty', async () => {
    await renderEditPage(emptyUrlTask)

    fireEvent.click(await screen.findByText('更 新'))

    await waitFor(() => {
      expect(screen.getByText('请至少保留一个 URL')).toBeInTheDocument()
    })
    expect(updateCrawlTask).not.toHaveBeenCalled()
  })
})