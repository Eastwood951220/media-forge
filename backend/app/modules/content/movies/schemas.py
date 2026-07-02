import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class MovieMagnetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    magnet_url: str
    info_hash: str | None
    name: str
    size_text: str
    has_chinese_sub: bool
    date: str
    selected: bool
    movie_id: uuid.UUID
    dedupe_key: str
    size_mb: Decimal | None
    file_count: int | None
    file_text: str
    tags: list[str]
    weight: int


class MovieRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str | None
    source_url: str | None
    source_name: str
    cover: str
    release_date: date | None
    duration: int
    director: str
    maker: str
    series: str
    rating: Decimal | None
    actors: list[str]
    tags: list[str]
    source_task_ids: list[uuid.UUID]
    storage_summary: dict[str, Any]
    raw_detail: dict[str, Any]
    marked: bool
    created_at: datetime
    updated_at: datetime | None


class MovieDetailRead(MovieRead):
    magnets: list[MovieMagnetRead] = []
