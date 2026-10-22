from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceMetadata:
    site_key: str
    title: str | None = None
    original_title: str | None = None
    year: int | None = None
    premiered: str | None = None
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    studio: str | None = None
    series: str | None = None
    actors: list[str] = field(default_factory=list)
    cover_url: str | None = None
    backdrop_url: str | None = None
    landscape_url: str | None = None
    preview_urls: list[str] = field(default_factory=list)
