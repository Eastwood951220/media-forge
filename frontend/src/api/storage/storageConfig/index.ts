import { request } from '@/request'
import type { StorageConfig, StorageConfigUpdate, StorageTestResult } from './types.ts'

export type { StorageConfig, StorageConfigUpdate, StorageTestResult } from './types.ts'

const BASE_URL = '/api/storage/config'

export function fetchStorageConfig(): Promise<StorageConfig> {
  return request.get<StorageConfig>(BASE_URL)
}

export function updateStorageConfig(data: StorageConfigUpdate): Promise<StorageConfig> {
  return request.put<StorageConfig>(BASE_URL, data)
}

export function testStorageConnection(): Promise<StorageTestResult> {
  return request.post<StorageTestResult>(`${BASE_URL}/test`)
}
