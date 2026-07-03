from scraper.spiders.javdb.javdb_constants import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_SKIPPED,
)
from scraper.tasks.task_schema import CrawlTask, CrawlTaskUrlEntry


def summarize_detail_tasks(detail_tasks: list[dict]) -> dict:
    return {
        "total_tasks": len(detail_tasks),
        "completed_tasks": sum(
            1 for item in detail_tasks if item.get("status") == TASK_STATUS_COMPLETED
        ),
        "failed_tasks": sum(
            1 for item in detail_tasks if item.get("status") == TASK_STATUS_FAILED
        ),
        "skipped_tasks": sum(
            1 for item in detail_tasks if item.get("status") == TASK_STATUS_SKIPPED
        ),
    }


def _matching_url_tasks(entry: CrawlTaskUrlEntry, detail_tasks: list[dict]) -> list[dict]:
    final_url = entry.final_url or entry.url
    return [
        item
        for item in detail_tasks
        if item.get("_task_url") == entry.url
        and item.get("_task_final_url") == final_url
    ]


def _url_result_item(entry: CrawlTaskUrlEntry, detail_tasks: list[dict]) -> dict:
    matching_tasks = _matching_url_tasks(entry, detail_tasks)
    summary = summarize_detail_tasks(matching_tasks)
    return {
        "url": entry.url,
        "final_url": entry.final_url or entry.url,
        "url_type": entry.url_type,
        "source": entry.source,
        "url_name": entry.url_name,
        "has_magnet": entry.has_magnet,
        "has_chinese_sub": entry.has_chinese_sub,
        "sort_type": entry.sort_type,
        **summary,
    }


def url_result_items(task: CrawlTask, detail_tasks: list[dict]) -> list[dict]:
    return [_url_result_item(entry, detail_tasks) for entry in task.urls]


def build_skipped_task_result(task: CrawlTask) -> dict:
    return {
        "task_name": task.name,
        "is_skip": True,
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "skipped_tasks": 0,
        "saved": 0,
        "items": url_result_items(task, []),
        "reason": "skipped_by_config",
    }


def build_task_result(
    task: CrawlTask,
    detail_tasks: list[dict],
    saved_items: list[dict],
    stopped: bool,
) -> dict:
    return {
        "task_name": task.name,
        "is_skip": task.is_skip,
        **summarize_detail_tasks(detail_tasks),
        "saved": 0,
        "items": url_result_items(task, detail_tasks),
        "stopped": stopped,
    }
