from __future__ import annotations

import uuid

from backend.app.models.crawl_task import CrawlTask as BackendCrawlTask
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def _normalize_selected_ids(selected_url_ids: list[uuid.UUID] | None) -> set[uuid.UUID] | None:
    if selected_url_ids is None:
        return None
    return {uuid.UUID(str(url_id)) for url_id in selected_url_ids}


def to_scraper_task(
    task: BackendCrawlTask,
    selected_url_ids: list[uuid.UUID] | None = None,
) -> CrawlTask:
    selected_ids = _normalize_selected_ids(selected_url_ids)
    sorted_urls = sorted(task.urls, key=lambda item: item.position)
    if selected_ids is not None:
        sorted_urls = [url for url in sorted_urls if url.id in selected_ids]
        if not sorted_urls:
            raise ValueError("选择的 URL 不属于该任务")

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
        for url in sorted_urls
    ]
    return CrawlTask(
        name=task.name,
        urls=urls,
        is_skip=bool(task.is_skip),
        filter=getattr(task, "filter", None),
    )
