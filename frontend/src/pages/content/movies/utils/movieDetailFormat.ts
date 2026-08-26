import type { MovieMagnet } from '@/api/movie/types'

export function getMagnetSizeText(magnet: MovieMagnet): string {
  if (magnet.size_text) return magnet.size_text
  if (typeof magnet.size === 'string' && magnet.size.trim()) return magnet.size
  const sizeMb = typeof magnet.size_mb === 'number' ? magnet.size_mb : magnet.size
  return typeof sizeMb === 'number' ? `${(sizeMb / 1024).toFixed(1)} GB` : ''
}

export function uniqueStrings(values: unknown): string[] {
  if (!Array.isArray(values)) return []
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    if (typeof value !== 'string') continue
    const normalized = value.trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    result.push(normalized)
  }
  return result
}

const DETAIL_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export function formatDateTime(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return DETAIL_DATE_TIME_FORMATTER.format(date).replace(/\//g, '/')
}
