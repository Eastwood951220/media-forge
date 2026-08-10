from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException

from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
from backend.app.schemas.crawl_task import ExtractNameRequest
from scraper.config.sites import JAVBUS_SITE, JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.core.security import detect_access_state
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.spiders.javdb.javdb_parser import parse_page_section_name
from scraper.spiders.registry import get_site_spider
from scraper.tasks.task_utils import determine_source

logger = logging.getLogger(__name__)


def extract_task_name(body: ExtractNameRequest) -> str:
    """Extract task name from a URL.

    For search URLs, parses the ``q`` query parameter.
    For other URL types, detects the source and delegates to the appropriate
    site plugin for name extraction.
    """
    if body.url_type == "search":
        parsed = urlparse(body.url)
        q_values = parse_qs(parsed.query).get("q", [])
        return q_values[0].strip() if q_values else ""

    source = determine_source(body.url)
    if source == "unknown":
        raise HTTPException(status_code=400, detail="不支持的 URL 来源")

    try:
        runtime_config = read_crawler_runtime_config()
        site_config = JAVBUS_SITE if source == "javbus" else JAVDB_SITE
        cookie_manager = CookieManager(site_config["cookie_file"])
        fetcher = ScraplingFetcher(
            headers=site_config["headers"],
            cookies=cookie_manager.load(),
            timeout=runtime_config.REQUEST_TIMEOUT,
        )

        if source == "javbus":
            spider = get_site_spider(source, fetcher=fetcher)
            name = spider.extract_url_name(body.url, body.url_type)
            return name or ""

        page = fetcher.get(body.url)
        access_state = detect_access_state(page)
        if not access_state.ok:
            raise HTTPException(status_code=429, detail=access_state.message)

        name = parse_page_section_name(page, body.url_type)
        if not name and body.url_type not in {"search"}:
            raise HTTPException(
                status_code=502,
                detail="JavDB 页面可访问，但未解析到名称，请检查 URL 类型或页面结构",
            )
        return name
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Extract task URL name failed: %s", body.url)
        raise HTTPException(status_code=500, detail=f"提取名称失败: {exc}") from exc
