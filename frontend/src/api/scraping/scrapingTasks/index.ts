import { request } from '@/request'
import type { ScrapingTask, ScrapingTaskDetail, ScrapingTaskListResponse } from './types'

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

export function createScrapingTask(movieIds: string[]): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(BASE_URL, { movie_ids: movieIds })
}

export function cancelScrapingTask(id: string): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(`${BASE_URL}/${id}/cancel`)
}

export function retryScrapingTask(id: string): Promise<ScrapingTask> {
  return request.post<ScrapingTask>(`${BASE_URL}/${id}/retry`)
}
