import json

from scraper.cookies.cookie_manager import COOKIE_DIR, CookieManager


def test_load_browser_cookies_preserves_browser_export_rows(monkeypatch, tmp_path) -> None:
    cookie_dir = tmp_path / "cookies"
    monkeypatch.setattr("scraper.cookies.cookie_manager.COOKIE_DIR", cookie_dir)
    cookie_dir.mkdir(parents=True)
    rows = [
        {
            "domain": "javdb.com",
            "expirationDate": 1787586161.0,
            "hostOnly": True,
            "httpOnly": True,
            "name": "_jdb_session",
            "path": "/",
            "sameSite": "no_restriction",
            "secure": True,
            "session": False,
            "storeId": None,
            "value": "secret",
        },
        {"domain": "javdb.com", "name": "locale", "path": "/", "value": "zh"},
        {"domain": "javdb.com", "name": "", "value": "missing-name"},
        {"domain": "javdb.com", "name": "missing-value"},
        "not-a-cookie",
    ]
    (cookie_dir / "javdb_cookies.json").write_text(json.dumps(rows), encoding="utf-8")

    cookies = CookieManager("javdb_cookies.json").load_browser_cookies()

    assert cookies == rows[:2]


def test_load_browser_cookies_converts_flat_dict_to_browser_rows(monkeypatch, tmp_path) -> None:
    cookie_dir = tmp_path / "cookies"
    monkeypatch.setattr("scraper.cookies.cookie_manager.COOKIE_DIR", cookie_dir)
    cookie_dir.mkdir(parents=True)
    (cookie_dir / "javdb_cookies.json").write_text(
        json.dumps({"_jdb_session": "secret", "locale": "zh"}),
        encoding="utf-8",
    )

    cookies = CookieManager("javdb_cookies.json").load_browser_cookies()

    assert cookies == [
        {"name": "_jdb_session", "value": "secret", "domain": "javdb.com", "path": "/"},
        {"name": "locale", "value": "zh", "domain": "javdb.com", "path": "/"},
    ]


def test_load_browser_cookies_returns_empty_for_missing_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scraper.cookies.cookie_manager.COOKIE_DIR", tmp_path / "cookies")

    assert CookieManager("javdb_cookies.json").load_browser_cookies() == []
