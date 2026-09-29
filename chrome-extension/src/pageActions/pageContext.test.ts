// @vitest-environment happy-dom

import { beforeEach, describe, expect, it } from 'vitest'

import {
  classifyPage,
  extractPageContext,
  normalizeListUrlPreview,
} from './pageContext'

describe('JavDB page context', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    document.title = ''
  })

  it.each([
    ['https://javdb.com/', '<div class="item"></div>', 'home'],
    ['https://javdb.com/v/abc', '<div class="video-detail"></div>', 'detail'],
    ['https://javdb.com/actors/A?page=9', '<div class="item"></div>', 'list'],
    ['https://javdb.com/future-list', '<div class="item"></div>', 'list'],
    ['https://javdb.com/users/sign_in', '<form></form>', 'unsupported'],
  ] as const)('classifies %s as %s', (url, html, expected) => {
    document.body.innerHTML = html

    expect(classifyPage(new URL(url), document)).toBe(expected)
  })

  it.each([
    ['<div class="video-detail"><h2 class="title is-4">影片标题 A</h2></div>', '影片标题 A'],
    ['<h2 class="title is-4">影片标题 B</h2>', '影片标题 B'],
  ])('extracts a detail title from supported title markup', (html, expected) => {
    document.body.innerHTML = html

    const context = extractPageContext(new URL('https://javdb.com/v/abc'), document)

    expect(context.pageName).toBe(expected)
    expect(context.normalizedUrl).toBe('https://javdb.com/v/abc')
  })

  it.each([
    ['<h2 class="actor-section-name">演员名称</h2><div class="item"></div>', '演员名称'],
    ['<h2 class="section-name">系列名称</h2><div class="item"></div>', '系列名称'],
    ['<h2 class="section-title">标签名称</h2><div class="item"></div>', '标签名称'],
  ])('extracts a list name from section markup', (html, expected) => {
    document.body.innerHTML = html

    const context = extractPageContext(new URL('https://javdb.com/future-list'), document)

    expect(context.kind).toBe('list')
    expect(context.pageName).toBe(expected)
  })

  it('uses the search query when a list heading is absent', () => {
    document.body.innerHTML = '<div class="item"></div>'

    const context = extractPageContext(
      new URL('https://javdb.com/search?q=波多野结衣'),
      document,
    )

    expect(context.pageName).toBe('波多野结衣')
  })

  it('uses a cleaned document title as the final list-name fallback', () => {
    document.body.innerHTML = '<div class="item"></div>'
    document.title = '热门影片 - JavDB'

    const context = extractPageContext(new URL('https://javdb.com/future-list'), document)

    expect(context.pageName).toBe('热门影片')
  })

  it('normalizes the list preview with stable filters and exactly page one', () => {
    expect(
      normalizeListUrlPreview(
        'https://JAVDB.com:443/search?z=2&page=3&q=abc&a=1&page=8#results',
      ),
    ).toBe('https://javdb.com/search?a=1&page=1&q=abc&z=2')
  })

  it('preserves repeated non-page query values in stable order', () => {
    expect(normalizeListUrlPreview('https://javdb.com/tags?c=2&c=1&page=7')).toBe(
      'https://javdb.com/tags?c=1&c=2&page=1',
    )
  })

  it('keeps the original URL separately from the display normalization', () => {
    document.body.innerHTML = '<h2 class="section-title">列表</h2><div class="item"></div>'
    const location = new URL('https://javdb.com/tags?page=9#results')

    const context = extractPageContext(location, document)

    expect(context.url).toBe('https://javdb.com/tags?page=9#results')
    expect(context.normalizedUrl).toBe('https://javdb.com/tags?page=1')
  })
})
