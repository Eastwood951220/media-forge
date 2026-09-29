from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class PageActionTaskChoice(BaseModel):
    id: uuid.UUID
    name: str


class TemporaryPageRunCreate(BaseModel):
    task_id: uuid.UUID
    detail_url: str


class QuickCreatePageRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    page_name: str = Field(min_length=1, max_length=200)
    list_url: str = Field(min_length=1)


class AddUrlPageRunCreate(BaseModel):
    task_id: uuid.UUID
    page_name: str = Field(min_length=1, max_length=200)
    list_url: str = Field(min_length=1)


class PageActionRunResult(BaseModel):
    task_id: uuid.UUID
    task_name: str
    run_id: uuid.UUID
    crawl_mode: Literal["temporary", "full", "incremental"]
    accepted: bool
    runtime_error: str | None = None
    url_entry_id: uuid.UUID | None = None
    url_added: bool | None = None
