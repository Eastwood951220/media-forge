export type UrlType =
  | 'actors'
  | 'series'
  | 'makers'
  | 'directors'
  | 'video_codes'
  | 'lists'
  | 'tags'
  | 'search'
  | 'detail'

export type UrlSource = 'javdb' | 'javbus'

type CondParamConfig = {
  magnet: string
  sub: string
  both: string
}

const URL_TYPE_PARAMS: Record<string, CondParamConfig> = {
  actors: { magnet: 't=d', sub: 't=c', both: 't=c,d' },
  series: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  makers: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  directors: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  video_codes: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  lists: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
  tags: { magnet: 'c10=1', sub: 'c10=2', both: 'c10=1,2' },
  search: { magnet: 'f=download', sub: 'f=cnsub', both: 'f=cnsub' },
}

const PARAM_KEYS = ['t', 'f', 'c10', 'sort', 'page', 'sb'] as const

export const URL_TYPE_LABELS: Record<UrlType, string> = {
  actors: '演员 (actors)',
  series: '系列 (series)',
  makers: '片商 (makers)',
  directors: '导演 (directors)',
  video_codes: '番号 (video_codes)',
  lists: '列表 (lists)',
  tags: '标签 (tags)',
  search: '搜索 (search)',
  detail: '详情页 (detail)',
}

export const SORT_OPTIONS = [
  { value: 0, label: '日期降序' },
  { value: 5, label: '番号降序' },
]

export const SEARCH_SORT_OPTIONS = [
  { value: 0, label: '按相关度' },
  { value: 1, label: '按发布日期' },
]

export function detectUrlSource(url: string): UrlSource | null {
  try {
    const parsed = new URL(url)
    const hostname = parsed.hostname.toLowerCase()
    if (hostname === 'javdb.com' || hostname.endsWith('.javdb.com')) return 'javdb'
    if (hostname === 'javbus.com' || hostname === 'www.javbus.com') return 'javbus'
    return null
  } catch {
    return null
  }
}

export function detectUrlType(url: string): UrlType | null {
  try {
    const parsed = new URL(url)
    const path = parsed.pathname
    if (path.startsWith('/search')) return 'search'
    if (path.startsWith('/actors/')) return 'actors'
    if (path.startsWith('/series/')) return 'series'
    if (path.startsWith('/makers/')) return 'makers'
    if (path.startsWith('/directors/')) return 'directors'
    if (path.startsWith('/video_codes/')) return 'video_codes'
    if (path.startsWith('/lists/')) return 'lists'
    if (path === '/tags' || path.startsWith('/tags/')) return 'tags'
    return null
  } catch {
    return null
  }
}

function stripQueryParams(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl)
    PARAM_KEYS.forEach((key) => parsed.searchParams.delete(key))
    const query = parsed.searchParams.toString()
    return parsed.pathname + (query ? `?${query}` : '')
  } catch {
    return rawUrl
  }
}

export function buildFinalUrlPreview(
  baseUrl: string,
  urlType: UrlType,
  hasMagnet: boolean,
  hasSub: boolean,
  sortType: number,
  source?: UrlSource | null,
): string {
  if (!baseUrl) return baseUrl
  if (source === 'javbus') return baseUrl

  const stripped = stripQueryParams(baseUrl)
  const parts: string[] = []

  if (urlType === 'search') {
    if (hasMagnet) parts.push('f=download')
    else if (hasSub) parts.push('f=cnsub')
    parts.push(`sb=${sortType}`)
  } else {
    const cfg = URL_TYPE_PARAMS[urlType]
    if (hasMagnet && hasSub && cfg.both) parts.push(cfg.both)
    else if (hasMagnet) parts.push(cfg.magnet)
    else if (hasSub) parts.push(cfg.sub)
    if ((urlType === 'actors' || urlType === 'video_codes') && sortType !== 0) {
      parts.push(`sort=${sortType}`)
    }
  }

  if (parts.length === 0) return stripped

  try {
    const parsed = new URL(baseUrl)
    const base = parsed.origin + stripped
    return base + (stripped.includes('?') ? '&' : '?') + parts.join('&')
  } catch {
    return stripped + (stripped.includes('?') ? '&' : '?') + parts.join('&')
  }
}
