from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    sync_movie_filters,
    upsert_movie_with_magnets,
)
from backend.app.modules.crawler.runtime.config import read_incremental_threshold_from_conf
from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
from backend.app.modules.crawler.runtime.details import (
    RESTARTABLE_DETAIL_STATUSES,
    count_run_detail_tasks,
    detail_row_to_task_info,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)
from backend.app.modules.crawler.runtime.engine import CrawlCallbacks, get_crawler_engine
from backend.app.modules.crawler.runtime.events import (
    append_run_log_for_run,
    publish_run_detail_updated,
    publish_run_updated,
)
from backend.app.modules.crawler.runtime.progress import increment_progress, new_progress, write_progress
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.source_task_names import (
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.app.modules.crawler.runtime.task_adapter import to_scraper_task

logger = logging.getLogger(__name__)


def execute_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState) -> None:
    """Execute a crawler run."""
    task = db.get(CrawlTask, run.task_id) if run.task_id else None
    if task is None:
        raise ValueError("关联任务不存在")

    # Build task URLs
    task_urls = [{"url": u.url, "url_type": u.url_type} for u in task.urls]
    if not task_urls:
        raise ValueError("任务没有URL")

    # Track progress
    progress = new_progress()
    detail_index = DetailTaskIndex()

    def on_tasks_batch_created(items: list[dict[str, Any]]) -> None:
        skipped_count = 0
        created_details: list[CrawlRunDetailTask] = []
        for item in items:
            is_skipped = item.get("status") == "skipped"
            reason = item.get("reason") if is_skipped else None
            detail = detail_index.find(item)
            if detail is None:
                detail = CrawlRunDetailTask(
                    run_id=run.id,
                    task_name=task.name,
                    code=item.get("code"),
                    source_url=item.get("url", ""),
                    source_name=item.get("name", ""),
                    status="skipped" if is_skipped else "pending_crawl",
                    error=reason,
                    created_at=datetime.now(),
                )
                db.add(detail)
                db.flush()
            elif detail.status not in {"saved", "skipped"}:
                detail.status = "skipped" if is_skipped else "pending_crawl"
                detail.error = reason
                detail.item_data = None
                detail.crawled_at = None
                detail.saved_at = None
            detail_index.remember(detail)
            created_details.append(detail)
            if is_skipped:
                skipped_count += 1
                if append_source_task_id(db, item.get("code"), task.id):
                    append_run_log_for_run(db, run, f"已存在影片追加任务ID: {item.get('code')} -> {task.id}", "INFO", code=item.get("code"))
        increment_progress(progress, "total", len(items))
        increment_progress(progress, "skipped", skipped_count)
        write_progress(runtime, str(run.id), progress)
        db.commit()
        publish_run_detail_updated(db, run, created_details)
        if items:
            append_run_log_for_run(db, run, f"创建子任务 {len(items)} 条，跳过 {skipped_count} 条")

    def on_item_saved(task_info: dict[str, Any], item_data: dict[str, Any]) -> None:
        detail = detail_index.find(task_info, item_data)
        code = item_data.get("code") or task_info.get("code") or "-"
        # Inject source_task_ids into item_data for persistence
        item_data_with_task_ids = {**item_data, "source_task_ids": [task.id]}
        try:
            movie_id = upsert_movie_with_magnets(db, item_data_with_task_ids)
            if detail:
                detail.status = "saved"
                detail.item_data = item_data
                detail.error = None
                detail.crawled_at = datetime.now()
                detail.saved_at = datetime.now()
            increment_progress(progress, "saved")
            append_run_log_for_run(db, run, f"入库成功: {code}", "INFO", code=code, movie_id=str(movie_id))
        except Exception as exc:
            if detail:
                detail.status = "save_failed"
                detail.item_data = item_data
                detail.error = str(exc)[:500]
                detail.crawled_at = datetime.now()
                detail.saved_at = None
            increment_progress(progress, "save_failed")
            append_run_log_for_run(db, run, f"入库失败: {code}: {exc}", "ERROR", code=code)
        write_progress(runtime, str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])

    def on_detail_failed(task_info: dict[str, Any], error: str) -> None:
        detail = detail_index.find(task_info)
        if detail:
            detail.status = "crawl_failed"
            detail.error = error[:500]
            detail.crawled_at = datetime.now()
        increment_progress(progress, "failed")
        write_progress(runtime, str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
        append_run_log_for_run(db, run, f"爬取失败: {task_info.get('code') or task_info.get('url')}: {error}", "ERROR")

    def on_item_already_exists(task_info: dict[str, Any]) -> None:
        detail = detail_index.find(task_info)
        code = task_info.get("code")
        was_skipped = detail is not None and detail.status == "skipped"
        if detail:
            detail.status = "skipped"
            detail.error = "already_exists"
            detail.crawled_at = detail.crawled_at or datetime.now()
            detail.saved_at = None
        append_source_task_id(db, code, task.id)
        if not was_skipped:
            increment_progress(progress, "skipped")
        write_progress(runtime, str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
        append_run_log_for_run(db, run, f"跳过已存在影片并追加任务ID: {code}", "INFO", code=code)

    def log_callback(message: str, level: str = "INFO") -> None:
        append_run_log_for_run(db, run, message, level)

    def db_check_callback(codes: list[str]) -> set[str]:
        existing_codes = find_existing_movie_codes(db, codes)
        if existing_codes:
            append_run_log_for_run(db, run, f"列表阶段发现已存在影片 {len(existing_codes)} 条", "INFO")
        return existing_codes

    def on_detail_check_callback(code: str) -> bool:
        exists = movie_code_exists(db, code)
        if exists:
            append_run_log_for_run(db, run, f"详情阶段跳过已存在影片: {code}", "INFO", code=code)
        return exists

    # Preload existing detail tasks for in-place restart
    existing_details = (
        db.query(CrawlRunDetailTask)
        .filter(CrawlRunDetailTask.run_id == run.id)
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    for detail in existing_details:
        detail_index.remember(detail)

    # Execute crawl
    try:
        engine_task = to_scraper_task(task)
        engine = get_crawler_engine()

        detail_phase_restart = has_detail_phase_started(db, run)
        restartable_existing_details = [
            detail for detail in existing_details
            if detail.status in RESTARTABLE_DETAIL_STATUSES
        ]
        if detail_phase_restart and restartable_existing_details:
            append_run_log_for_run(
                db,
                run,
                f"检测到已有详情子任务 {len(restartable_existing_details)} 条，跳过列表收集直接重试详情",
                "INFO",
            )
            result = engine.crawl_detail_tasks(
                engine_task,
                detail_tasks=[detail_row_to_task_info(detail) for detail in restartable_existing_details],
                task_id=str(run.task_id) if run.task_id else None,
                callbacks=CrawlCallbacks(
                    on_item_saved=on_item_saved,
                    on_detail_failed=on_detail_failed,
                    on_item_already_exists=on_item_already_exists,
                    log_callback=log_callback,
                    on_detail_check_callback=on_detail_check_callback,
                    stop_check=lambda: runtime.is_stop_requested(str(run.id)),
                ),
            )
        else:
            incremental_threshold = read_incremental_threshold_from_conf()
            result = engine.crawl_task(
                engine_task,
                task_id=str(run.task_id) if run.task_id else None,
                crawl_mode=run.crawl_mode,
                incremental_threshold=incremental_threshold,
                callbacks=CrawlCallbacks(
                    on_tasks_batch_created=on_tasks_batch_created,
                    on_item_saved=on_item_saved,
                    on_detail_failed=on_detail_failed,
                    on_item_already_exists=on_item_already_exists,
                    log_callback=log_callback,
                    db_check_callback=db_check_callback,
                    on_detail_check_callback=on_detail_check_callback,
                    stop_check=lambda: runtime.is_stop_requested(str(run.id)),
                ),
            )

        stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
        if stopped:
            reset_details = reset_unfinished_detail_tasks_to_pending(db, run)
            if reset_details:
                publish_run_detail_updated(db, run, reset_details)

        total_count = count_run_detail_tasks(db, run.id)
        saved_count = count_run_detail_tasks(db, run.id, "saved")
        save_failed_count = count_run_detail_tasks(db, run.id, "save_failed")
        crawl_failed_count = count_run_detail_tasks(db, run.id, "crawl_failed")
        skipped_count = count_run_detail_tasks(db, run.id, "skipped")
        run.result = {
            **(result or {}),
            "total_tasks": total_count,
            "saved": saved_count,
            "save_failed": save_failed_count,
            "crawl_failed": crawl_failed_count,
            "skipped_tasks": skipped_count,
            "stopped": stopped,
        }
        if stopped:
            run.status = "stopped"
            run.error = run.error or "用户停止任务"
            append_run_log_for_run(
                db,
                run,
                f"任务已停止: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
                "WARNING",
            )
        else:
            run.status = "completed"
            append_run_log_for_run(
                db, run,
                f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
                "INFO",
            )
            try:
                sync_result = sync_movie_filters(db)
                append_run_log_for_run(
                    db, run,
                    f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, "
                    f"导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}",
                    "INFO",
                )
            except Exception as sync_exc:
                logger.warning("Failed to sync movie filters for run %s: %s", run.id, sync_exc)
                append_run_log_for_run(db, run, f"筛选列表同步失败: {sync_exc}", "WARNING")
    except Exception:
        raise

    run.finished_at = datetime.now()
    db.commit()
    publish_run_updated(db, run)
