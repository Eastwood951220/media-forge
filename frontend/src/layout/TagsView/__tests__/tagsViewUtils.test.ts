import { describe, expect, it } from 'vitest'
import { clampContextMenuPosition, getRemovedCacheKeys } from '../tagsViewUtils'

describe('tagsViewUtils', () => {
  it('returns cache keys removed from closable tags only', () => {
    const before = [
      { path: '/', fullPath: '/', cacheKey: 'root', title: 'Root', closable: false },
      { path: '/a', fullPath: '/a', cacheKey: 'a', title: 'A', closable: true },
      { path: '/b', fullPath: '/b', cacheKey: 'b', title: 'B', closable: true },
    ]
    const next = [before[0], before[2]]

    expect(getRemovedCacheKeys(before, next)).toEqual(['a'])
  })

  it('clamps context menu to viewport', () => {
    expect(clampContextMenuPosition(790, 590, 140, 260, 800, 600)).toEqual({ left: 652, top: 332 })
  })
})
