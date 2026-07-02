import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CrawlTaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    target_websites: list[str] = Field(default_factory=list)
    schedule: str | None = None
    max_pages: int = Field(default=100, ge=1, le=10000)
    crawl_depth: int = Field(default=3, ge=1, le=10)


class CrawlTaskCreate(CrawlTaskBase):
    pass


class CrawlTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    keywords: list[str] | None = None
    target_websites: list[str] | None = None
    schedule: str | None = None
    max_pages: int | None = Field(default=None, ge=1, le=10000)
    crawl_depth: int | None = Field(default=None, ge=1, le=10)


class CrawlTaskRead(CrawlTaskBase):
    id: uuid.UUID
    status: str
    task_id: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_found: int
    total_qualified: int
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
