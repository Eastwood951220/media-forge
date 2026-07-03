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


class StorageSubTaskResponse(BaseModel):
    id: str
    main_task_id: str
    movie_id: str
    movie_code: str
    movie_title: str
    status: str
    step: str
    storage_mode: str
    selected_storage_location: str | None = None
    target_locations: list[str] = []
    download_path: str = ""
    target_paths: list[str] = []
    magnet_attempts: list[dict] = []
    current_magnet_id: str | None = None
    current_magnet_url: str = ""
    renamed_files: list[dict] = []
    moved_files: list[dict] = []
    skipped_files: list[dict] = []
    result: dict = {}
    skip_reason: str | None = None
    error_message: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class StorageTaskLogResponse(BaseModel):
    timestamp: str
    level: str
    message: str
    context: dict = {}
