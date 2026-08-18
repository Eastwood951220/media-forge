import { request } from '@/request'
import type {
  AgentEventPage,
  AgentEventQuery,
  AgentWorkItemPage,
} from '@/api/crawler/crawlerAgent/types'
import type {
  CrawlRun,
  CrawlMode,
  RetryCrawlerRunTasksRequest,
  RunListResponse,
  RunLogEntry,
  RunTaskPageWithSummary,
} from './types.ts'

const BASE_URL = '/api/crawler/runs'

export function getCrawlerRuns(params: {
  page: number
  size: number
  task_id?: string
  status?: string
}): Promise<RunListResponse> {
  return request.get<RunListResponse>(BASE_URL, params)
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
): Promise<RunTaskPageWithSummary> {
  return request.get<RunTaskPageWithSummary>(`${BASE_URL}/${runId}/tasks`, params)
}

export function stopCrawlerRun(runId: string): Promise<void> {
  return request.post<void>(`${BASE_URL}/${runId}/stop`)
}

export function deleteCrawlerRun(runId: string): Promise<void> {
  return request.delete<void>(`${BASE_URL}/${runId}`)
}

export function restartCrawlerRun(runId: string): Promise<void> {
  return request.post<void>(`${BASE_URL}/${runId}/restart`)
}

export function retryCrawlerRunTasks(
  runId: string,
  payload: RetryCrawlerRunTasksRequest,
): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${runId}/tasks/retry`, payload)
}

export function runCrawlTask(taskId: string, crawlMode: CrawlMode): Promise<CrawlRun> {
  return request.post<CrawlRun>(`/api/crawler/tasks/${taskId}/run`, {
    crawl_mode: crawlMode,
  })
}

export function getCrawlerRunAgentWorkItems(runId: string): Promise<AgentWorkItemPage> {
  return request.get<AgentWorkItemPage>(`${BASE_URL}/${runId}/agent-work-items`)
}

export function getCrawlerRunAgentEvents(
  runId: string,
  params: AgentEventQuery = {},
): Promise<AgentEventPage> {
  return request.get<AgentEventPage>(`${BASE_URL}/${runId}/agent-events`, params)
}
