from __future__ import annotations

from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest


class JavbusMagnetProvider:
    source = "javbus"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch_detail_with_magnets(self, request: MovieDetailRequest, **kwargs) -> MovieDetailPayload:
        raise NotImplementedError("JavBus magnet provider adapter is added in a later task")
