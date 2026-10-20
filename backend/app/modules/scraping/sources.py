from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.parse import quote

from scraper.config.sites import JAVBUS_SITE, JAVDB_SITE
from scraper.fetchers.site_fetcher import build_site_fetcher
from scraper.spiders.javbus.javbus_parser import parse_detail_page as parse_javbus_detail
from scraper.spiders.javbus.javbus_parser import parse_list_page as parse_javbus_list
from scraper.spiders.javdb.javdb_parser import parse_detail_page as parse_javdb_detail
from scraper.spiders.javdb.javdb_parser import parse_search_page as parse_javdb_search

from backend.app.modules.scraping.paths import normalize_code

logger = logging.getLogger(__name__)


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


class SourceAdapter(Protocol):
    key: str
    site_key: str

    def fetch_by_code(self, code: str) -> SourceMetadata | None: ...


def _clean(value: object) -> str:
    return str(value or "").strip()


class JavdbAdapter:
    key = "javdb"
    site_key = "JavDB"

    def __init__(self, fetcher_factory: Callable[[str], object] = build_site_fetcher) -> None:
        self.fetcher_factory = fetcher_factory

    def fetch_by_code(self, code: str) -> SourceMetadata | None:
        try:
            fetcher = self.fetcher_factory("javdb")
            base = JAVDB_SITE["base_url"].rstrip("/")
            search_url = f"{base}/search?q={quote(code)}&f=all"
            search_page = fetcher.get(search_url)
            tasks = parse_javdb_search(search_page, 1)
            wanted = normalize_code(code)
            target = next(
                (task for task in tasks if normalize_code(task.get("code") or "") == wanted and task.get("status") != "skipped"),
                tasks[0] if tasks else None,
            )
            if target is None or not target.get("url"):
                return None
            detail = parse_javdb_detail(fetcher.get(target["url"]))
            return SourceMetadata(
                site_key=self.site_key,
                title=_clean(detail.get("source_name")) or None,
                original_title=_clean(detail.get("source_name")) or None,
                premiered=_clean(detail.get("release_date")) or None,
                genres=list(detail.get("tags") or []),
                tags=list(detail.get("tags") or []),
                studio=_clean(detail.get("maker")) or None,
                series=_clean(detail.get("series")) or None,
                actors=list(detail.get("actors") or []),
                cover_url=_clean(detail.get("cover")) or None,
            )
        except Exception:
            logger.warning("javdb metadata fetch failed for %s", code, exc_info=True)
            return None


class JavbusAdapter:
    key = "javbus"
    site_key = "JavBus"

    def __init__(self, fetcher_factory: Callable[[str], object] = build_site_fetcher) -> None:
        self.fetcher_factory = fetcher_factory

    def fetch_by_code(self, code: str) -> SourceMetadata | None:
        try:
            fetcher = self.fetcher_factory("javbus")
            base = JAVBUS_SITE["base_url"].rstrip("/")
            search_url = f"{base}/search/{quote(code)}"
            search_page = fetcher.get(search_url)
            movies, _page = parse_javbus_list(search_page, search_url)
            wanted = normalize_code(code)
            target = next((movie for movie in movies if normalize_code(movie.get("code") or "") == wanted), None)
            if target is None or not target.get("source_url"):
                return None
            detail = parse_javbus_detail(fetcher.get(target["source_url"]), target["source_url"])
            return SourceMetadata(
                site_key=self.site_key,
                title=_clean(detail.get("source_name")) or None,
                original_title=_clean(detail.get("source_name")) or None,
                premiered=_clean(detail.get("release_date")) or None,
                genres=list(detail.get("tags") or []),
                tags=list(detail.get("tags") or []),
                studio=_clean(detail.get("maker")) or None,
                series=_clean(detail.get("series")) or None,
                actors=list(detail.get("actors") or []),
                cover_url=_clean(detail.get("cover_url")) or None,
                backdrop_url=_clean(detail.get("cover_url")) or None,
            )
        except Exception:
            logger.warning("javbus metadata fetch failed for %s", code, exc_info=True)
            return None


SOURCE_REGISTRY: dict[str, SourceAdapter] = {
    "javdb": JavdbAdapter(),
    "javbus": JavbusAdapter(),
}
SOURCE_LABELS = {
    "javdb": "JavDB",
    "javbus": "JavBus",
}


def fetch_with_source(source: str, code: str) -> SourceMetadata | None:
    adapter = SOURCE_REGISTRY.get(source)
    if adapter is None:
        return None
    return adapter.fetch_by_code(code)


def fetch_by_priority(code: str, sources: list[str]) -> SourceMetadata | None:
    for source in sources:
        metadata = fetch_with_source(source, code)
        if metadata is not None:
            return metadata
    return None
