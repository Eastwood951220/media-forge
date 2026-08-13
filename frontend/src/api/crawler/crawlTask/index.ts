import { request } from '@/request'
import type { CrawlRun } from '@/api/crawlerRun/types'
import type {
  CountResponse,
  CrawlTask,
  CrawlTaskCreateParams,
  CrawlTaskRuntimeStatusResponse,
  CrawlTaskStats,
  CrawlTaskUpdateParams,
  DeleteMode,
  DeleteTaskResult,
  FastListResponse,
  TaskDictItem,
  TaskUrlRunCreateParams,
  TemporaryCrawlRunCreateParams,
} from './types'

const BASE_URL = '/api/crawler/tasks'

export function getCrawlTasks(params: {
  page: number
  size: number
  keyword?: string
}): Promise<FastListResponse<CrawlTask> & { runtime?: CrawlTaskRuntimeStatusResponse }> {
  return request.get<FastListResponse<CrawlTask> & { runtime?: CrawlTaskRuntimeStatusResponse }>(BASE_URL, params)
}

export function getCrawlTaskCount(params?: { keyword?: string }): Promise<CountResponse> {
  return request.get<CountResponse>(`${BASE_URL}/count`, params)
}

export function getCrawlTaskStats(): Promise<CrawlTaskStats> {
  return request.get<CrawlTaskStats>(`${BASE_URL}/stats`)
}

export function getTaskDict(): Promise<TaskDictItem[]> {
  return request.get<TaskDictItem[]>(`${BASE_URL}/dict`)
}

export function getCrawlTask(taskId: string): Promise<CrawlTask> {
  return request.get<CrawlTask>(`${BASE_URL}/${taskId}`)
}

export function createCrawlTask(data: CrawlTaskCreateParams): Promise<CrawlTask> {
  return request.post<CrawlTask>(BASE_URL, data)
}

export function updateCrawlTask(
  taskId: string,
  data: CrawlTaskUpdateParams,
): Promise<CrawlTask> {
  return request.put<CrawlTask>(`${BASE_URL}/${taskId}`, data)
}

export function deleteCrawlTask(taskId: string, mode: DeleteMode = 'task_only'): Promise<DeleteTaskResult> {
  return request.delete<DeleteTaskResult>(`${BASE_URL}/${taskId}?mode=${mode}`)
}

export function extractTaskName(url: string, urlType: string): Promise<{ name: string }> {
  return request.post<{ name: string }>(`${BASE_URL}/extract-name`, {
    url,
    url_type: urlType,
  })
}

export function getCrawlTaskRuntimeStatuses(): Promise<CrawlTaskRuntimeStatusResponse> {
  return request.get<CrawlTaskRuntimeStatusResponse>(`${BASE_URL}/statuses`)
}

export function createTemporaryCrawlRun(data: TemporaryCrawlRunCreateParams): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/temp-run`, data)
}

export function createTaskUrlRun(taskId: string, data: TaskUrlRunCreateParams): Promise<CrawlRun> {
  return request.post<CrawlRun>(`${BASE_URL}/${taskId}/url-run`, data)
}
