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

    def get(self, url: str):
        if self.dynamic:
            return DynamicFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                timeout=self.timeout,
            )

        return Fetcher.get(
            url,
            headers=self.headers,
            cookies=self.cookies,
            timeout=self.timeout,
        )
