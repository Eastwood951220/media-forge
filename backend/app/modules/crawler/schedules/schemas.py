import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ScheduleType = Literal["daily", "weekly"]
StorageMode = Literal["single", "multiple"]
TriggerType = Literal["scheduled", "manual"]


class CrawlerScheduleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    enabled: bool = True
    schedule_type: ScheduleType
    time_of_day: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] = Field(default_factory=list)
    auto_storage_enabled: bool = False
    storage_mode: StorageMode = "single"
    selected_storage_location: str | None = Field(default=None, max_length=500)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain values from 0 to 6")
        return value


class CrawlerScheduleCreate(CrawlerScheduleBase):
    task_ids: list[uuid.UUID] = Field(..., min_length=1)


class CrawlerScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    task_ids: list[uuid.UUID] | None = None
    schedule_type: ScheduleType | None = None
    time_of_day: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] | None = None
    auto_storage_enabled: bool | None = None
    storage_mode: StorageMode | None = None
    selected_storage_location: str | None = Field(default=None, max_length=500)


class CrawlerScheduleTaskSummary(BaseModel):
    id: uuid.UUID
    name: str
    is_skip: bool


class CrawlerScheduleRead(CrawlerScheduleBase):
    id: uuid.UUID
    task_count: int
    tasks: list[CrawlerScheduleTaskSummary] = []
    last_triggered_at: datetime | None = None
    next_run_at: datetime | None = None
    latest_run_status: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CrawlerScheduleListResponse(BaseModel):
    rows: list[CrawlerScheduleRead]
    total: int
    page: int
    size: int
