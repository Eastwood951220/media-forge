from scraper.fetchers import scrapling_fetcher as module
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher, normalize_browser_cookies


def test_normalize_browser_cookies_maps_export_fields() -> None:
    cookies = normalize_browser_cookies(
        [
            {
                "domain": "javdb.com",
                "expirationDate": 1787586161.0,
                "httpOnly": True,
                "name": "_jdb_session",
                "path": "/",
                "sameSite": "no_restriction",
                "secure": True,
                "value": "secret",
            },
            {"domain": "javdb.com", "name": "locale", "path": "/", "sameSite": "lax", "value": "zh"},
        ]
    )

    assert cookies == [
        {
            "name": "_jdb_session",
            "value": "secret",
            "domain": "javdb.com",
            "path": "/",
            "expires": 1787586161.0,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        },
        {
            "name": "locale",
            "value": "zh",
            "domain": "javdb.com",
            "path": "/",
            "sameSite": "Lax",
        },
    ]


def test_static_fetcher_uses_chrome_impersonation(monkeypatch) -> None:
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(module.Fetcher, "get", fake_get)

    fetcher = ScraplingFetcher(headers={"User-Agent": "Agent"}, cookies={"locale": "zh"})
    fetcher.get("https://javdb.com/")

    assert captured["kwargs"]["headers"] == {"User-Agent": "Agent"}
    assert captured["kwargs"]["cookies"] == {"locale": "zh"}
    assert captured["kwargs"]["impersonate"] == "chrome"


def test_browser_fetcher_delegates_to_persistent_session() -> None:
    calls = {}

    class FakeBrowserSession:
        def fetch(self, url, *, headers=None, timeout=30):
            calls["url"] = url
            calls["headers"] = headers
            calls["timeout"] = timeout

            class FakePage:
                text = "JavDB 成人影片數據庫"
                status_code = 200

            return FakePage()

    fetcher = ScraplingFetcher(
        headers={"Accept-Language": "zh-CN"},
        timeout=45,
        dynamic=True,
        browser_session=FakeBrowserSession(),
    )

    page = fetcher.get("https://javdb.com/actors/8VGXO")

    assert page.status_code == 200
    assert calls == {
        "url": "https://javdb.com/actors/8VGXO",
        "headers": {"Accept-Language": "zh-CN"},
        "timeout": 45,
    }
