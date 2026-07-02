import { describe, expect, it } from 'vitest'
import { getFullPath, getRouteTagMeta, getRouteViewKey } from '../src/routes/tags'

describe('route tag helpers', () => {
  it('keeps ordinary routes keyed by pathname and search string', () => {
    expect(getFullPath('/crawler/tasks', '?page=2')).toBe('/crawler/tasks?page=2')
    expect(getRouteViewKey('/crawler/tasks', '?page=2')).toBe('/crawler/tasks?page=2')
  })

  it('uses one singleton key for crawler task edit pages', () => {
    expect(getRouteTagMeta('/crawler/tasks/task-a/edit')).toMatchObject({
      title: '编辑任务',
      activeMenu: '/crawler/tasks',
      singletonKey: '/crawler/tasks/:id/edit',
    })
    expect(getRouteViewKey('/crawler/tasks/task-a/edit', '')).toBe('/crawler/tasks/:id/edit')
    expect(getRouteViewKey('/crawler/tasks/task-b/edit', '?tab=url')).toBe('/crawler/tasks/:id/edit')
  })

  it('uses one singleton key for crawler run detail pages', () => {
    expect(getRouteTagMeta('/crawler/runs/run-a')).toMatchObject({
      title: '运行详情',
      activeMenu: '/crawler/runs',
      singletonKey: '/crawler/runs/:id',
    })
    expect(getRouteViewKey('/crawler/runs/run-a', '')).toBe('/crawler/runs/:id')
    expect(getRouteViewKey('/crawler/runs/run-b', '?status=failed')).toBe('/crawler/runs/:id')
  })
})
