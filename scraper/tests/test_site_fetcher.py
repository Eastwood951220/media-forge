from backend.app.modules.crawler.config.conf_reader import CrawlerRuntimeConfig
from scraper.fetchers.site_fetcher import build_site_fetcher

import pytest


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


def test_build_site_fetcher_uses_avjoho_site_without_javdb_cookies(monkeypatch) -> None:
    loaded_cookie_files = []

    def fake_load(self):
        loaded_cookie_files.append(self.filepath.name)
        return {"avjoho_session": "profile"}

    monkeypatch.setattr("scraper.fetchers.site_fetcher.CookieManager.load", fake_load)

    fetcher = build_site_fetcher("avjoho", CrawlerRuntimeConfig(REQUEST_TIMEOUT=12))

    assert fetcher.timeout == 12
    assert fetcher.cookies == {"avjoho_session": "profile"}
    assert loaded_cookie_files == ["avjoho_cookies.json"]
    assert "User-Agent" in fetcher.headers


def test_build_site_fetcher_rejects_unsupported_source() -> None:
    with pytest.raises(ValueError):
        build_site_fetcher("unknown")
