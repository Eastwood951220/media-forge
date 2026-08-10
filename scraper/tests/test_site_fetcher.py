from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig
from scraper.fetchers.site_fetcher import build_site_fetcher


def test_build_site_fetcher_uses_browser_mode_for_javdb(monkeypatch) -> None:
    monkeypatch.setattr(
        "scraper.fetchers.site_fetcher.CookieManager.load",
        lambda self: {"locale": "zh"},
    )
    monkeypatch.setattr(
        "scraper.fetchers.site_fetcher.CookieManager.load_browser_cookies",
        lambda self: [{"domain": "javdb.com", "name": "locale", "path": "/", "value": "zh"}],
    )
    runtime_config = CrawlerRuntimeConfig(REQUEST_TIMEOUT=45, JAVDB_FETCH_MODE="browser")

    fetcher = build_site_fetcher("javdb", runtime_config)

    assert fetcher.dynamic is True
    assert fetcher.timeout == 45
    assert fetcher.cookies == {"locale": "zh"}
    assert fetcher.browser_cookies == [{"domain": "javdb.com", "name": "locale", "path": "/", "value": "zh"}]


def test_build_site_fetcher_keeps_javbus_static(monkeypatch) -> None:
    monkeypatch.setattr(
        "scraper.fetchers.site_fetcher.CookieManager.load",
        lambda self: {"existmag": "mag"},
    )
    monkeypatch.setattr(
        "scraper.fetchers.site_fetcher.CookieManager.load_browser_cookies",
        lambda self: [{"domain": "javdb.com", "name": "locale", "path": "/", "value": "zh"}],
    )
    runtime_config = CrawlerRuntimeConfig(REQUEST_TIMEOUT=20, JAVDB_FETCH_MODE="browser")

    fetcher = build_site_fetcher("javbus", runtime_config)

    assert fetcher.dynamic is False
    assert fetcher.timeout == 20
    assert fetcher.cookies == {"existmag": "mag"}
    assert fetcher.browser_cookies == []
