import { request } from '@/request'
import type {
  ScrapingConfig,
  ScrapingConfigUpdate,
  ScrapingDirectoryListing,
  ScrapingRunResult,
  ScrapingScanSummary,
} from './types.ts'

export type {
  ScrapingConfig,
  ScrapingConfigUpdate,
  ScrapingDirectoryEntry,
  ScrapingDirectoryListing,
  ScrapingRunResult,
  ScrapingScanSummary,
} from './types.ts'

const BASE_URL = '/api/scraping'

export function getScrapingConfig(): Promise<ScrapingConfig> {
  return request.get<ScrapingConfig>(`${BASE_URL}/config`)
}

export function listMetatubeProviders(): Promise<string[]> {
  return request.get<string[]>(`${BASE_URL}/metatube/providers`, undefined, { showError: false })
}

export function updateScrapingConfig(data: ScrapingConfigUpdate): Promise<ScrapingConfig> {
  return request.put<ScrapingConfig>(`${BASE_URL}/config`, data)
}

export function runScrapingStrm(): Promise<ScrapingRunResult> {
  return request.post<ScrapingRunResult>(`${BASE_URL}/strm/run`)
}

export function runScrapingScan(): Promise<ScrapingScanSummary> {
  return request.post<ScrapingScanSummary>(`${BASE_URL}/scan`)
}

export function listScrapingDirectories(
  path?: string,
  includeHidden = false,
): Promise<ScrapingDirectoryListing> {
  return request.get<ScrapingDirectoryListing>(
    `${BASE_URL}/directories`,
    {
      ...(path ? { path } : {}),
      include_hidden: includeHidden,
    },
    { showError: false },
  )
}

export function revealScrapingSecret(field: 'api_key' | 'metatube_token' | 'jellyfin_api_key'): Promise<{ value: string }> {
  return request.post<{ value: string }>(`${BASE_URL}/config/secrets/${field}`, undefined, { isRepeatSubmit: false, showError: false })
}
