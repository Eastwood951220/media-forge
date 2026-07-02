from scraper.config.settings import REQUEST_TIMEOUT
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.pipelines.movie_pipeline import MoviePipeline
from scraper.services.movie_result import build_skipped_task_result, build_task_result
from scraper.spiders.javdb.javdb_spider import JavdbSpider
from scraper.tasks.task_schema import CrawlTask


class MovieService:
    def _build_spider(self) -> JavdbSpider:
        cookie_manager = CookieManager(JAVDB_SITE["cookie_file"])
        cookies = cookie_manager.load()

        fetcher = ScraplingFetcher(
            headers=JAVDB_SITE["headers"],
            cookies=cookies,
            timeout=REQUEST_TIMEOUT,
        )

        return JavdbSpider(fetcher=fetcher)

    def crawl_javdb_task(self, task: CrawlTask, crawl_mode: str = "incremental", incremental_threshold: int = 0, stop_check=None, log_callback=None, on_item_saved=None, on_tasks_batch_created=None, on_detail_failed=None, db_check_callback=None, on_detail_check_callback=None, on_item_already_exists=None) -> dict:
        if task.is_skip:
            if log_callback:
                log_callback(f"跳过任务: {task.name}", "INFO")
            return build_skipped_task_result(task)

        spider = self._build_spider()
        pipeline = MoviePipeline()
        collected_items: list[dict] = []

        def collect_completed_detail(detail_task: dict) -> None:
            item = self._build_detail_item(task, detail_task)
            if not item:
                return

            cleaned = pipeline.process_item(item, task_name=task.name)
            if cleaned is not None:
                collected_items.append(cleaned)
                msg = (
                    f"[{task.name}] 详情完成: code={cleaned.get('code')} "
                    f"source_task_name={cleaned.get('source_task_name')}"
                )
                print(msg)
                if log_callback:
                    log_callback(msg, "INFO")
                # Per-item save callback
                if on_item_saved:
                    on_item_saved(detail_task, cleaned)
            else:
                msg = f"[{task.name}] 跳过无效数据: code={item.get('code')}"
                print(msg)
                if log_callback:
                    log_callback(msg, "WARNING")

        detail_tasks = spider.run_task(
            task,
            crawl_mode=crawl_mode,
            incremental_threshold=incremental_threshold,
            on_detail_completed=collect_completed_detail,
            on_tasks_batch_created=on_tasks_batch_created,
            on_detail_failed=on_detail_failed,
            stop_check=stop_check,
            log_callback=log_callback,
            db_check_callback=db_check_callback,
            on_detail_check_callback=on_detail_check_callback,
            on_item_already_exists=on_item_already_exists,
        )

        stopped = stop_check() if stop_check else False
        return build_task_result(
            task=task,
            detail_tasks=detail_tasks,
            items=collected_items,
            stopped=stopped,
        )

    def _build_detail_item(self, task: CrawlTask, detail_task: dict) -> dict:
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
