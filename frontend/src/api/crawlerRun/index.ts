import { request } from '@/request'
import type {
  CrawlRun,
  CrawlRunDetailTask,
  CrawlMode,
  QueueStatus,
  RetryCrawlerRunTasksRequest,
  RunLogEntry,
  RunTaskSummary,
} from './types'
import type { PaginatedResponse } from '../crawlTask/types'

export type CrawlerRunTasksResponse = PaginatedResponse<CrawlRunDetailTask> & {
  summary: RunTaskSummary
}

const BASE_URL = '/api/crawler/runs'

export function getCrawlerRuns(params?: {
  skip?: number
  limit?: number
  task_id?: string
  status?: string
}): Promise<PaginatedResponse<CrawlRun>> {
  return request.get<PaginatedResponse<CrawlRun>>(BASE_URL, params)
}

export function getCrawlerRun(runId: string): Promise<CrawlRun> {
  return request.get<CrawlRun>(`${BASE_URL}/${runId}`)
}

export function getCrawlerRunLogs(runId: string): Promise<RunLogEntry[]> {
  return request.get<RunLogEntry[]>(`${BASE_URL}/${runId}/logs`)
}

export function getCrawlerRunTasks(
  runId: string,
  params?: {
    page?: number
    size?: number
    status?: string
    keyword?: string
  },
): Promise<CrawlerRunTasksResponse> {
  return request.get<CrawlerRunTasksResponse>(`${BASE_URL}/${runId}/tasks`, params)
}

export function stopCrawlerRun(runId: string): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${runId}/stop`)
}

export function deleteCrawlerRun(runId: string): Promise<void> {
  return request.delete<void>(`${BASE_URL}/${runId}`)
}

export function restartCrawlerRun(runId: string): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${runId}/restart`)
}

export function retryCrawlerRunTasks(
  runId: string,
  payload: RetryCrawlerRunTasksRequest,
): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${runId}/tasks/retry`, payload)
}

export function getCrawlerQueueStatus(): Promise<QueueStatus> {
  return request.get<QueueStatus>(`${BASE_URL}/queue-status`)
}

export function runCrawlTask(taskId: string, crawlMode: CrawlMode): Promise<CrawlRun> {
  return request.post<CrawlRun>(`/api/crawler/tasks/${taskId}/run`, {
    crawl_mode: crawlMode,
  })
}
