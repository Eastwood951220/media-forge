import { request } from '@/request'
import type {
  StorageBatchPushPayload,
  StorageMainTask,
  StorageSinglePushPayload,
  StorageSubTask,
  StorageTaskLog,
} from './types'
import type { CountResponse, PagedListResponse, PaginatedResponse } from '@/api/crawler/crawlTask/types'

const BASE_URL = '/api/storage/tasks'

export function getNextAlias(): Promise<{ alias: string }> {
  return request.get<{ alias: string }>(`${BASE_URL}/next-alias`)
}

export function createStoragePush(payload: StorageSinglePushPayload): Promise<StorageMainTask> {
  return request.post<StorageMainTask>(`${BASE_URL}/push`, payload)
}

export function createBatchStoragePush(payload: StorageBatchPushPayload): Promise<StorageMainTask> {
  return request.post<StorageMainTask>(`${BASE_URL}/batch`, payload)
}

export function listStorageMainTasks(params: {
  page: number
  size: number
  status?: string
  keyword?: string
}): Promise<PagedListResponse<StorageMainTask>> {
  return request.get<PagedListResponse<StorageMainTask>>(BASE_URL, params)
}

export function countStorageMainTasks(params?: {
  status?: string
  keyword?: string
}): Promise<CountResponse> {
  return request.get<CountResponse>(`${BASE_URL}/count`, params)
}

export function getStorageMainTask(id: string): Promise<StorageMainTask> {
  return request.get<StorageMainTask>(`${BASE_URL}/${id}`)
}

export function stopStorageMainTask(id: string): Promise<StorageMainTask> {
  return request.post<StorageMainTask>(`${BASE_URL}/${id}/stop`)
}

export function restartStorageMainTask(id: string): Promise<StorageMainTask> {
  return request.post<StorageMainTask>(`${BASE_URL}/${id}/restart`)
}

export function deleteStorageMainTask(id: string): Promise<void> {
  return request.delete<void>(`${BASE_URL}/${id}`)
}

export function listStorageSubTasks(
  mainTaskId: string,
  params?: {
    page?: number
    limit?: number
  },
): Promise<PaginatedResponse<StorageSubTask>> {
  return request.get<PaginatedResponse<StorageSubTask>>(`${BASE_URL}/${mainTaskId}/subtasks`, params)
}

export function getStorageSubTask(subtaskId: string): Promise<StorageSubTask> {
  return request.get<StorageSubTask>(`${BASE_URL}/subtasks/${subtaskId}`)
}

export function retryStorageSubTask(subtaskId: string): Promise<StorageSubTask> {
  return request.post<StorageSubTask>(`${BASE_URL}/subtasks/${subtaskId}/retry`)
}

export function getStorageSubTaskLogs(subtaskId: string): Promise<StorageTaskLog[]> {
  return request.get<StorageTaskLog[]>(`${BASE_URL}/subtasks/${subtaskId}/logs`)
}
