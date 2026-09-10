from __future__ import annotations

from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest
from scraper.spiders.javdb.javdb_spider import JavdbSpider


class JavdbMagnetProvider:
    source = "javdb"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch_detail_with_magnets(self, request: MovieDetailRequest, **kwargs) -> MovieDetailPayload:
        spider = JavdbSpider(fetcher=self.fetcher)
        task = {
            "url": request.url,
            "name": request.name or request.code or request.url,
            "code": request.code,
            "_task_url": request.task_url,
            "_task_final_url": request.task_final_url,
            "_task_url_type": request.task_url_type,
            "_task_url_name": request.task_url_name,
            "_task_source": request.source,
        }
        result = spider.run_single_detail_task(task, **kwargs)
        return MovieDetailPayload.from_spider_result(result, default_reason="javdb detail fetch failed")
