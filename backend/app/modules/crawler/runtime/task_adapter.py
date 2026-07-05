from __future__ import annotations

from backend.app.models.crawl_task import CrawlTask as BackendCrawlTask
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def to_scraper_task(task: BackendCrawlTask) -> CrawlTask:
    urls = [
        CrawlTaskUrlEntry(
            url=url.url,
            url_type=url.url_type,
            has_magnet=bool(url.has_magnet),
            has_chinese_sub=bool(url.has_chinese_sub),
            sort_type=int(url.sort_type or 0),
            source=url.source,
            final_url=url.final_url,
            url_name=url.url_name,
        )
        for url in sorted(task.urls, key=lambda item: item.position)
    ]
    return CrawlTask(
        name=task.name,
        urls=urls,
        is_skip=bool(task.is_skip),
        filter=getattr(task, "filter", None),
    )
