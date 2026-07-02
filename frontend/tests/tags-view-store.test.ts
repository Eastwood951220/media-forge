import { beforeEach, describe, expect, it } from 'vitest'
import { useTagsViewStore } from '../src/stores/useTagsViewStore'

describe('useTagsViewStore', () => {
  beforeEach(() => {
    useTagsViewStore.getState().resetViews()
  })

  it('keeps dashboard affix and adds crawler task routes', () => {
    useTagsViewStore.getState().addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })

    expect(useTagsViewStore.getState().visitedViews.map((view) => view.title)).toEqual([
      '仪表盘',
      '任务列表',
    ])
  })

  it('removes right-side closable views while preserving affix dashboard', () => {
    const store = useTagsViewStore.getState()
    store.addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/tasks/new',
      fullPath: '/crawler/tasks/new',
      cacheKey: '/crawler/tasks/new',
      title: '新建任务',
      closable: true,
    })

    const nextViews = store.removeRightViews({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })

    expect(nextViews.map((view) => view.fullPath)).toEqual(['/', '/crawler/tasks'])
  })

  it('deduplicates dynamic task edit tags by cache key and keeps the latest url', () => {
    const store = useTagsViewStore.getState()
    store.addVisitedView({
      path: '/crawler/tasks/task-a/edit',
      fullPath: '/crawler/tasks/task-a/edit',
      cacheKey: '/crawler/tasks/:id/edit',
      title: '编辑任务',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/tasks/task-b/edit',
      fullPath: '/crawler/tasks/task-b/edit',
      cacheKey: '/crawler/tasks/:id/edit',
      title: '编辑任务',
      closable: true,
    })

    expect(useTagsViewStore.getState().visitedViews).toEqual([
      { path: '/', fullPath: '/', cacheKey: '/', title: '仪表盘', closable: false },
      {
        path: '/crawler/tasks/task-b/edit',
        fullPath: '/crawler/tasks/task-b/edit',
        cacheKey: '/crawler/tasks/:id/edit',
        title: '编辑任务',
        closable: true,
      },
    ])
  })

  it('removes and keeps tags by cache key', () => {
    const store = useTagsViewStore.getState()
    store.addVisitedView({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      cacheKey: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/runs/run-a',
      fullPath: '/crawler/runs/run-a',
      cacheKey: '/crawler/runs/:id',
      title: '运行详情',
      closable: true,
    })

    const nextViews = store.removeSelectedView({
      path: '/crawler/runs/run-b',
      fullPath: '/crawler/runs/run-b',
      cacheKey: '/crawler/runs/:id',
      title: '运行详情',
      closable: true,
    })

    expect(nextViews.map((view) => view.cacheKey)).toEqual(['/', '/crawler/tasks'])
  })
})
