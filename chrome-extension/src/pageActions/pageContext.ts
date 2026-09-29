export type PageKind = 'home' | 'detail' | 'list' | 'unsupported'

export type PageContext = {
  kind: PageKind
  url: string
  normalizedUrl: string
  pageName: string
}

function cleanText(value: string | null | undefined): string {
  return String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
}

function queryText(document: Document, selectors: string[]): string {
  for (const selector of selectors) {
    const value = cleanText(document.querySelector(selector)?.textContent)
    if (value) return value
  }
  return ''
}

function cleanedDocumentTitle(document: Document): string {
  return cleanText(document.title.replace(/\s*(?:[-|–—·]\s*)?JavDB.*$/i, ''))
}

export function classifyPage(location: URL, document: Document): PageKind {
  const path = location.pathname || '/'
  if (path === '/') return 'home'
  if (/^\/v\/[^/]+\/?$/.test(path)) return 'detail'
  if (document.querySelector('div.item')) return 'list'
  return 'unsupported'
}

export function normalizeListUrlPreview(rawUrl: string): string {
  const url = new URL(rawUrl)
  url.hash = ''
  const query = [...url.searchParams.entries()].filter(([key]) => key !== 'page')
  query.push(['page', '1'])
  query.sort(([leftKey, leftValue], [rightKey, rightValue]) => {
    const keyOrder = leftKey.localeCompare(rightKey)
    return keyOrder || leftValue.localeCompare(rightValue)
  })
  url.search = new URLSearchParams(query).toString()
  return url.toString()
}

function detailPageName(document: Document): string {
  return (
    queryText(document, [
      '.video-detail h2.title.is-4',
      '.video-detail .title.is-4',
      'h2.title.is-4',
      '.video-detail .title',
    ]) ||
    cleanedDocumentTitle(document) ||
    'JavDB 影片'
  )
}

function listPageName(location: URL, document: Document): string {
  const heading = queryText(document, [
    '.actor-section-name',
    '.section-name',
    '.section-title',
  ])
  if (heading) return heading
  const searchName = cleanText(location.searchParams.get('q') ?? location.searchParams.get('s'))
  return searchName || cleanedDocumentTitle(document) || 'JavDB 列表'
}

export function extractPageContext(location: URL, document: Document): PageContext {
  const kind = classifyPage(location, document)
  const url = location.toString()
  return {
    kind,
    url,
    normalizedUrl: kind === 'list' ? normalizeListUrlPreview(url) : url,
    pageName: kind === 'detail' ? detailPageName(document) : listPageName(location, document),
  }
}
