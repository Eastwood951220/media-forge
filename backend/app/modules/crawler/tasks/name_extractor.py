from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException

from backend.app.schemas.crawl_task import ExtractNameRequest
from scraper.config.settings import REQUEST_TIMEOUT
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.core.security import is_security_check_page
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.spiders.javdb.javdb_parser import parse_page_section_name

logger = logging.getLogger(__name__)


def extract_task_name(body: ExtractNameRequest) -> str:
    """Extract task name from a URL.

    For search URLs, parses the ``q`` query parameter.
    For other URL types, fetches the page and extracts the name via the
    JavDB parser.
    """
    if body.url_type == "search":
        parsed = urlparse(body.url)
        q_values = parse_qs(parsed.query).get("q", [])
        return q_values[0].strip() if q_values else ""

    try:
        cookie_manager = CookieManager(JAVDB_SITE["cookie_file"])
        fetcher = ScraplingFetcher(
            headers=JAVDB_SITE["headers"],
            cookies=cookie_manager.load(),
            timeout=REQUEST_TIMEOUT,
        )
        page = fetcher.get(body.url)
        if is_security_check_page(page):
            raise HTTPException(status_code=429, detail="触发安全验证，请稍后重试")
        return parse_page_section_name(page, body.url_type)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Extract task URL name failed: %s", body.url)
        raise HTTPException(status_code=500, detail=f"提取名称失败: {exc}") from exc
