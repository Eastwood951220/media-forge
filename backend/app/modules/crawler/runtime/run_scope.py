from __future__ import annotations

import uuid
from typing import Any

from backend.app.models.crawl_task import CrawlTask

TASK_FULL_SCOPE = "task_full"
TASK_URL_SUBSET_SCOPE = "task_url_subset"
TEMPORARY_DETAIL_SCOPE = "temporary_detail"

TASK_FULL_LABEL = "全部任务"
TEMPORARY_DETAIL_LABEL = "临时任务"
URL_SUBSET_FALLBACK_LABEL = "URL 爬取"

RUN_SCOPE_RESULT_KEYS = {
    "scope",
    "run_scope_label",
    "url_subset",
    "selected_task_url_ids",
    "selected_task_url_count",
    "selected_task_urls",
    "temporary",
    "detail_url_count",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _task_url_record(url: Any) -> dict[str, str | None]:
    return {
        "id": str(url.id),
        "url": _text(url.url),
        "url_type": _text(url.url_type) or None,
        "url_name": _text(url.url_name) or None,
    }


def _selected_task_urls(task: CrawlTask, selected_task_url_ids: list[uuid.UUID]) -> list[dict[str, str | None]]:
    urls_by_id = {url.id: url for url in task.urls}
    return [
        _task_url_record(urls_by_id[url_id])
        for url_id in selected_task_url_ids
        if url_id in urls_by_id
    ]


def _url_subset_label(selected_urls: list[dict[str, str | None]]) -> str:
    parts = [
        _text(url.get("url_name")) or _text(url.get("url_type")) or _text(url.get("url"))
        for url in selected_urls
    ]
    return ", ".join(part for part in parts if part) or URL_SUBSET_FALLBACK_LABEL


def full_task_result() -> dict[str, Any]:
    return {
        "scope": TASK_FULL_SCOPE,
        "run_scope_label": TASK_FULL_LABEL,
    }


def url_subset_result(task: CrawlTask, selected_task_url_ids: list[uuid.UUID]) -> dict[str, Any]:
    selected_ids = [str(url_id) for url_id in selected_task_url_ids]
    selected_urls = _selected_task_urls(task, selected_task_url_ids)
    return {
        "scope": TASK_URL_SUBSET_SCOPE,
        "run_scope_label": _url_subset_label(selected_urls),
        "url_subset": True,
        "selected_task_url_ids": selected_ids,
        "selected_task_url_count": len(selected_ids),
        "selected_task_urls": selected_urls,
    }


def temporary_detail_result(detail_url_count: int) -> dict[str, Any]:
    return {
        "scope": TEMPORARY_DETAIL_SCOPE,
        "run_scope_label": TEMPORARY_DETAIL_LABEL,
        "temporary": True,
        "detail_url_count": detail_url_count,
    }


def preserved_run_scope_result(result: dict[str, Any] | None) -> dict[str, Any]:
    source = result if isinstance(result, dict) else {}
    return {key: source[key] for key in RUN_SCOPE_RESULT_KEYS if key in source}


def merge_preserved_run_scope(
    existing_result: dict[str, Any] | None,
    next_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **preserved_run_scope_result(existing_result),
        **(next_result or {}),
    }


def run_scope_display(crawl_mode: str, result: dict[str, Any] | None) -> dict[str, str]:
    data = result if isinstance(result, dict) else {}
    scope = _text(data.get("scope"))
    if scope == TASK_URL_SUBSET_SCOPE or data.get("url_subset"):
        selected_urls = data.get("selected_task_urls") if isinstance(data.get("selected_task_urls"), list) else []
        return {
            "run_scope": TASK_URL_SUBSET_SCOPE,
            "run_scope_label": _text(data.get("run_scope_label")) or _url_subset_label(selected_urls),
        }
    if scope == TEMPORARY_DETAIL_SCOPE or crawl_mode == "temporary" or data.get("temporary"):
        return {
            "run_scope": TEMPORARY_DETAIL_SCOPE,
            "run_scope_label": _text(data.get("run_scope_label")) or TEMPORARY_DETAIL_LABEL,
        }
    return {
        "run_scope": TASK_FULL_SCOPE,
        "run_scope_label": _text(data.get("run_scope_label")) or TASK_FULL_LABEL,
    }
