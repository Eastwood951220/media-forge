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


def test_browser_fetcher_returns_adaptor_with_status(monkeypatch) -> None:
    events = {}

    class FakeResponse:
        status = 200

    class FakePage:
        def set_default_timeout(self, timeout):
            events["timeout"] = timeout

        def set_extra_http_headers(self, headers):
            events["headers"] = headers

        def goto(self, url, wait_until, timeout):
            events["goto"] = (url, wait_until, timeout)
            return FakeResponse()

        def wait_for_load_state(self, state, timeout):
            events["load_state"] = (state, timeout)

        def content(self):
            return '<html><body><div class="actor-section-name">Name</div></body></html>'

    class FakeContext:
        def add_cookies(self, cookies):
            events["cookies"] = cookies

        def new_page(self):
            return FakePage()

        def close(self):
            events["context_closed"] = True

    class FakeBrowser:
        def new_context(self, locale):
            events["locale"] = locale
            return FakeContext()

        def close(self):
            events["browser_closed"] = True

    class FakeChromium:
        def launch(self, headless):
            events["headless"] = headless
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            events["playwright_closed"] = True

    monkeypatch.setattr(module, "sync_playwright", lambda: FakeSyncPlaywright())

    fetcher = ScraplingFetcher(
        headers={"Accept-Language": "zh-CN"},
        browser_cookies=[{"domain": "javdb.com", "name": "locale", "path": "/", "value": "zh"}],
        timeout=30,
        dynamic=True,
    )
    page = fetcher.get("https://javdb.com/actors/8VGXO")

    assert page.status_code == 200
    assert page.css(".actor-section-name::text").get() == "Name"
    assert events["cookies"] == [{"name": "locale", "value": "zh", "domain": "javdb.com", "path": "/", "sameSite": "Lax"}]
    assert events["headers"] == {"Accept-Language": "zh-CN"}
    assert events["goto"] == ("https://javdb.com/actors/8VGXO", "domcontentloaded", 30000)
    assert events["headless"] is True
    assert events["browser_closed"] is True
