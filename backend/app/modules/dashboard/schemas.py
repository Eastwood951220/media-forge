from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SystemStatus = Literal["healthy", "busy", "warning", "error"]
AlertSeverity = Literal["info", "warning", "error"]


class CountItem(BaseModel):
    status: str
    count: int


class DailyTrendItem(BaseModel):
    date: str
    completed: int = 0
    failed: int = 0


class DashboardTaskStats(BaseModel):
    total: int = 0
    enabled: int = 0
    disabled: int = 0


class DashboardRuntimeStats(BaseModel):
    total: int = 0
    idle: int = 0
    running: int = 0
    queued: int = 0
    stopped: int = 0


class DashboardQueueStatus(BaseModel):
    queue_size: int = 0
    is_running: bool = False
    current_run_id: str | None = None
    stop_requested: bool = False


class DashboardCrawlerSection(BaseModel):
    task_stats: DashboardTaskStats = Field(default_factory=DashboardTaskStats)
    runtime_stats: DashboardRuntimeStats = Field(default_factory=DashboardRuntimeStats)
    queue: DashboardQueueStatus = Field(default_factory=DashboardQueueStatus)


class RecentCrawlerRun(BaseModel):
    id: str
    task_name: str
    status: str
    crawl_mode: str
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class DashboardRunsSection(BaseModel):
    status_distribution: list[CountItem] = Field(default_factory=list)
    daily_trend: list[DailyTrendItem] = Field(default_factory=list)
    recent: list[RecentCrawlerRun] = Field(default_factory=list)


class DashboardMovieStorageStatus(BaseModel):
    stored: int = 0
    storing: int = 0
    not_stored: int = 0


class DashboardContentSection(BaseModel):
    movie_total: int = 0
    storage_status: DashboardMovieStorageStatus = Field(default_factory=DashboardMovieStorageStatus)


class DashboardStorageIndex(BaseModel):
    target_folder: str = ""
    status: str = "never_built"
    category_count: int = 0
    code_folder_count: int = 0
    video_count: int = 0
    completed_at: str | None = None
    errors: list[dict] = Field(default_factory=list)


class RecentStorageTask(BaseModel):
    id: str
    alias: str
    display_name: str
    status: str
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None


class DashboardStorageSection(BaseModel):
    task_status_distribution: list[CountItem] = Field(default_factory=list)
    recent_tasks: list[RecentStorageTask] = Field(default_factory=list)
    index: DashboardStorageIndex = Field(default_factory=DashboardStorageIndex)


class DashboardAlert(BaseModel):
    id: str
    title: str
    description: str
    severity: AlertSeverity
    source: str
    target_path: str | None = None
    occurred_at: str | None = None


class PartialError(BaseModel):
    section: str
    message: str


class DashboardOverview(BaseModel):
    system_status: SystemStatus
    refreshed_at: str
    crawler: DashboardCrawlerSection = Field(default_factory=DashboardCrawlerSection)
    runs: DashboardRunsSection = Field(default_factory=DashboardRunsSection)
    content: DashboardContentSection = Field(default_factory=DashboardContentSection)
    storage: DashboardStorageSection = Field(default_factory=DashboardStorageSection)
    alerts: list[DashboardAlert] = Field(default_factory=list)
    partial_errors: list[PartialError] = Field(default_factory=list)


class DashboardOverviewDraft(BaseModel):
    queue_status: dict
    index_status: str
    index_errors: list[dict] = Field(default_factory=list)
    failed_run_count: int = 0
    failed_storage_count: int = 0
    stopped_runtime_count: int = 0
    running_runtime_count: int = 0
