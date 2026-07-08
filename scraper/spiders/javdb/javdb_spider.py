from scraper.config.logging import get_logger
from scraper.config.settings import (
    DETAIL_PAGE_DELAY_MAX,
    DETAIL_PAGE_DELAY_MIN,
    LIST_PAGE_DELAY_MAX,
    LIST_PAGE_DELAY_MIN,
    MAX_LIST_PAGES,
    SECURITY_WAIT_SECONDS,
)
from scraper.core.security import is_security_check_page
from scraper.core.throttle import fixed_sleep, random_sleep
from scraper.spiders.base_spider import BaseSpider
from scraper.spiders.javdb.javdb_constants import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SKIPPED,
)
from scraper.spiders.javdb.javdb_parser import parse_detail_page, parse_search_page
from scraper.spiders.javdb.javdb_urls import build_task_page_url
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


class JavdbSpider(BaseSpider):
    name = "javdb"

    def __init__(self, fetcher):
        super().__init__(fetcher)
        self.logger = get_logger(self.name)

    @staticmethod
    def _emit(message: str, log_callback=None, level: str = "INFO") -> None:
        print(message)
        if log_callback:
            log_callback(message, level)

    @staticmethod
    def _url_label(url_entry: CrawlTaskUrlEntry) -> str:
        return (
            (url_entry.url_name or "").strip()
            or (url_entry.url_type or "").strip()
            or (url_entry.final_url or url_entry.url or "").strip()
            or "-"
        )

    @staticmethod
    def _detail_url_label(task: dict) -> str:
        return (
            str(task.get("_task_url_name") or "").strip()
            or str(task.get("_task_url_type") or "").strip()
            or str(task.get("_task_final_url") or task.get("_task_url") or "").strip()
        )

    @staticmethod
    def _task_prefix(task_name: str | None, url_label: str | None = None) -> str:
        prefix = f"[{task_name}]" if task_name else ""
        if url_label:
            prefix = f"{prefix}[URL: {url_label}]"
        return prefix

    def collect_detail_tasks_for_url(
        self,
        url_entry: CrawlTaskUrlEntry,
        task_name: str,
        crawl_mode: str = "incremental",
        incremental_threshold: int = 0,
        stop_check=None,
        log_callback=None,
        on_tasks_batch_created=None,
        db_check_callback=None,
    ) -> list[dict]:
        """Collect detail tasks from list pages for a single URL entry."""
        max_pages = MAX_LIST_PAGES
        detail_tasks: list[dict] = []
        seen_codes: set[str] = set()
        verification_count = 0

        url_label = self._url_label(url_entry)
        prefix = self._task_prefix(task_name, url_label)

        msg = f"{prefix} 增量阈值: {incremental_threshold}, 爬取模式: {crawl_mode}"
        self._emit(msg, log_callback, "INFO")

        final_url = url_entry.final_url or url_entry.url
        msg = f"{prefix} 开始收集列表页 url={final_url}, 最大页数={max_pages}"
        self._emit(msg, log_callback)

        page_no = 1

        while page_no <= max_pages:
            if stop_check and stop_check():
                msg = f"{prefix} 列表页 {page_no} 收到停止信号"
                self._emit(msg, log_callback, "WARNING")
                break
            page_url = build_task_page_url(final_url, page_no)
            msg = f"{prefix} 正在获取列表页 {page_no}/{max_pages}"
            self._emit(msg, log_callback)
            self.logger.info("List page: %s", page_url)

            page = self.fetch(page_url)

            if is_security_check_page(page):
                verification_count += 1
                msg = (
                    f"{prefix} 列表页 {page_no} 触发安全验证, "
                    f"等待 {SECURITY_WAIT_SECONDS}s 后重试"
                )
                self._emit(msg, log_callback, "WARNING")
                if verification_count >= 5:
                    msg = (
                        f"{prefix} 连续验证次数={verification_count}, "
                        "请手动刷新 cookies 或完成浏览器验证"
                    )
                    self._emit(msg, log_callback, "ERROR")
                fixed_sleep(SECURITY_WAIT_SECONDS, reason="列表页触发人工验证")
                continue

            verification_count = 0
            page_tasks = parse_search_page(
                page=page,
                source_page=page_no,
            )

            if not page_tasks:
                msg = f"{prefix} 列表页 {page_no} 无数据, 停止收集"
                self._emit(msg, log_callback)
                break

            # Dedup: filter out codes already seen in this URL
            fresh_tasks: list[dict] = []
            for t in page_tasks:
                code = t.get("code")
                if code and code in seen_codes:
                    continue
                if code:
                    seen_codes.add(code)
                t["_task_url"] = url_entry.url
                t["_task_final_url"] = url_entry.final_url or url_entry.url
                t["_task_url_type"] = url_entry.url_type
                t["_task_source"] = url_entry.source
                t["_task_url_name"] = url_entry.url_name
                t["_task_has_magnet"] = url_entry.has_magnet
                t["_task_has_chinese_sub"] = url_entry.has_chinese_sub
                t["_task_sort_type"] = url_entry.sort_type
                fresh_tasks.append(t)

            # DB dedup: check which codes already exist in movies collection
            if db_check_callback and fresh_tasks:
                codes_to_check = [t.get("code") for t in fresh_tasks if t.get("code")]
                if codes_to_check:
                    existing_codes = db_check_callback(codes_to_check)
                    db_skipped = 0
                    for t in fresh_tasks:
                        code = t.get("code")
                        if code and code in existing_codes:
                            t["status"] = TASK_STATUS_SKIPPED
                            t["reason"] = "already_exists"
                            db_skipped += 1
                    if db_skipped:
                        msg = f"{prefix} 列表页 {page_no}: {db_skipped} 条已存在于数据库, 跳过"
                        self._emit(msg, log_callback, "INFO")

                        # 增量爬取: 如果本页已存在的条目数 >= 阈值，跳过后续页面
                        if (crawl_mode == "incremental"
                            and incremental_threshold > 0
                            and db_skipped >= incremental_threshold):
                            msg = (
                                f"{prefix} 列表页 {page_no} 已存在 {db_skipped} 条 "
                                f"(>= 阈值 {incremental_threshold}), 跳过后续页面"
                            )
                            self._emit(msg, log_callback, "INFO")
                            non_skipped_tasks = [
                                item for item in fresh_tasks
                                if item.get("status") != TASK_STATUS_SKIPPED
                            ]
                            if non_skipped_tasks:
                                detail_tasks.extend(non_skipped_tasks)
                                if on_tasks_batch_created:
                                    on_tasks_batch_created(non_skipped_tasks)
                            msg = (
                                f"{prefix} 当前 URL 达到增量阈值，"
                                "停止该 URL 后续列表页，继续下一个 URL"
                            )
                            self._emit(msg, log_callback, "INFO")
                            break

            detail_tasks.extend(fresh_tasks)

            if on_tasks_batch_created and fresh_tasks:
                on_tasks_batch_created(fresh_tasks)

            total_count = len(detail_tasks)
            skipped_count = sum(
                1 for t in detail_tasks if t.get("status") == TASK_STATUS_SKIPPED
            )
            pending_count = total_count - skipped_count

            msg = (
                f"{prefix} 列表页 {page_no} 完成: 本页={len(fresh_tasks)}条(去重后), "
                f"总计={total_count}, 待处理={pending_count}, 跳过={skipped_count}"
            )
            self._emit(msg, log_callback)

            if page_no < max_pages:
                random_sleep(LIST_PAGE_DELAY_MIN, LIST_PAGE_DELAY_MAX)

            page_no += 1

        msg = f"{prefix} URL 列表收集完成: 共 {len(detail_tasks)} 条任务"
        self._emit(msg, log_callback)

        return detail_tasks

    def collect_all_detail_tasks(
        self,
        task: CrawlTask,
        crawl_mode: str = "incremental",
        incremental_threshold: int = 0,
        stop_check=None,
        log_callback=None,
        on_tasks_batch_created=None,
        db_check_callback=None,
    ) -> list[dict]:
        """Collect detail tasks from ALL URLs in a task sequentially."""
        all_detail_tasks: list[dict] = []
        seen_codes: set[str] = set()

        for i, url_entry in enumerate(task.urls, 1):
            if stop_check and stop_check():
                msg = f"[{task.name}] URL {i}/{len(task.urls)} 收到停止信号"
                self._emit(msg, log_callback, "WARNING")
                break

            url_label = self._url_label(url_entry)
            msg = f"[{task.name}][URL: {url_label}] 处理 URL {i}/{len(task.urls)}: {url_entry.url_type}"
            self._emit(msg, log_callback)

            url_tasks = self.collect_detail_tasks_for_url(
                url_entry=url_entry,
                task_name=task.name,
                crawl_mode=crawl_mode,
                incremental_threshold=incremental_threshold,
                stop_check=stop_check,
                log_callback=log_callback,
                on_tasks_batch_created=on_tasks_batch_created,
                db_check_callback=db_check_callback,
            )

            # Dedup within this run: skip codes already seen
            for t in url_tasks:
                code = t.get("code")
                if code and code in seen_codes:
                    continue
                if code:
                    seen_codes.add(code)
                all_detail_tasks.append(t)

        msg = f"[{task.name}] 所有 URL 列表收集完成: 共 {len(all_detail_tasks)} 条唯一任务"
        self._emit(msg, log_callback)

        return all_detail_tasks

    def run_detail_tasks(
        self,
        tasks: list[dict],
        task_name: str | None = None,
        on_detail_completed=None,
        on_detail_failed=None,
        stop_check=None,
        log_callback=None,
        on_detail_check_callback=None,
        on_item_already_exists=None,
    ) -> list[dict]:
        total = len(tasks)
        verification_count = 0
        prefix = f"[{task_name}]" if task_name else ""

        msg = f"{prefix} 开始处理详情页: 共 {total} 条"
        self._emit(msg, log_callback)

        index = 0

        while index < total:
            if stop_check and stop_check():
                msg = f"{prefix} 详情页 {index + 1}/{total} 收到停止信号"
                self._emit(msg, log_callback, "WARNING")
                break
            task = tasks[index]

            detail_prefix = self._task_prefix(task_name, self._detail_url_label(task))

            completed_count = sum(
                1 for item in tasks if item.get("status") == TASK_STATUS_COMPLETED
            )
            failed_count = sum(
                1 for item in tasks if item.get("status") == TASK_STATUS_FAILED
            )
            skipped_count = sum(
                1 for item in tasks if item.get("status") == TASK_STATUS_SKIPPED
            )

            if task.get("status") == TASK_STATUS_SKIPPED:
                msg = (
                    f"{detail_prefix} 详情 {index + 1}/{total} 跳过: "
                    f"name={task.get('name')} reason={task.get('reason')}"
                )
                self._emit(msg, log_callback)
                # LIST 阶段跳过的已存在电影，也需要更新 source_task_name
                if task.get("reason") == "already_exists" and on_item_already_exists:
                    on_item_already_exists(task)
                index += 1
                continue

            # Pre-fetch DB check: skip if code already exists
            code = task.get("code")
            if code and on_detail_check_callback and on_detail_check_callback(code):
                task["status"] = TASK_STATUS_SKIPPED
                task["reason"] = "already_exists"
                msg = (
                    f"{detail_prefix} 详情 {index + 1}/{total} 跳过: "
                    f"code={code} 已存在于数据库"
                )
                self._emit(msg, log_callback, "INFO")
                # 通知已存在，用于更新 source_task_name
                if on_item_already_exists:
                    on_item_already_exists(task)
                index += 1
                continue

            url = task.get("url")

            if not url:
                task["status"] = TASK_STATUS_FAILED
                task["reason"] = "missing_url"
                msg = f"{detail_prefix} 详情 {index + 1}/{total} 失败: 缺少URL"
                self._emit(msg, log_callback, "ERROR")
                index += 1
                continue

            msg = (
                f"{detail_prefix} 详情 {index + 1}/{total} 处理中: "
                f"已完成={completed_count} 失败={failed_count} 跳过={skipped_count} "
                f"name={task.get('name')}"
            )
            self._emit(msg, log_callback)
            self.logger.info("Detail page: %s", url)

            task["status"] = TASK_STATUS_RUNNING

            try:
                page = self.fetch(url)

                if is_security_check_page(page):
                    verification_count += 1
                    task["status"] = TASK_STATUS_PENDING
                    msg = (
                        f"{detail_prefix} 详情 {index + 1}/{total} 触发安全验证, "
                        f"等待 {SECURITY_WAIT_SECONDS}s 后重试"
                    )
                    self._emit(msg, log_callback, "WARNING")
                    if verification_count >= 5:
                        msg = (
                            f"{detail_prefix} 连续验证次数={verification_count}, "
                            "请手动刷新 cookies 或完成浏览器验证"
                        )
                        self._emit(msg, log_callback, "ERROR")
                    fixed_sleep(SECURITY_WAIT_SECONDS, reason="详情页触发人工验证")
                    continue

                verification_count = 0
                detail = parse_detail_page(page)

                task["detail"] = detail
                task["status"] = TASK_STATUS_COMPLETED

                msg = f"{detail_prefix} 详情 {index + 1}/{total} 完成: {task.get('name')}"
                self._emit(msg, log_callback)

                if on_detail_completed:
                    on_detail_completed(task)

                index += 1

                if index < total:
                    random_sleep(DETAIL_PAGE_DELAY_MIN, DETAIL_PAGE_DELAY_MAX)

            except Exception as exc:
                verification_count = 0
                task["status"] = TASK_STATUS_FAILED
                task["reason"] = str(exc)

                if on_detail_failed:
                    on_detail_failed(task, str(exc))

                msg = f"{detail_prefix} 详情 {index + 1}/{total} 失败: {task.get('name')} error={exc}"
                self._emit(msg, log_callback, "ERROR")

                index += 1

                if index < total:
                    random_sleep(DETAIL_PAGE_DELAY_MIN, DETAIL_PAGE_DELAY_MAX)

        completed_count = sum(1 for item in tasks if item.get("status") == TASK_STATUS_COMPLETED)
        failed_count = sum(1 for item in tasks if item.get("status") == TASK_STATUS_FAILED)
        skipped_count = sum(1 for item in tasks if item.get("status") == TASK_STATUS_SKIPPED)

        msg = (
            f"{prefix} 详情处理完成: 总计={total} "
            f"已完成={completed_count} 失败={failed_count} 跳过={skipped_count}"
        )
        self._emit(msg, log_callback)

        return tasks

    def run_task(self, task: CrawlTask, crawl_mode: str = "incremental", incremental_threshold: int = 0, on_detail_completed=None, on_detail_failed=None, on_tasks_batch_created=None, stop_check=None, log_callback=None, db_check_callback=None, on_detail_check_callback=None, on_item_already_exists=None) -> list[dict]:
        if task.is_skip:
            print(f"[Task:{task.name}] skipped by config")
            return []

        if not task.urls:
            print(f"[Task:{task.name}] skipped: no URLs configured")
            return []

        # Phase 1: Collect all detail tasks from all URLs
        detail_tasks = self.collect_all_detail_tasks(
            task,
            crawl_mode=crawl_mode,
            incremental_threshold=incremental_threshold,
            stop_check=stop_check,
            log_callback=log_callback,
            on_tasks_batch_created=on_tasks_batch_created,
            db_check_callback=db_check_callback,
        )

        # Phase 2: Process all detail tasks
        return self.run_detail_tasks(
            detail_tasks,
            task_name=task.name,
            on_detail_completed=on_detail_completed,
            on_detail_failed=on_detail_failed,
            stop_check=stop_check,
            log_callback=log_callback,
            on_detail_check_callback=on_detail_check_callback,
            on_item_already_exists=on_item_already_exists,
        )

    def run(self, task: CrawlTask) -> list[dict]:
        return self.run_task(task)
