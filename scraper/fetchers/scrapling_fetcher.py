from __future__ import annotations

from scrapling.fetchers import Fetcher


class ScraplingFetcher:
    def __init__(
        self,
        headers: dict | None = None,
        cookies: dict | None = None,
        timeout: int = 30,
    ):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.timeout = timeout

    def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
    ):
        merged_headers = {**self.headers, **(headers or {})}
        merged_cookies = {**self.cookies, **(cookies or {})}
        return Fetcher.get(
            url,
            headers=merged_headers,
            cookies=merged_cookies,
            timeout=self.timeout,
            impersonate="chrome",
        )
