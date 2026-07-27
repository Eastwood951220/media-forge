from scraper.fetchers import scrapling_fetcher as module
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher


def test_static_fetcher_merges_request_headers_and_cookies(monkeypatch) -> None:
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(module.Fetcher, "get", fake_get)

    fetcher = ScraplingFetcher(
        headers={"User-Agent": "Agent", "Accept": "text/html"},
        cookies={"PHPSESSID": "session"},
        timeout=15,
    )
    fetcher.get(
        "https://www.javbus.com/ajax",
        headers={"Accept": "*/*", "Referer": "https://www.javbus.com/TIKB-224"},
        cookies={"existmag": "mag"},
    )

    assert captured["kwargs"]["headers"] == {
        "User-Agent": "Agent",
        "Accept": "*/*",
        "Referer": "https://www.javbus.com/TIKB-224",
    }
    assert captured["kwargs"]["cookies"] == {
        "PHPSESSID": "session",
        "existmag": "mag",
    }
    assert fetcher.headers == {"User-Agent": "Agent", "Accept": "text/html"}
    assert fetcher.cookies == {"PHPSESSID": "session"}
