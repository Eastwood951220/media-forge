from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_BASE_URL = "http://192.168.0.36:12333"
DEFAULT_MEDIA_ROOT = "/media"
DEFAULT_METADATA_SOURCES = ["javdb", "javbus"]


class ScrapingConfig(BaseModel):
    """Persisted scraping settings."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int = Field(default=30, ge=10, le=3600)
    scrape_root: str = ""
    media_root: str = DEFAULT_MEDIA_ROOT
    metadata_sources: list[str] = Field(default_factory=lambda: list(DEFAULT_METADATA_SOURCES))


class ScrapingConfigUpdate(BaseModel):
    """Partial update; omitted fields keep their stored values."""

    base_url: str | None = None
    api_key: str | None = None
    directory_id: int | None = Field(default=None, ge=1)
    trigger_delay_seconds: int | None = Field(default=None, ge=10, le=3600)
    scrape_root: str | None = None
    media_root: str | None = None
    metadata_sources: list[str] | None = None


class ScrapingConfigResponse(ScrapingConfig):
    api_key: str = ""
    api_key_configured: bool = False
