import { request } from '@/request'
import type {
  ScrapingConfig,
  ScrapingConfigUpdate,
  ScrapingRunResult,
  ScrapingScanSummary,
} from './types.ts'

export type {
  ScrapingConfig,
  ScrapingConfigUpdate,
  ScrapingRunResult,
  ScrapingScanSummary,
} from './types.ts'

const BASE_URL = '/api/scraping'

export function getScrapingConfig(): Promise<ScrapingConfig> {
  return request.get<ScrapingConfig>(`${BASE_URL}/config`)
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
