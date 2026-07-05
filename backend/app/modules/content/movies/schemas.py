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


class MovieStorageSyncFilters(BaseModel):
    search: str | None = None
    source_task_id: str | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    actors: str | None = None
    actors_not: str | None = None
    actors_count_min: int | None = None
    actors_count_max: int | None = None
    tags: str | None = None
    tags_not: str | None = None
    director: str | None = None
    director_not: str | None = None
    maker: str | None = None
    maker_not: str | None = None
    series: str | None = None
    series_not: str | None = None
    release_date_from: str | None = None
    release_date_to: str | None = None
    created_at_from: str | None = None
    created_at_to: str | None = None
    storage_status: str | None = None


class MovieStorageSyncRequest(BaseModel):
    movie_ids: list[uuid.UUID] = []
    filters: MovieStorageSyncFilters | None = None


class MovieStorageSyncResponse(BaseModel):
    total: int
    stored_count: int
    not_stored_count: int
    results: list[dict[str, Any]]


class MovieDeleteRequest(BaseModel):
    movie_ids: list[uuid.UUID]
    mode: str = "database_only"


class MovieDeleteResponse(BaseModel):
    deleted_movies: int
    deleted_magnets: int
    updated_movies: int
    cloud_deleted_folders: list[str]
    cloud_missing_folders: list[str]
    cloud_failed_folders: list[dict[str, Any]]
