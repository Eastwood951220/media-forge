import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { TagsView } from '../src/layout/TagsView'
import type { RouteCacheControl } from '../src/layout/routeCache'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

function createCacheControl(): RouteCacheControl {
  return {
    destroy: vi.fn().mockResolvedValue(undefined),
    destroyMany: vi.fn().mockResolvedValue(undefined),
    destroyOther: vi.fn().mockResolvedValue(undefined),
    destroyAll: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn(),
  }
}

function renderTagsView(initialPath: string, cacheControl = createCacheControl()) {
  const rootRoute = createRootRoute({
    component: () => <TagsView cacheControl={cacheControl} />,
  })
  const dashboardRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => null,
  })
  const taskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks',
    component: () => null,
  })
  const newTaskRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/tasks/new',
    component: () => null,
  })
  const configRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/crawler/config',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([dashboardRoute, taskRoute, newTaskRoute, configRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })

  return {
    cacheControl,
    ...render(<RouterProvider router={router} />),
  }
}

describe('TagsView', () => {
  beforeEach(() => {
    useTagsViewStore.getState().resetViews()
  })

  it('adds current crawler task page to tags view', async () => {
    renderTagsView('/crawler/tasks')

    expect(await screen.findByText('仪表盘')).toBeInTheDocument()
    expect(await screen.findByText('任务列表')).toBeInTheDocument()
  })

  it('shows right-click context menu actions', async () => {
    renderTagsView('/crawler/tasks')

    await userEvent.pointer({
      keys: '[MouseRight]',
      target: await screen.findByText('任务列表'),
    })

    expect(await screen.findByText('刷新页面')).toBeInTheDocument()
    expect(screen.getByText('关闭当前')).toBeInTheDocument()
    expect(screen.getByText('关闭其他')).toBeInTheDocument()
    expect(screen.getByText('关闭左侧')).toBeInTheDocument()
    expect(screen.getByText('关闭右侧')).toBeInTheDocument()
    expect(screen.getByText('全部关闭')).toBeInTheDocument()
  })

  it('destroys the matching route cache when a tag close icon is clicked', async () => {
    const cacheControl = createCacheControl()
    renderTagsView('/crawler/tasks', cacheControl)

    await userEvent.click(await screen.findByLabelText('关闭 任务列表'))

    expect(cacheControl.destroy).toHaveBeenCalledWith('/crawler/tasks')
  })

  it('destroys removed route caches when closing other tags', async () => {
    const cacheControl = createCacheControl()
    useTagsViewStore.setState({
      visitedViews: [
        { path: '/', fullPath: '/', title: '仪表盘', closable: false },
        { path: '/crawler/tasks', fullPath: '/crawler/tasks', title: '任务列表', closable: true },
        {
          path: '/crawler/tasks/new',
          fullPath: '/crawler/tasks/new?draft=1',
          title: '新建任务',
          closable: true,
        },
        {
          path: '/crawler/config',
          fullPath: '/crawler/config',
          title: '爬虫配置',
          closable: true,
        },
      ],
    })
    renderTagsView('/crawler/tasks', cacheControl)

    await userEvent.pointer({
      keys: '[MouseRight]',
      target: await screen.findByText('任务列表'),
    })
    await userEvent.click(await screen.findByText('关闭其他'))

    expect(cacheControl.destroyMany).toHaveBeenCalledWith([
      '/crawler/tasks/new?draft=1',
      '/crawler/config',
    ])
  })

  it('refreshes the selected route cache from the context menu', async () => {
    const cacheControl = createCacheControl()
    renderTagsView('/crawler/tasks', cacheControl)

    await userEvent.pointer({
      keys: '[MouseRight]',
      target: await screen.findByText('任务列表'),
    })
    await userEvent.click(await screen.findByText('刷新页面'))

    expect(cacheControl.refresh).toHaveBeenCalledWith('/crawler/tasks')
  })
})
