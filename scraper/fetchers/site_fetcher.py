from __future__ import annotations

from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig, read_crawler_runtime_config
from scraper.config.sites import JAVBUS_SITE, JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.fetchers.javdb_browser_session import JavDBBrowserSession
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher


def build_site_fetcher(
    source: str = "javdb",
    runtime_config: CrawlerRuntimeConfig | None = None,
) -> ScraplingFetcher:
    active_config = runtime_config or read_crawler_runtime_config()
    site_config = JAVBUS_SITE if source == "javbus" else JAVDB_SITE
    cookie_manager = CookieManager(site_config["cookie_file"])
    cookies = cookie_manager.load()
    use_browser = source == "javdb" and active_config.JAVDB_FETCH_MODE == "browser"
    browser_session = JavDBBrowserSession() if use_browser else None
    return ScraplingFetcher(
        headers=site_config["headers"],
        cookies=cookies,
        browser_cookies=cookie_manager.load_browser_cookies() if use_browser else [],
        timeout=active_config.REQUEST_TIMEOUT,
        dynamic=use_browser,
        browser_session=browser_session,
    )
