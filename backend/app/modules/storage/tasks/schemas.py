from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StorageSinglePushRequest(BaseModel):
    movie_id: UUID
    alias: str | None = Field(default=None, max_length=240)
    storage_mode: str = "single"
    selected_storage_location: str | None = Field(default=None, max_length=500)


class StorageBatchPushRequest(BaseModel):
    movie_ids: list[UUID]
    alias: str | None = Field(default=None, max_length=240)
    storage_mode: str = "single"


class StorageMainTaskResponse(BaseModel):
    id: str
    alias: str
    display_name: str
    source: str
    storage_mode: str
    status: str
    total_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
