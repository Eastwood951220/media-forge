export type SystemStatus = 'healthy' | 'busy' | 'warning' | 'error'
export type AlertSeverity = 'info' | 'warning' | 'error'

export interface CountItem {
  status: string
  count: number
}

export interface DailyTrendItem {
  date: string
  completed: number
  failed: number
}

export interface DashboardTaskStats {
  total: number
  enabled: number
  disabled: number
}

export interface DashboardRuntimeStats {
  total: number
  idle: number
  running: number
  queued: number
  stopped: number
}

export interface DashboardQueueStatus {
  queue_size: number
  is_running: boolean
  current_run_id: string | null
  stop_requested: boolean
}

export interface DashboardCrawlerSection {
  task_stats: DashboardTaskStats
  runtime_stats: DashboardRuntimeStats
  queue: DashboardQueueStatus
}

export interface RecentCrawlerRun {
  id: string
  task_name: string
  status: string
  crawl_mode: string
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
}

export interface DashboardRunsSection {
  status_distribution: CountItem[]
  daily_trend: DailyTrendItem[]
  recent: RecentCrawlerRun[]
}

export interface DashboardMovieStorageStatus {
  stored: number
  storing: number
  not_stored: number
}

export interface DashboardContentSection {
  movie_total: number
  storage_status: DashboardMovieStorageStatus
}

export interface DashboardStorageIndex {
  target_folder: string
  status: string
  category_count: number
  code_folder_count: number
  video_count: number
  completed_at: string | null
  errors: Array<Record<string, unknown>>
}

export interface RecentStorageTask {
  id: string
  alias: string
  display_name: string
  status: string
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
}

export interface DashboardStorageSection {
  task_status_distribution: CountItem[]
  recent_tasks: RecentStorageTask[]
  index: DashboardStorageIndex
}

export interface DashboardAlert {
  id: string
  title: string
  description: string
  severity: AlertSeverity
  source: string
  target_path: string | null
  occurred_at: string | null
}

export interface PartialError {
  section: string
  message: string
}

export interface DashboardOverview {
  system_status: SystemStatus
  refreshed_at: string
  crawler: DashboardCrawlerSection
  runs: DashboardRunsSection
  content: DashboardContentSection
  storage: DashboardStorageSection
  alerts: DashboardAlert[]
  partial_errors: PartialError[]
}
