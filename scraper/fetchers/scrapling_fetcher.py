from __future__ import annotations

from typing import Any

from scrapling.fetchers import Fetcher

from scraper.fetchers.javdb_browser_session import JavDBBrowserSession


def _normalize_same_site(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text == "lax":
        return "Lax"
    if text == "strict":
        return "Strict"
    if text in {"none", "no_restriction"}:
        return "None"
    return None


def normalize_browser_cookies(cookies: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for cookie in cookies or []:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue

        item: dict[str, Any] = {
            "name": str(name),
            "value": str(value),
        }
        if cookie.get("domain"):
            item["domain"] = str(cookie["domain"])
        if cookie.get("path"):
            item["path"] = str(cookie["path"])
        if cookie.get("expirationDate") is not None:
            item["expires"] = float(cookie["expirationDate"])
        if cookie.get("httpOnly") is not None:
            item["httpOnly"] = bool(cookie["httpOnly"])
        if cookie.get("secure") is not None:
            item["secure"] = bool(cookie["secure"])
        same_site = _normalize_same_site(cookie.get("sameSite"))
        if same_site:
            item["sameSite"] = same_site
        elif item.get("domain") == "javdb.com":
            item["sameSite"] = "Lax"
        normalized.append(item)
    return normalized


class ScraplingFetcher:
    def __init__(
        self,
        headers: dict | None = None,
        cookies: dict | None = None,
        browser_cookies: list[dict] | None = None,
        timeout: int = 30,
        dynamic: bool = False,
        browser_session: JavDBBrowserSession | None = None,
    ):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.browser_cookies = browser_cookies or []
        self.timeout = timeout
        self.dynamic = dynamic
        self.browser_session = browser_session

    def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
    ):
        merged_headers = {**self.headers, **(headers or {})}
        merged_cookies = {**self.cookies, **(cookies or {})}

        if self.dynamic:
            return self._browser_get(url, headers=merged_headers)

        return Fetcher.get(
            url,
            headers=merged_headers,
            cookies=merged_cookies,
            timeout=self.timeout,
            impersonate="chrome",
        )

    def _browser_get(self, url: str, *, headers: dict):
        session = self.browser_session or JavDBBrowserSession()
        return session.fetch(url, headers=headers, timeout=self.timeout)
