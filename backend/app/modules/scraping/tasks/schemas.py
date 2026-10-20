from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ScrapingTaskCreate(BaseModel):
    movie_ids: list[UUID] = Field(min_length=1, max_length=500)
