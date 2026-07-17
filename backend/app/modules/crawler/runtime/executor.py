from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.details import has_detail_phase_started
from backend.app.modules.crawler.runtime.events import append_run_log_for_run
from backend.app.modules.crawler.runtime.finalize import finalize_run
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.threaded import execute_threaded_crawl


def selected_task_url_ids_from_run(run: CrawlRun) -> list[uuid.UUID] | None:
    result = run.result or {}
    if not result.get("url_subset"):
        return None
    raw_ids = result.get("selected_task_url_ids") or []
    return [uuid.UUID(str(raw_id)) for raw_id in raw_ids]


def execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None:
    """Execute a crawler run."""
    if run.crawl_mode == "magnet_refresh":
        from backend.app.modules.content.movies.magnet_refresh import execute_magnet_refresh_run
        result = execute_magnet_refresh_run(db, run, runtime)
        stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
        finalize_run(db, run, runtime, result, stopped=stopped)
        return

    task = db.get(CrawlTask, run.task_id) if run.task_id else None
    if task is None:
        raise ValueError("关联任务不存在")

    task_urls = [{"url": u.url, "url_type": u.url_type} for u in task.urls]
    if not task_urls:
        raise ValueError("任务没有URL")

    try:
        detail_phase_restart = has_detail_phase_started(db, run)
        detail_retry_requested = bool((run.result or {}).get("detail_retry"))
        pending_detail_retry_rows = (
            db.query(CrawlRunDetailTask)
            .filter(
                CrawlRunDetailTask.run_id == run.id,
                CrawlRunDetailTask.status == "pending_crawl",
            )
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        temporary_run = run.crawl_mode == "temporary" or bool((run.result or {}).get("temporary"))
        detail_only = temporary_run or bool(pending_detail_retry_rows and (detail_phase_restart or detail_retry_requested))
        if temporary_run:
            append_run_log_for_run(db, run, f"临时任务详情子任务 {len(pending_detail_retry_rows)} 条，跳过列表收集直接处理详情", "INFO")
        elif detail_only:
            append_run_log_for_run(
                db,
                run,
                f"检测到待重试详情子任务 {len(pending_detail_retry_rows)} 条，跳过列表收集直接重试详情",
                "INFO",
            )

        result = execute_threaded_crawl(
            db,
            run,
            task,
            runtime,
            detail_only=detail_only,
            selected_task_url_ids=selected_task_url_ids_from_run(run),
        )

        stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
        finalize_run(db, run, runtime, result, stopped=stopped)
    except Exception:
        raise
