from collections.abc import Callable
from typing import Any, Protocol

from scraper.tasks.task_schema import CrawlTaskUrlEntry


class SiteSpiderProtocol(Protocol):
    source: str

    def collect_detail_tasks_for_url(
        self,
        url_entry: CrawlTaskUrlEntry,
        task_name: str,
        crawl_mode: str = "incremental",
        incremental_threshold: int = 0,
        stop_check: Callable[[], bool] | None = None,
        log_callback: Callable[..., None] | None = None,
        on_tasks_batch_created: Callable[[list[dict[str, Any]]], None] | None = None,
        db_check_callback: Callable[[list[str]], set[str]] | None = None,
        on_item_already_exists: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]: ...

    def run_single_detail_task(
        self,
        task: dict[str, Any],
        task_name: str | None = None,
        on_detail_completed: Callable[[dict[str, Any]], None] | None = None,
        on_detail_failed: Callable[[dict[str, Any], str], None] | None = None,
        stop_check: Callable[[], bool] | None = None,
        log_callback: Callable[..., None] | None = None,
        on_detail_check_callback: Callable[[str], bool] | None = None,
        on_item_already_exists: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]: ...

    def extract_url_name(self, url: str, url_type: str) -> str | None: ...
