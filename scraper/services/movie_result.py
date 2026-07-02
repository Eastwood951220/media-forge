from scraper.spiders.javdb.javdb_constants import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_SKIPPED,
)
from scraper.tasks.task_schema import CrawlTask


def first_url_metadata(task: CrawlTask) -> dict:
    first_url = task.urls[0] if task.urls else None
    return {
        "source": first_url.source if first_url else None,
        "url": first_url.url if first_url else None,
        "final_url": first_url.final_url if first_url else None,
    }


def build_skipped_task_result(task: CrawlTask) -> dict:
    return {
        "task_name": task.name,
        **first_url_metadata(task),
        "is_skip": True,
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "skipped_tasks": 0,
        "saved": 0,
        "items": [],
        "reason": "skipped_by_config",
    }


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


def build_task_result(
    task: CrawlTask,
    detail_tasks: list[dict],
    items: list[dict],
    stopped: bool,
) -> dict:
    return {
        "task_name": task.name,
        **first_url_metadata(task),
        "is_skip": task.is_skip,
        **summarize_detail_tasks(detail_tasks),
        "saved": 0,
        "items": items,
        "stopped": stopped,
    }
