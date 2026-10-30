from __future__ import annotations

from urllib.parse import urlsplit

from backend.app.modules.scraping.metatube import fetch_metatube_movie, is_metatube_source
from backend.app.modules.scraping.source_types import SourceMetadata


_REFERER_BY_HOST = {
    "javdb.com": "https://javdb.com/",
    "www.javdb.com": "https://javdb.com/",
    "javbus.com": "https://www.javbus.com/",
    "www.javbus.com": "https://www.javbus.com/",
}


def source_referer(site_key: str) -> str | None:
    return {
        "JavDB": "https://javdb.com/",
        "JavBus": "https://www.javbus.com/",
        "FANZA": "https://video.dmm.co.jp/",
    }.get(site_key)


def referer_for_url(url: str | None) -> str | None:
    """Use the original site's referer for pre-existing cover URLs."""
    try:
        host = urlsplit(str(url or "").strip()).hostname
    except ValueError:
        return None
    return _REFERER_BY_HOST.get(host.lower()) if host else None


def fetch_by_priority(
    code: str, sources: list[str], *, metatube_url: str = "", metatube_token: str = "",
) -> SourceMetadata | None:
    for source in sources:
        if not is_metatube_source(source):
            continue
        metadata = fetch_metatube_movie(
            code, source.partition(":")[2], base_url=metatube_url, token=metatube_token,
        )
        if metadata is not None:
            return metadata
    return None
