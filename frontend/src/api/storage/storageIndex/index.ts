import { request } from '@/request'
import type { StorageIndexMetadata, StorageIndexRefreshStartResult } from './types.ts'

export type { StorageIndexMetadata, StorageIndexRefreshStartResult } from './types.ts'

export type StorageIndexRefreshMode = 'full' | 'incremental'

const BASE_URL = '/api/storage/index'

export function fetchStorageIndexStatus(): Promise<StorageIndexMetadata> {
  return request.get<StorageIndexMetadata>(`${BASE_URL}/status`)
}

export function refreshStorageIndex(mode: StorageIndexRefreshMode): Promise<StorageIndexRefreshStartResult> {
  return request.post<StorageIndexRefreshStartResult>(`${BASE_URL}/refresh`, { mode })
}
