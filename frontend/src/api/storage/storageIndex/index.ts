import { request } from '@/request'
import type { StorageIndexMetadata } from './types.ts'

export type { StorageIndexMetadata } from './types.ts'

const BASE_URL = '/api/storage/index'

export function fetchStorageIndexStatus(): Promise<StorageIndexMetadata> {
  return request.get<StorageIndexMetadata>(`${BASE_URL}/status`)
}

export function refreshStorageIndex(): Promise<StorageIndexMetadata> {
  return request.post<StorageIndexMetadata>(`${BASE_URL}/refresh`)
}
