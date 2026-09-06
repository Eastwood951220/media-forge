export type BackupGroup = 'movies' | 'tasks' | 'config'
export type RestoreMode = 'merge' | 'overwrite'
export type BackupJobStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'
export type ScheduleType = 'daily' | 'weekly'

export interface BackupConfig {
  enabled: boolean
  backup_dir: string
  schedule_type: ScheduleType
  time_of_day: string
  weekdays: number[]
  groups: BackupGroup[]
  include_sensitive: boolean
  retention_count: number
}

export interface BackupConfigUpdate {
  enabled?: boolean
  backup_dir?: string
  schedule_type?: ScheduleType
  time_of_day?: string
  weekdays?: number[]
  groups?: BackupGroup[]
  include_sensitive?: boolean
  retention_count?: number
}

export interface BackupFileInfo {
  name: string
  path: string
  size: number
  created_at: string
  groups: BackupGroup[]
  include_sensitive: boolean
}

export interface BackupExportRequest {
  groups: BackupGroup[]
  include_sensitive: boolean
}

export interface BackupRestoreRequest {
  mode: RestoreMode
  groups: BackupGroup[]
}

export interface BackupJobResponse {
  job_id: string
}

export interface BackupInspectResult {
  manifest: Record<string, unknown>
  groups: BackupGroup[]
  row_counts: Record<string, number>
  include_sensitive: boolean
}

export type BackupGroupStats = {
  created: number
  updated: number
  skipped: number
  conflicts: number
  errors: number
}

export interface BackupJob {
  id: string
  operation: 'export' | 'inspect' | 'restore' | 'auto_export' | 'delete'
  status: BackupJobStatus
  phase: string
  processed: number
  total: number | null
  result: Record<string, unknown>
  error: string | null
  created_at: string
  updated_at: string
}
