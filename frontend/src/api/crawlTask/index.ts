import { request } from '@/request'
import type {
  CrawlTask,
  CrawlTaskCreateParams,
  CrawlTaskStats,
  CrawlTaskUpdateParams,
  PaginatedResponse,
} from './types'

const BASE_URL = '/api/crawler/tasks'

export function getCrawlTasks(params?: {
  skip?: number
  limit?: number
  keyword?: string
}): Promise<PaginatedResponse<CrawlTask>> {
  return request.get<PaginatedResponse<CrawlTask>>(BASE_URL, params)
}

export function getCrawlTaskStats(): Promise<CrawlTaskStats> {
  return request.get<CrawlTaskStats>(`${BASE_URL}/stats`)
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

export function deleteCrawlTask(taskId: string): Promise<void> {
  return request.delete(`${BASE_URL}/${taskId}`)
}

export function extractTaskName(url: string, urlType: string): Promise<{ name: string }> {
  return request.post<{ name: string }>(`${BASE_URL}/extract-name`, {
    url,
    url_type: urlType,
  })
}
