from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.modules.backup.groups import DEFAULT_BACKUP_GROUPS, BackupGroup

BackupOperation = Literal["export", "inspect", "restore", "auto_export", "delete"]
BackupJobStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
RestoreMode = Literal["merge", "overwrite"]
ScheduleType = Literal["daily", "weekly", "monthly"]


class BackupConfig(BaseModel):
    enabled: bool = False
    backup_dir: str
    schedule_type: ScheduleType = "daily"
    time_of_day: str = "03:30"
    weekdays: list[int] = Field(default_factory=list)
    monthdays: list[int] = Field(default_factory=list)
    groups: list[BackupGroup] = Field(default_factory=lambda: list(DEFAULT_BACKUP_GROUPS))
    include_sensitive: bool = False
    retention_count: int = Field(default=10, ge=1, le=365)

    @field_validator("time_of_day")
    @classmethod
    def validate_time_of_day(cls, value: str) -> str:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("time_of_day must be HH:MM")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain values from 0 to 6")
        return sorted(set(value))

    @field_validator("monthdays")
    @classmethod
    def validate_monthdays(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 31 for day in value):
            raise ValueError("monthdays must contain values from 1 to 31")
        return sorted(set(value))

    @model_validator(mode="after")
    def normalize_schedule_days(self) -> "BackupConfig":
        if self.schedule_type == "daily":
            self.weekdays = []
            self.monthdays = []
        elif self.schedule_type == "weekly":
            self.monthdays = []
        elif self.schedule_type == "monthly":
            self.weekdays = []
        return self


class BackupConfigUpdate(BaseModel):
    enabled: bool | None = None
    backup_dir: str | None = None
    schedule_type: ScheduleType | None = None
    time_of_day: str | None = None
    weekdays: list[int] | None = None
    monthdays: list[int] | None = None
    groups: list[BackupGroup] | None = None
    include_sensitive: bool | None = None
    retention_count: int | None = Field(default=None, ge=1, le=365)


class BackupJob(BaseModel):
    id: UUID
    operation: BackupOperation
    status: BackupJobStatus = "pending"
    phase: str = "pending"
    processed: int = 0
    total: int | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class BackupFileInfo(BaseModel):
    name: str
    path: str
    size: int
    created_at: datetime
    groups: list[BackupGroup] = Field(default_factory=list)
    include_sensitive: bool = False


class BackupExportRequest(BaseModel):
    groups: list[BackupGroup] = Field(default_factory=lambda: list(DEFAULT_BACKUP_GROUPS))
    include_sensitive: bool = False


class BackupInspectResult(BaseModel):
    manifest: dict[str, Any]
    groups: list[BackupGroup]
    row_counts: dict[str, int]
    include_sensitive: bool


class BackupRestoreRequest(BaseModel):
    mode: RestoreMode = "merge"
    groups: list[BackupGroup] = Field(default_factory=lambda: list(DEFAULT_BACKUP_GROUPS))


class BackupJobResponse(BaseModel):
    job_id: UUID
