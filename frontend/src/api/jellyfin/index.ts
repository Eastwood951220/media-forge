import { request } from '@/request'

const BASE = '/api/jellyfin'

export interface JellyfinLibrary {
  Name: string
  ItemId: string
  Locations: string[]
}

export interface JellyfinWatchStatus {
  status: string
  last_attempt_at: string | null
  last_success_at: string | null
  last_error: string | null
}

export function testJellyfinConnection(): Promise<{ library_count: number; root_user_id: string }> {
  return request.post(`${BASE}/test`)
}

export function listJellyfinLibraries(): Promise<JellyfinLibrary[]> {
  return request.get(`${BASE}/libraries`)
}

export function refreshJellyfinLibraries(): Promise<{ libraries: Array<{ library_id: string; name: string; accepted: boolean; error: string | null }> }> {
  return request.post(`${BASE}/libraries/refresh`)
}

export function syncJellyfinWatch(): Promise<{ total_count: number; matched_count: number; ambiguous_count: number; synced_at: string }> {
  return request.post(`${BASE}/watch/sync`)
}

export function getJellyfinWatchStatus(): Promise<JellyfinWatchStatus> {
  return request.get(`${BASE}/watch/status`)
}
