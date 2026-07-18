import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    source_url_name: str | None = None
    task_url: str | None = None
    task_final_url: str | None = None
    task_url_type: str | None = None
    status: str
    error: str | None
    item_data: dict[str, Any] | None
    created_at: datetime
    crawled_at: datetime | None
    saved_at: datetime | None
    display_code: str | None = None
    display_source_name: str | None = None


class RunDetailRetryRequest(BaseModel):
    detail_ids: list[uuid.UUID] = Field(default_factory=list)
    retry_all: bool = False


class RunTaskSummary(BaseModel):
    total: int = 0
    pending_crawl: int = 0
    crawling: int = 0
    saved: int = 0
    skipped: int = 0
    crawl_failed: int = 0
    save_failed: int = 0
    completed: int = 0
    waiting: int = 0
    failed: int = 0


TEMPORARY_SOURCE_NAMES = {"临时详情页", "临时任务", ""}


def _item_data_text(row: Any, key: str) -> str:
    item_data = row.item_data if isinstance(row.item_data, dict) else {}
    value = item_data.get(key)
    return str(value or "").strip()


def _serialize_run_detail_task(row: Any) -> dict:
    payload = CrawlRunDetailTaskRead.model_validate(row).model_dump(mode="json")
    display_code = str(row.code or "").strip() or _item_data_text(row, "code") or None
    source_name = str(row.source_name or "").strip()
    if source_name in TEMPORARY_SOURCE_NAMES:
        source_name = _item_data_text(row, "source_name") or _item_data_text(row, "name") or source_name
    payload["display_code"] = display_code
    payload["display_source_name"] = source_name or None
    return payload
