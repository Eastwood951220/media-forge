from __future__ import annotations

from typing import Any

from backend.app.models.crawl_run import CrawlRunDetailTask


class DetailTaskIndex:
    def __init__(self) -> None:
        self.by_code: dict[str, CrawlRunDetailTask] = {}
        self.by_source_url: dict[str, CrawlRunDetailTask] = {}

    def remember(self, detail: CrawlRunDetailTask) -> None:
        if detail.code:
            self.by_code[str(detail.code)] = detail
        if detail.source_url:
            self.by_source_url[str(detail.source_url)] = detail

    def find(
        self,
        task_info: dict[str, Any],
        item_data: dict[str, Any] | None = None,
    ) -> CrawlRunDetailTask | None:
        item_data = item_data or {}
        code = item_data.get("code") or task_info.get("code")
        source_url = task_info.get("url") or task_info.get("source_url") or item_data.get("source_url")
        if code and code in self.by_code:
            return self.by_code[str(code)]
        if source_url and source_url in self.by_source_url:
            return self.by_source_url[str(source_url)]
        return None
