from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.details import has_detail_phase_started
from backend.app.modules.crawler.runtime.events import append_run_log_for_run
from backend.app.modules.crawler.runtime.finalize import finalize_run
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.threaded import execute_threaded_crawl


def execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None:
    """Execute a crawler run."""
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

        result = execute_threaded_crawl(db, run, task, runtime, detail_only=detail_only)

        stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
        finalize_run(db, run, runtime, result, stopped=stopped)
    except Exception:
        raise
