import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TaskUrlEntryBase(BaseModel):
    url: str = Field(..., min_length=1)
    url_type: str = Field(..., min_length=1, max_length=50)
    has_magnet: bool = False
    has_chinese_sub: bool = False
    sort_type: int = Field(default=0, ge=0)
    final_url: str | None = None
    source: str | None = None
    url_name: str | None = Field(default=None, max_length=200)


class TaskUrlEntryCreate(TaskUrlEntryBase):
    pass


class TaskUrlEntryRead(TaskUrlEntryBase):
    id: uuid.UUID
    position: int
    source: str
    final_url: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CrawlTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    urls: list[TaskUrlEntryCreate] = Field(..., min_length=1)
    is_skip: bool = False


class CrawlTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    urls: list[TaskUrlEntryCreate] | None = None
    is_skip: bool | None = None


class CrawlTaskRead(BaseModel):
    id: uuid.UUID
    _id: uuid.UUID
    name: str
    urls: list[TaskUrlEntryRead]
    is_skip: bool
    status: str
    task_id: str | None = None
    error_message: str | None = None
    total_found: int
    total_qualified: int
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExtractNameRequest(BaseModel):
    url: str = Field(..., min_length=1)
    url_type: str = Field(..., min_length=1)


class ExtractNameResponse(BaseModel):
    name: str
