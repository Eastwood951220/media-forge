import { request } from '@/request'
import type { ScrapingTask, ScrapingTaskDetail, ScrapingTaskItem, ScrapingTaskListResponse, ScrapingTaskLog } from './types'

export type * from './types'

const BASE_URL = '/api/scraping/tasks'

export function listScrapingTasks(params: {
  page: number
  size: number
  status?: string
}): Promise<ScrapingTaskListResponse> {
  return request.get<ScrapingTaskListResponse>(BASE_URL, params)
}

export function getScrapingTask(id: string): Promise<ScrapingTaskDetail> {
  return request.get<ScrapingTaskDetail>(`${BASE_URL}/${id}`)
}

export function getScrapingItem(id: string): Promise<ScrapingTaskItem> {
  return request.get<ScrapingTaskItem>(`${BASE_URL}/items/${id}`)
}

export function getScrapingItemLogs(id: string): Promise<ScrapingTaskLog[]> {
  return request.get<ScrapingTaskLog[]>(`${BASE_URL}/items/${id}/logs`)
}

export function createScrapingTask(movieIds: string[]): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(BASE_URL, { movie_ids: movieIds })
}

export function cancelScrapingTask(id: string): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(`${BASE_URL}/${id}/cancel`)
}

export function retryScrapingTask(id: string): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(`${BASE_URL}/${id}/retry`)
}
