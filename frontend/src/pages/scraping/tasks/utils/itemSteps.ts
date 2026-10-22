import type { ScrapingTaskItem, ScrapingTaskLog } from '@/api/scraping/scrapingTasks'

export const stepOrder = [
  'prepare', 'locate_folder', 'fetch_metadata', 'write_artwork', 'write_nfo', 'refresh_status',
] as const

export const stepLabels: Record<string, string> = {
  prepare: '准备任务',
  locate_folder: '定位影片文件夹',
  fetch_metadata: '获取元数据',
  write_artwork: '下载并筛选图片',
  write_nfo: '写入影片 NFO',
  refresh_status: '更新刮削状态',
}

export const levelColors: Record<string, string> = {
  INFO: 'processing', WARNING: 'warning', ERROR: 'error', DEBUG: 'default',
}

export function stepColor(item: ScrapingTaskItem, logs: ScrapingTaskLog[], step: string) {
  const matching = logs.filter((log) => log.step === step)
  if (matching.some((log) => log.level === 'ERROR')) return 'red'
  if (item.status === 'running' && item.step === step) return 'blue'
  if (matching.length > 0) return 'green'
  return 'gray'
}

const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hour12: false,
  hour: '2-digit', minute: '2-digit', second: '2-digit',
})

export function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : timeFormatter.format(date)
}
