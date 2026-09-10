import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ActressFetchFromTaskRequest(BaseModel):
    task_id: uuid.UUID
    task_url_id: uuid.UUID
    avjoho_url: str | None = Field(default=None, max_length=500)


class ActressRecentMovieRead(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    cover: str
    release_date: date | None


class ActressExternalLinkRead(BaseModel):
    id: uuid.UUID
    source: str
    label: str
    url: str
    url_type: str
    url_name: str


class ActressProfileRead(BaseModel):
    id: uuid.UUID
    display_name: str
    reading: str
    aliases: list[str]
    canonical_names: list[str]
    source_url: str
    source_site: str
    source_task_ids: list[uuid.UUID]
    source_task_url_ids: list[uuid.UUID]
    image_url: str
    debut_date: date | None
    birth_date: date | None
    height_cm: int | None
    bust_cm: int | None
    waist_cm: int | None
    hip_cm: int | None
    cup: str
    birthplace: str
    blood_type: str
    hobbies: str
    biography: str
    exclusive_maker: str
    sns_links: list[dict[str, Any]]
    representative_works: list[dict[str, Any]]
    similar_actresses: list[dict[str, Any]]
    raw_profile: dict[str, Any]
    last_fetched_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class ActressProfileDetailRead(ActressProfileRead):
    recent_movies: list[ActressRecentMovieRead]
    external_links: list[ActressExternalLinkRead]


class ActressFetchFromTaskResponse(BaseModel):
    matched: bool
    profiles: list[ActressProfileRead]
    candidates: list[str]
    message: str
