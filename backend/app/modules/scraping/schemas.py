from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_BASE_URL = "http://192.168.0.36:12333"


class ScrapingConfig(BaseModel):
    """Persisted scraping settings."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int = Field(default=30, ge=10, le=3600)


class ScrapingConfigUpdate(BaseModel):
    """Partial update; omitted fields keep their stored values."""

    base_url: str | None = None
    api_key: str | None = None
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int | None = Field(default=None, ge=10, le=3600)


class ScrapingConfigResponse(ScrapingConfig):
    api_key: str = ""
    api_key_configured: bool = False
