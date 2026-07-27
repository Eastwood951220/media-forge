from scrapling.fetchers import DynamicFetcher, Fetcher


class ScraplingFetcher:
    def __init__(
        self,
        headers: dict | None = None,
        cookies: dict | None = None,
        timeout: int = 30,
        dynamic: bool = False,
    ):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.timeout = timeout
        self.dynamic = dynamic

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
            return DynamicFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                timeout=self.timeout,
                extra_headers=merged_headers,
            )

        return Fetcher.get(
            url,
            headers=merged_headers,
            cookies=merged_cookies,
            timeout=self.timeout,
        )
