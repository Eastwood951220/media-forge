import type {CrawlTaskRuntimeSnapshot, CrawlTaskRuntimeStats} from '@/api/crawlTask/types'

export const initialStats: CrawlTaskRuntimeStats = {
  total: 0,
  idle: 0,
  running: 0,
  queued: 0,
  stopped: 0,
}

export function recomputeStats(runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>): CrawlTaskRuntimeStats {
  const rows = Object.values(runtimeByTaskId)
  return rows.reduce<CrawlTaskRuntimeStats>(
    (acc, row) => {
      acc.total += 1
      acc[row.runtime_status] += 1
      return acc
    },
    {total: 0, idle: 0, running: 0, queued: 0, stopped: 0},
  )
}
