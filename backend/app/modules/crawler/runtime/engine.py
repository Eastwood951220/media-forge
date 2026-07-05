from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from backend.app.modules.crawler.runtime.results import build_skipped_task_result, build_task_result
from scraper.config.settings import REQUEST_TIMEOUT
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.pipelines.movie_pipeline import MoviePipeline
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTask


@dataclass
class CrawlCallbacks:
    stop_check: Callable[[], bool] | None = None
    log_callback: Callable[[str, str], None] | None = None
    on_item_saved: Callable[[dict[str, Any], dict[str, Any]], None] | None = None
    on_tasks_batch_created: Callable[[list[dict[str, Any]]], None] | None = None
    on_detail_failed: Callable[[dict[str, Any], str], None] | None = None
    db_check_callback: Callable[[list[str]], set[str]] | None = None
    on_detail_check_callback: Callable[[str], bool] | None = None
    on_item_already_exists: Callable[[dict[str, Any]], None] | None = None


class CrawlerEngine(Protocol):
    def crawl_task(
        self,
        task: CrawlTask,
        *,
        task_id: str | None,
        crawl_mode: str,
        incremental_threshold: int,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        ...

    def crawl_detail_tasks(
        self,
        task: CrawlTask,
        *,
        detail_tasks: list[dict[str, Any]],
        task_id: str | None,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        ...


class JavdbCrawlerEngine:
    def __init__(
        self,
        *,
        spider_factory: Callable[[], Any] | None = None,
        pipeline_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._spider_factory = spider_factory or self._build_spider
        self._pipeline_factory = pipeline_factory or MoviePipeline

    def _build_spider(self) -> JavdbSpider:
        cookie_manager = CookieManager(JAVDB_SITE["cookie_file"])
        cookies = cookie_manager.load()
        fetcher = ScraplingFetcher(
            headers=JAVDB_SITE["headers"],
            cookies=cookies,
            timeout=REQUEST_TIMEOUT,
        )
        return JavdbSpider(fetcher=fetcher)

    def crawl_task(
        self,
        task: CrawlTask,
        *,
        task_id: str | None,
        crawl_mode: str,
        incremental_threshold: int,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        if task.is_skip:
            if callbacks.log_callback:
                callbacks.log_callback(f"跳过任务: {task.name}", "INFO")
            return build_skipped_task_result(task)

        spider = self._spider_factory()
        pipeline = self._pipeline_factory()
        saved_items: list[dict[str, Any]] = []

        def collect_completed_detail(detail_task: dict[str, Any]) -> None:
            self._collect_completed_detail(
                task=task,
                task_id=task_id,
                detail_task=detail_task,
                pipeline=pipeline,
                saved_items=saved_items,
                callbacks=callbacks,
            )

        detail_tasks = spider.run_task(
            task,
            crawl_mode=crawl_mode,
            incremental_threshold=incremental_threshold,
            on_detail_completed=collect_completed_detail,
            on_tasks_batch_created=callbacks.on_tasks_batch_created,
            on_detail_failed=callbacks.on_detail_failed,
            stop_check=callbacks.stop_check,
            log_callback=callbacks.log_callback,
            db_check_callback=callbacks.db_check_callback,
            on_detail_check_callback=callbacks.on_detail_check_callback,
            on_item_already_exists=callbacks.on_item_already_exists,
        )
        stopped = callbacks.stop_check() if callbacks.stop_check else False
        return build_task_result(task=task, detail_tasks=detail_tasks, saved_items=saved_items, stopped=stopped)

    def crawl_detail_tasks(
        self,
        task: CrawlTask,
        *,
        detail_tasks: list[dict[str, Any]],
        task_id: str | None,
        callbacks: CrawlCallbacks,
    ) -> dict[str, Any]:
        if task.is_skip:
            if callbacks.log_callback:
                callbacks.log_callback(f"跳过任务: {task.name}", "INFO")
            return build_skipped_task_result(task)

        spider = self._spider_factory()
        pipeline = self._pipeline_factory()
        saved_items: list[dict[str, Any]] = []

        def collect_completed_detail(detail_task: dict[str, Any]) -> None:
            self._collect_completed_detail(
                task=task,
                task_id=task_id,
                detail_task=detail_task,
                pipeline=pipeline,
                saved_items=saved_items,
                callbacks=callbacks,
            )

        processed_tasks = spider.run_detail_tasks(
            detail_tasks,
            task_name=task.name,
            on_detail_completed=collect_completed_detail,
            on_detail_failed=callbacks.on_detail_failed,
            stop_check=callbacks.stop_check,
            log_callback=callbacks.log_callback,
            on_detail_check_callback=callbacks.on_detail_check_callback,
            on_item_already_exists=callbacks.on_item_already_exists,
        )
        stopped = callbacks.stop_check() if callbacks.stop_check else False
        return build_task_result(task=task, detail_tasks=processed_tasks, saved_items=saved_items, stopped=stopped)

    def _collect_completed_detail(
        self,
        *,
        task: CrawlTask,
        task_id: str | None,
        detail_task: dict[str, Any],
        pipeline: Any,
        saved_items: list[dict[str, Any]],
        callbacks: CrawlCallbacks,
    ) -> None:
        item = self._build_detail_item(detail_task)
        if not item:
            return

        cleaned = pipeline.process_item(item, task_name=task.name, task_id=task_id)
        if cleaned is not None:
            saved_items.append(cleaned)
            message = f"[{task.name}] 详情完成: code={cleaned.get('code')} source_task_name={cleaned.get('source_task_name')}"
            if callbacks.log_callback:
                callbacks.log_callback(message, "INFO")
            if callbacks.on_item_saved:
                callbacks.on_item_saved(detail_task, cleaned)
            return

        message = f"[{task.name}] 跳过无效数据: code={item.get('code')}"
        if callbacks.log_callback:
            callbacks.log_callback(message, "WARNING")

    def _build_detail_item(self, detail_task: dict[str, Any]) -> dict[str, Any]:
        detail = detail_task.get("detail") or {}
        if not detail:
            return {}
        source_code = detail_task.get("code")
        return {
            **detail,
            "code": detail.get("code") or source_code,
            "source_url": detail_task.get("url"),
            "source_name": detail_task.get("name") or detail.get("source_name"),
            "source_code": source_code,
        }


def get_crawler_engine() -> CrawlerEngine:
    return JavdbCrawlerEngine()
