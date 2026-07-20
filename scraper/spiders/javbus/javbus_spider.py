import re
from typing import Any
from urllib.parse import urlencode

from scraper.config.logging import get_logger
from scraper.core.throttle import random_sleep
from scraper.spiders.base_spider import BaseSpider
from scraper.spiders.javbus import javbus_parser
from scraper.tasks.task_schema import CrawlTaskUrlEntry

TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_SKIPPED = "skipped"


def _is_detail_url(url: str) -> bool:
    return bool(re.search(r"/[A-Za-z]+-\d+", url))


class JavbusSpider(BaseSpider):
    name = "javbus"
    source = "javbus"

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
    def _task_prefix(task_name: str | None, url_label: str | None = None) -> str:
        prefix = f"[{task_name}]" if task_name else ""
        if url_label:
            prefix = f"{prefix}[URL: {url_label}]"
        return prefix

    @staticmethod
    def _detail_url_label(task: dict) -> str:
        return (
            str(task.get("_task_url_name") or "").strip()
            or str(task.get("_task_url_type") or "").strip()
            or str(task.get("_task_final_url") or task.get("_task_url") or "").strip()
        )

    def extract_url_name(self, url: str, url_type: str) -> str | None:
        try:
            page = self.fetch(url)
            result = javbus_parser.parse_detail_page(page, url)
            return result.get("source_name") or result.get("title") or None
        except Exception:
            return None

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
        on_item_already_exists=None,
    ) -> list[dict[str, Any]]:
        detail_tasks: list[dict[str, Any]] = []
        seen_codes: set[str] = set()

        url_label = self._url_label(url_entry)
        prefix = self._task_prefix(task_name, url_label)

        msg = f"{prefix} 增量阈值: {incremental_threshold}, 爬取模式: {crawl_mode}"
        self._emit(msg, log_callback, "INFO")

        current_url = url_entry.final_url or url_entry.url

        if _is_detail_url(current_url):
            msg = f"{prefix} 检测到详情页 URL, 创建单个详情任务"
            self._emit(msg, log_callback)
            code = javbus_parser._extract_code_from_url(current_url)
            task = {
                "url": current_url,
                "name": url_entry.url_name or code or current_url,
                "code": code,
                "_task_url": url_entry.url,
                "_task_final_url": url_entry.final_url or url_entry.url,
                "_task_url_type": url_entry.url_type,
                "_task_source": url_entry.source,
                "_task_url_name": url_entry.url_name,
                "_task_has_magnet": url_entry.has_magnet,
                "_task_has_chinese_sub": url_entry.has_chinese_sub,
                "_task_sort_type": url_entry.sort_type,
            }
            detail_tasks.append(task)
            if on_tasks_batch_created:
                on_tasks_batch_created([task])
            return detail_tasks

        page_no = 0
        while current_url:
            page_no += 1
            if stop_check and stop_check():
                msg = f"{prefix} 列表页 {page_no} 收到停止信号"
                self._emit(msg, log_callback, "WARNING")
                break

            msg = f"{prefix} 正在获取列表页 {page_no}: {current_url}"
            self._emit(msg, log_callback)

            try:
                page = self.fetch(current_url)
            except Exception as exc:
                msg = f"{prefix} 列表页 {page_no} 请求失败: {exc}"
                self._emit(msg, log_callback, "ERROR")
                break

            try:
                page_items, next_url = javbus_parser.parse_list_page(page, current_url)
            except Exception as exc:
                msg = f"{prefix} 列表页 {page_no} 解析失败: {exc}"
                self._emit(msg, log_callback, "ERROR")
                break

            if not page_items:
                msg = f"{prefix} 列表页 {page_no} 无数据, 停止收集"
                self._emit(msg, log_callback)
                break

            fresh_tasks: list[dict[str, Any]] = []
            for item in page_items:
                code = item.get("code")
                if code and code in seen_codes:
                    continue
                if code:
                    seen_codes.add(code)
                task = {
                    "url": item["url"],
                    "name": item.get("title") or code or item["url"],
                    "code": code or "",
                    "_task_url": url_entry.url,
                    "_task_final_url": url_entry.final_url or url_entry.url,
                    "_task_url_type": url_entry.url_type,
                    "_task_source": url_entry.source,
                    "_task_url_name": url_entry.url_name,
                    "_task_has_magnet": url_entry.has_magnet,
                    "_task_has_chinese_sub": url_entry.has_chinese_sub,
                    "_task_sort_type": url_entry.sort_type,
                }
                fresh_tasks.append(task)

            existing_count = 0
            if db_check_callback and fresh_tasks:
                codes_to_check = [t.get("code") for t in fresh_tasks if t.get("code")]
                if codes_to_check:
                    existing_codes = db_check_callback(codes_to_check)
                    if existing_codes:
                        crawlable_tasks: list[dict[str, Any]] = []
                        ignored_existing_tasks: list[dict[str, Any]] = []
                        kept_skipped_tasks: list[dict[str, Any]] = []
                        for t in fresh_tasks:
                            code = t.get("code")
                            if code and code in existing_codes:
                                t["status"] = TASK_STATUS_SKIPPED
                                t["reason"] = "already_exists"
                                existing_count += 1
                                if crawl_mode == "incremental":
                                    ignored_existing_tasks.append(t)
                                else:
                                    kept_skipped_tasks.append(t)
                                continue
                            crawlable_tasks.append(t)

                        if ignored_existing_tasks:
                            for task_info in ignored_existing_tasks:
                                if on_item_already_exists:
                                    on_item_already_exists(task_info)
                            msg = (
                                f"{prefix} 列表页 {page_no}: {len(ignored_existing_tasks)} 条已存在于数据库, "
                                "不创建子任务"
                            )
                            self._emit(msg, log_callback, "INFO")

                        fresh_tasks = [*kept_skipped_tasks, *crawlable_tasks]

                        if (
                            crawl_mode == "incremental"
                            and incremental_threshold > 0
                            and existing_count >= incremental_threshold
                        ):
                            msg = (
                                f"{prefix} 列表页 {page_no} 已存在 {existing_count} 条 "
                                f"(>= 阈值 {incremental_threshold}), 跳过后续页面"
                            )
                            self._emit(msg, log_callback, "INFO")
                            if fresh_tasks:
                                detail_tasks.extend(fresh_tasks)
                                if on_tasks_batch_created:
                                    on_tasks_batch_created(fresh_tasks)
                            break

            detail_tasks.extend(fresh_tasks)

            if on_tasks_batch_created and fresh_tasks:
                on_tasks_batch_created(fresh_tasks)

            msg = f"{prefix} 列表页 {page_no} 完成: 本页={len(fresh_tasks)}条, 总计={len(detail_tasks)}"
            self._emit(msg, log_callback)

            if next_url:
                current_url = next_url
                random_sleep(1, 3)
            else:
                msg = f"{prefix} 无下一页, 列表收集完成"
                self._emit(msg, log_callback)
                break

        msg = f"{prefix} URL 列表收集完成: 共 {len(detail_tasks)} 条任务"
        self._emit(msg, log_callback)

        return detail_tasks

    def run_single_detail_task(
        self,
        task: dict[str, Any],
        task_name: str | None = None,
        on_detail_completed=None,
        on_detail_failed=None,
        stop_check=None,
        log_callback=None,
        on_detail_check_callback=None,
        on_item_already_exists=None,
    ) -> dict[str, Any]:
        detail_prefix = self._task_prefix(task_name, self._detail_url_label(task))
        code = task.get("code")

        if code and on_detail_check_callback and on_detail_check_callback(code):
            task["status"] = TASK_STATUS_SKIPPED
            task["reason"] = "already_exists"
            msg = f"{detail_prefix} 跳过: code={code} 已存在于数据库"
            self._emit(msg, log_callback, "INFO")
            if on_item_already_exists:
                on_item_already_exists(task)
            return task

        url = task.get("url")
        if not url:
            task["status"] = TASK_STATUS_FAILED
            task["reason"] = "missing_url"
            msg = f"{detail_prefix} 失败: 缺少URL"
            self._emit(msg, log_callback, "ERROR")
            if on_detail_failed:
                on_detail_failed(task, "missing_url")
            return task

        task["status"] = TASK_STATUS_RUNNING
        msg = f"{detail_prefix} 处理中: {task.get('name')}"
        self._emit(msg, log_callback)

        try:
            page = self.fetch(url)
            detail = javbus_parser.parse_detail_page(page, url)

            ajax_params = javbus_parser.extract_ajax_params(page)
            gid = ajax_params.get("gid")
            uc = ajax_params.get("uc")
            img = ajax_params.get("img")

            if not gid or not uc or not img:
                missing = [k for k, v in {"gid": gid, "uc": uc, "img": img}.items() if not v]
                task["status"] = TASK_STATUS_FAILED
                task["reason"] = f"missing ajax params: {', '.join(missing)}"
                msg = f"{detail_prefix} 失败: 缺少 Ajax 参数: {', '.join(missing)}"
                self._emit(msg, log_callback, "ERROR")
                if on_detail_failed:
                    on_detail_failed(task, task["reason"])
                return task

            ajax_url = f"https://www.javbus.com/ajax/uncledatoolsbyajax.php?{urlencode({'gid': gid, 'lang': 'zh', 'img': img, 'uc': uc, 'floor': '735'})}"
            msg = f"{detail_prefix} 请求 Ajax 磁力链接"
            self._emit(msg, log_callback)

            try:
                ajax_page = self.fetch(ajax_url)
                magnets = javbus_parser.parse_magnet_ajax(ajax_page)
            except Exception as exc:
                task["status"] = TASK_STATUS_FAILED
                task["reason"] = f"ajax request failed: {exc}"
                msg = f"{detail_prefix} Ajax 请求失败: {exc}"
                self._emit(msg, log_callback, "ERROR")
                if on_detail_failed:
                    on_detail_failed(task, task["reason"])
                return task

            detail["magnets"] = magnets
            task["detail"] = detail
            task["status"] = TASK_STATUS_COMPLETED

            msg = f"{detail_prefix} 完成: {task.get('name')}, 磁力链接: {len(magnets)} 条"
            self._emit(msg, log_callback)

            if on_detail_completed:
                on_detail_completed(task)

        except Exception as exc:
            task["status"] = TASK_STATUS_FAILED
            task["reason"] = str(exc)
            msg = f"{detail_prefix} 失败: {task.get('name')} error={exc}"
            self._emit(msg, log_callback, "ERROR")
            if on_detail_failed:
                on_detail_failed(task, str(exc))

        return task
