from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig
from scraper.fetchers.site_fetcher import build_site_fetcher


def test_javdb_agent_mode_does_not_use_dynamic_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "scraper.fetchers.site_fetcher.CookieManager.load",
        lambda self: {"locale": "zh"},
    )

    fetcher = build_site_fetcher(
        "javdb",
        CrawlerRuntimeConfig(JAVDB_FETCH_MODE="agent", JAVDB_AGENT_PARSE_MODE="backend"),
    )

    assert fetcher.cookies == {"locale": "zh"}
    assert not hasattr(fetcher, "browser_session")
    assert not getattr(fetcher, "dynamic", False)


def test_build_site_fetcher_keeps_javbus_static(monkeypatch) -> None:
    monkeypatch.setattr(
        "scraper.fetchers.site_fetcher.CookieManager.load",
        lambda self: {"existmag": "mag"},
    )
    runtime_config = CrawlerRuntimeConfig(REQUEST_TIMEOUT=20, JAVDB_FETCH_MODE="agent")

    fetcher = build_site_fetcher("javbus", runtime_config)

    assert getattr(fetcher, "dynamic", False) is False
    assert fetcher.timeout == 20
    assert fetcher.cookies == {"existmag": "mag"}


def test_build_site_fetcher_reads_avjoho_cookies_not_javdb_cookies(monkeypatch) -> None:
    opened_cookie_files: list[str] = []

    class RecordingCookieManager:
        def __init__(self, filepath) -> None:
            opened_cookie_files.append(str(filepath))

        def load(self) -> dict:
            return {"javdb_session": "secret"} if "javdb" in opened_cookie_files[-1] else {}

    monkeypatch.setattr("scraper.fetchers.site_fetcher.CookieManager", RecordingCookieManager)

    fetcher = build_site_fetcher("avjoho", CrawlerRuntimeConfig(JAVDB_FETCH_MODE="agent"))

    assert opened_cookie_files == ["avjoho_cookies.json"]
    assert fetcher.cookies == {}
