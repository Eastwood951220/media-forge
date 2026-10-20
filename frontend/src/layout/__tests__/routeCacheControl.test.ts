import { describe, expect, it } from 'vitest'
import { isRouteCacheExcluded } from '../routeCacheControl'

describe('route cache exclusions', () => {
  it('excludes the three task list pages from keep-alive', () => {
    expect(isRouteCacheExcluded('/crawler/runs')).toBe(true)
    expect(isRouteCacheExcluded('/storage/tasks')).toBe(true)
    expect(isRouteCacheExcluded('/scraping/tasks')).toBe(true)
  })

  it('keeps detail routes cached', () => {
    expect(isRouteCacheExcluded('/crawler/runs/run-1')).toBe(false)
    expect(isRouteCacheExcluded('/storage/tasks/task-1')).toBe(false)
    expect(isRouteCacheExcluded('/scraping/tasks/task-1')).toBe(false)
  })
})
