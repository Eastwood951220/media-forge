import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RunCreateRequest(BaseModel):
    crawl_mode: Literal["incremental", "full"]


class RunLogEntry(BaseModel):
    timestamp: datetime
    level: str
    component: str | None = None
    event: str | None = None
    message: str
    context: dict[str, Any] = {}


class CrawlRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID | None
    task_name: str
    status: str
    crawl_mode: str
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    resumed_from: uuid.UUID | None
    created_at: datetime
    updated_at: datetime | None
    logs: list[RunLogEntry] = []


class CrawlRunDetailTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    task_name: str
    code: str | None
    source_url: str
    source_name: str
    status: str
    error: str | None
    item_data: dict[str, Any] | None
    created_at: datetime
    crawled_at: datetime | None
    saved_at: datetime | None
