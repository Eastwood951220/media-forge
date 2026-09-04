import { request } from '@/request'
import type {
  CrawlerSchedule,
  CrawlerSchedulePage,
  CrawlerSchedulePayload,
  CrawlerScheduleRunPage,
} from './types.ts'

const BASE_URL = '/api/crawler/schedules'

export function getCrawlerSchedules(params: { page: number; size: number }): Promise<CrawlerSchedulePage> {
  return request.get<CrawlerSchedulePage>(BASE_URL, params)
}

export function getCrawlerScheduleRuns(
  scheduleId: string,
  params: { page: number; size: number },
): Promise<CrawlerScheduleRunPage> {
  return request.get<CrawlerScheduleRunPage>(`${BASE_URL}/${scheduleId}/runs`, params)
}

export function createCrawlerSchedule(data: CrawlerSchedulePayload): Promise<CrawlerSchedule> {
  return request.post<CrawlerSchedule>(BASE_URL, data)
}

export function updateCrawlerSchedule(id: string, data: CrawlerSchedulePayload): Promise<CrawlerSchedule> {
  return request.put<CrawlerSchedule>(`${BASE_URL}/${id}`, data)
}

export function enableCrawlerSchedule(id: string): Promise<CrawlerSchedule> {
  return request.post<CrawlerSchedule>(`${BASE_URL}/${id}/enable`)
}

export function disableCrawlerSchedule(id: string): Promise<CrawlerSchedule> {
  return request.post<CrawlerSchedule>(`${BASE_URL}/${id}/disable`)
}

export function triggerCrawlerSchedule(id: string): Promise<{ schedule_run_id: string }> {
  return request.post<{ schedule_run_id: string }>(`${BASE_URL}/${id}/trigger`)
}

export function deleteCrawlerSchedule(id: string): Promise<{ id: string }> {
  return request.delete<{ id: string }>(`${BASE_URL}/${id}`)
}
