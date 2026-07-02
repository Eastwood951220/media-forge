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
      title: '任务列表',
      closable: true,
    })
    store.addVisitedView({
      path: '/crawler/tasks/new',
      fullPath: '/crawler/tasks/new',
      title: '新建任务',
      closable: true,
    })

    const nextViews = store.removeRightViews({
      path: '/crawler/tasks',
      fullPath: '/crawler/tasks',
      title: '任务列表',
      closable: true,
    })

    expect(nextViews.map((view) => view.fullPath)).toEqual(['/', '/crawler/tasks'])
  })
})
