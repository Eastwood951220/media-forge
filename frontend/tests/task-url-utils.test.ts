import { describe, expect, it } from 'vitest'
import { buildFinalUrlPreview, detectUrlType } from '../src/pages/crawler/tasks/taskUrlUtils'

describe('taskUrlUtils', () => {
  it('detects restored javdb URL types', () => {
    expect(detectUrlType('https://javdb.com/actors/abc')).toBe('actors')
    expect(detectUrlType('https://javdb.com/series/abc')).toBe('series')
    expect(detectUrlType('https://javdb.com/makers/abc')).toBe('makers')
    expect(detectUrlType('https://javdb.com/directors/abc')).toBe('directors')
    expect(detectUrlType('https://javdb.com/video_codes/abc')).toBe('video_codes')
    expect(detectUrlType('https://javdb.com/lists/abc')).toBe('lists')
    expect(detectUrlType('https://javdb.com/tags?c7=212')).toBe('tags')
    expect(detectUrlType('https://javdb.com/search?q=test')).toBe('search')
    expect(detectUrlType('not-a-url')).toBeNull()
  })

  it('builds search final url preview with subtitle and date sort', () => {
    expect(buildFinalUrlPreview('https://javdb.com/search?q=abc', 'search', false, true, 1)).toContain('f=cnsub')
    expect(buildFinalUrlPreview('https://javdb.com/search?q=abc', 'search', false, true, 1)).toContain('sb=1')
  })
})
