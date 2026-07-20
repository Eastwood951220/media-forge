from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def build_crawl_task_from_doc(doc: dict[str, Any]) -> CrawlTask:
    """Build a CrawlTask from a persisted crawl task record."""
    urls: list[CrawlTaskUrlEntry] = []

    # New format: urls array
    if "urls" in doc and isinstance(doc["urls"], list):
        for entry in doc["urls"]:
            urls.append(CrawlTaskUrlEntry(
                url=entry["url"],
                url_type=entry["url_type"],
                has_magnet=entry.get("has_magnet", False),
                has_chinese_sub=entry.get("has_chinese_sub", False),
                sort_type=entry.get("sort_type", 0),
                source=entry.get("source"),
                final_url=entry.get("final_url"),
                url_name=entry.get("url_name"),
            ))
    # Legacy format: single url field
    elif "url" in doc:
        urls.append(CrawlTaskUrlEntry(
            url=doc["url"],
            url_type=doc.get("url_type", ""),
            has_magnet=doc.get("has_magnet", False),
            has_chinese_sub=doc.get("has_chinese_sub", False),
            sort_type=doc.get("sort_type", 0),
            source=doc.get("source"),
            final_url=doc.get("final_url"),
        ))

    return CrawlTask(
        name=doc["name"],
        urls=urls,
        is_skip=doc.get("is_skip", False),
    )


def ensure_string(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def determine_source(url: str) -> str:
    parsed = urlparse(ensure_string(url))
    hostname = (parsed.hostname or "").lower()

    if not hostname or parsed.scheme not in ("http", "https"):
        return "unknown"

    if hostname == "javdb.com" or hostname.endswith(".javdb.com"):
        return "javdb"

    if hostname == "javbus.com" or hostname == "www.javbus.com":
        return "javbus"

    return "unknown"


def append_or_replace_query(url: str, params: dict) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value is not None})
    new_query = urlencode(
        query,
        doseq=True,
        quote_via=lambda v, safe, enc, err: quote(str(v), safe=safe + ","),
    )

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def _build_filter_params(
    url_type: str,
    has_magnet: bool,
    has_chinese_sub: bool,
) -> dict[str, str]:
    """Build filter query params based on URL type and flags."""
    if not has_magnet and not has_chinese_sub:
        return {}

    filters: list[str] = []
    if has_chinese_sub:
        filters.append("c" if url_type in ("actors", "actor") else "cnsub")
    if has_magnet:
        filters.append("d" if url_type in ("actors", "actor") else "download")

    if url_type in ("actors", "actor"):
        return {"t": ",".join(filters)}

    if url_type == "tags":
        tag_filters: list[str] = []
        if has_magnet:
            tag_filters.append("1")
        if has_chinese_sub:
            tag_filters.append("2")
        return {"c10": ",".join(tag_filters)}

    return {"f": ",".join(filters)}


def build_final_url(
    url: str,
    url_type: str,
    has_magnet: bool = False,
    has_chinese_sub: bool = False,
    sort_type: int = 0,
    source: str | None = None,
) -> str:
    url = ensure_string(url)
    url_type = ensure_string(url_type).lower()

    if not url:
        return ""

    if source == "javbus":
        return url

    params: dict[str, str | int] = {"page": 1}

    filter_params = _build_filter_params(url_type, has_magnet, has_chinese_sub)
    params.update(filter_params)

    if url_type in ("actors", "series", "makers", "directors", "video_codes"):
        params["sort_type"] = sort_type

    # search type uses sb param: 0=relevance, 1=date
    if url_type == "search":
        params["sb"] = sort_type

    if url_type == "search" and "?" not in url:
        params.setdefault("f", "all")

    return append_or_replace_query(url, params)


def build_page_url(final_url: str, page: int) -> str:
    return append_or_replace_query(final_url, {"page": page})
