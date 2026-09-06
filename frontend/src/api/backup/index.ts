import { request } from '@/request'
import type {
  BackupConfig,
  BackupConfigUpdate,
  BackupExportRequest,
  BackupFileInfo,
  BackupInspectResult,
  BackupJob,
  BackupJobResponse,
  BackupRestoreRequest,
} from './types.ts'

export type {
  BackupConfig,
  BackupConfigUpdate,
  BackupExportRequest,
  BackupFileInfo,
  BackupGroup,
  BackupGroupStats,
  BackupInspectResult,
  BackupJob,
  BackupJobResponse,
  BackupJobStatus,
  BackupRestoreRequest,
  RestoreMode,
  ScheduleType,
} from './types.ts'

const BASE_URL = '/api/backup'

export function getBackupConfig(): Promise<BackupConfig> {
  return request.get<BackupConfig>(`${BASE_URL}/config`)
}

export function updateBackupConfig(payload: BackupConfigUpdate): Promise<BackupConfig> {
  return request.put<BackupConfig>(`${BASE_URL}/config`, payload)
}

export function listBackupFiles(): Promise<BackupFileInfo[]> {
  return request.get<BackupFileInfo[]>(`${BASE_URL}/files`)
}

export function startBackupExport(payload: BackupExportRequest): Promise<BackupJobResponse> {
  return request.post<BackupJobResponse>(`${BASE_URL}/export`, payload)
}

export function inspectBackupFile(file: File): Promise<BackupInspectResult> {
  const form = new FormData()
  form.append('file', file)
  return request.post<BackupInspectResult>(`${BASE_URL}/inspect`, form)
}

export function startBackupRestore(file: File, payload: BackupRestoreRequest): Promise<BackupJobResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('payload', JSON.stringify(payload))
  return request.post<BackupJobResponse>(`${BASE_URL}/restore`, form)
}

export function restoreLocalBackup(name: string, payload: BackupRestoreRequest): Promise<BackupJobResponse> {
  return request.post<BackupJobResponse>(`${BASE_URL}/files/${encodeURIComponent(name)}/restore`, payload)
}

export function deleteBackupFile(name: string): Promise<{ deleted: boolean }> {
  return request.delete<{ deleted: boolean }>(`${BASE_URL}/files/${encodeURIComponent(name)}`)
}

export function getBackupJob(jobId: string): Promise<BackupJob> {
  return request.get<BackupJob>(`${BASE_URL}/jobs/${jobId}`)
}

export function getBackupDownloadUrl(name: string): string {
  return `${BASE_URL}/files/${encodeURIComponent(name)}/download`
}
