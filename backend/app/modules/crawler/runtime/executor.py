from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runtime.callbacks import CrawlerCallbackContext, build_crawl_callbacks
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
from backend.app.modules.crawler.runtime.details import (
    detail_row_to_task_info,
    has_detail_phase_started,
)
from backend.app.modules.crawler.runtime.engine import get_crawler_engine
from backend.app.modules.crawler.runtime.events import append_run_log_for_run
from backend.app.modules.crawler.runtime.finalize import finalize_run
from backend.app.modules.crawler.runtime.progress import new_progress
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.task_adapter import to_scraper_task


def execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None:
    """Execute a crawler run."""
    task = db.get(CrawlTask, run.task_id) if run.task_id else None
    if task is None:
        raise ValueError("关联任务不存在")

    # Build task URLs
    task_urls = [{"url": u.url, "url_type": u.url_type} for u in task.urls]
    if not task_urls:
        raise ValueError("任务没有URL")

    # Preload existing detail tasks for in-place restart
    detail_index = DetailTaskIndex()
    progress = new_progress()
    for detail in db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all():
        detail_index.remember(detail)

    callback_context = CrawlerCallbackContext(
        db=db,
        run=run,
        task=task,
        runtime=runtime,
        detail_index=detail_index,
        progress=progress,
    )

    # Execute crawl
    try:
        engine_task = to_scraper_task(task)
        engine = get_crawler_engine()

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
        if pending_detail_retry_rows and (detail_phase_restart or detail_retry_requested):
            append_run_log_for_run(
                db,
                run,
                f"检测到待重试详情子任务 {len(pending_detail_retry_rows)} 条，跳过列表收集直接重试详情",
                "INFO",
            )
            result = engine.crawl_detail_tasks(
                engine_task,
                detail_tasks=[detail_row_to_task_info(detail) for detail in pending_detail_retry_rows],
                task_id=str(run.task_id) if run.task_id else None,
                callbacks=build_crawl_callbacks(callback_context, include_list_callbacks=False),
            )
        else:
            incremental_threshold = read_incremental_threshold_from_conf()
            result = engine.crawl_task(
                engine_task,
                task_id=str(run.task_id) if run.task_id else None,
                crawl_mode=run.crawl_mode,
                incremental_threshold=incremental_threshold,
                callbacks=build_crawl_callbacks(callback_context, include_list_callbacks=True),
            )

        stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
        finalize_run(db, run, runtime, result, stopped=stopped)
    except Exception:
        raise
