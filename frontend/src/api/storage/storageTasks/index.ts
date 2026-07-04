import { request } from '@/request'
import type {
  StorageBatchPushPayload,
  StorageMainTask,
  StorageSinglePushPayload,
  StorageSubTask,
  StorageTaskLog,
} from './types'
import type { PaginatedResponse } from '@/api/crawlTask/types'

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

export function listStorageMainTasks(params?: {
  page?: number
  limit?: number
  status?: string
  keyword?: string
}): Promise<PaginatedResponse<StorageMainTask>> {
  return request.get<PaginatedResponse<StorageMainTask>>(BASE_URL, params)
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

export function getStorageSubTaskLogs(subtaskId: string): Promise<StorageTaskLog[]> {
  return request.get<StorageTaskLog[]>(`${BASE_URL}/subtasks/${subtaskId}/logs`)
}
