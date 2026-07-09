from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm.exc import ObjectDeletedError
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.movies.persistence import (
    append_source_task_id,
    append_source_task_ids_for_codes,
    upsert_movie_with_magnets,
)
from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
from backend.app.modules.crawler.runtime.engine import CrawlCallbacks
from backend.app.modules.crawler.runtime.events import (
    append_run_log_for_run,
    publish_run_detail_updated,
)
from backend.app.modules.crawler.runtime.progress import ProgressState, increment_progress, write_progress
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.source_task_names import (
    find_existing_movie_codes,
    movie_code_exists,
)


@dataclass
class CrawlerCallbackContext:
    """Shared state for all crawler callbacks."""

    db: Session
    run: CrawlRun
    task: CrawlTask
    runtime: CrawlerRuntimeState
    detail_index: DetailTaskIndex
    progress: ProgressState


def build_crawl_callbacks(
    ctx: CrawlerCallbackContext,
    *,
    include_list_callbacks: bool = True,
) -> CrawlCallbacks:
    """Build a CrawlCallbacks instance from the given context.

    When *include_list_callbacks* is ``True`` the returned callbacks include
    ``on_tasks_batch_created`` and ``db_check_callback`` which are only needed
    for a full crawl (list + detail).  For detail-only restarts these are
    omitted.
    """

    def active_indexed_detail(
        task_info: dict[str, Any],
        item_data: dict[str, Any] | None = None,
    ) -> CrawlRunDetailTask | None:
        detail = ctx.detail_index.find(task_info, item_data)
        if detail is None:
            return None
        try:
            detail.id
        except ObjectDeletedError:
            ctx.detail_index.forget(detail)
            return None
        return detail

    def detail_log_context(
        task_info: dict[str, Any],
        detail: CrawlRunDetailTask | None,
        *,
        item_data: dict[str, Any] | None = None,
        detail_status: str | None = None,
    ) -> dict[str, Any]:
        item_data = item_data or {}
        context: dict[str, Any] = {
            "code": item_data.get("code") or task_info.get("code"),
            "source_url": task_info.get("url") or item_data.get("source_url"),
            "source_url_name": task_info.get("_task_url_name"),
            "detail_status": detail_status,
        }
        if detail is not None:
            context["detail_id"] = str(detail.id)
            context["source_url"] = detail.source_url or context.get("source_url")
            context["source_url_name"] = detail.source_url_name or context.get("source_url_name")
        return {key: value for key, value in context.items() if value is not None}

    def on_tasks_batch_created(items: list[dict[str, Any]]) -> None:
        skipped_count = 0
        created_details: list[CrawlRunDetailTask] = []
        for item in items:
            is_skipped = item.get("status") == "skipped"
            reason = item.get("reason") if is_skipped else None
            detail = active_indexed_detail(item)
            if detail is None:
                detail = CrawlRunDetailTask(
                    run_id=ctx.run.id,
                    task_name=ctx.task.name,
                    code=item.get("code"),
                    source_url=item.get("url", ""),
                    source_name=item.get("name", ""),
                    source_url_name=item.get("_task_url_name"),
                    task_url=item.get("_task_url"),
                    task_final_url=item.get("_task_final_url"),
                    task_url_type=item.get("_task_url_type"),
                    status="skipped" if is_skipped else "pending_crawl",
                    error=reason,
                    created_at=datetime.now(),
                )
                ctx.db.add(detail)
                ctx.db.flush()
            elif detail.status not in {"saved", "skipped"}:
                detail.status = "skipped" if is_skipped else "pending_crawl"
                detail.error = reason
                detail.item_data = None
                detail.crawled_at = None
                detail.saved_at = None
                detail.source_url_name = item.get("_task_url_name")
                detail.task_url = item.get("_task_url")
                detail.task_final_url = item.get("_task_final_url")
                detail.task_url_type = item.get("_task_url_type")
            ctx.detail_index.remember(detail)
            created_details.append(detail)
            if is_skipped:
                skipped_count += 1
                if append_source_task_id(ctx.db, item.get("code"), ctx.task.id):
                    append_run_log_for_run(ctx.db, ctx.run, f"已存在影片追加任务ID: {item.get('code')} -> {ctx.task.id}", "INFO", code=item.get("code"))
        increment_progress(ctx.progress, "total", len(items))
        increment_progress(ctx.progress, "skipped", skipped_count)
        write_progress(ctx.runtime, str(ctx.run.id), ctx.progress)
        ctx.db.commit()
        publish_run_detail_updated(ctx.db, ctx.run, created_details)
        publish_run_detail_updated(
            ctx.db,
            ctx.run,
            [],
            refresh_tasks=True,
            reason="url_completed",
        )
        if items:
            append_run_log_for_run(ctx.db, ctx.run, f"创建子任务 {len(items)} 条，跳过 {skipped_count} 条")

    def on_item_saved(task_info: dict[str, Any], item_data: dict[str, Any]) -> None:
        detail = active_indexed_detail(task_info, item_data)
        code = item_data.get("code") or task_info.get("code") or "-"
        run_id_str = str(ctx.run.id)
        # Inject source_task_ids into item_data for persistence
        item_data_with_task_ids = {**item_data, "source_task_ids": [ctx.task.id]}
        try:
            movie_id = upsert_movie_with_magnets(ctx.db, item_data_with_task_ids)
            if detail:
                detail.status = "saved"
                detail.item_data = item_data
                detail.error = None
                detail.crawled_at = datetime.now()
                detail.saved_at = datetime.now()
            increment_progress(ctx.progress, "saved")
            append_run_log_for_run(
                ctx.db, ctx.run, f"入库成功: {code}", "INFO",
                **detail_log_context(task_info, detail, item_data=item_data, detail_status="saved"),
                movie_id=str(movie_id),
            )
        except Exception as exc:
            ctx.db.rollback()
            if detail:
                try:
                    detail.status = "save_failed"
                    detail.item_data = item_data
                    detail.error = str(exc)[:500]
                    detail.crawled_at = datetime.now()
                    detail.saved_at = None
                except Exception:
                    pass
            increment_progress(ctx.progress, "save_failed")
            try:
                append_run_log_for_run(
                    ctx.db, ctx.run, f"入库失败: {code}: {exc}", "ERROR",
                    **detail_log_context(task_info, detail, item_data=item_data, detail_status="save_failed"),
                )
            except Exception:
                logger.warning("入库失败且日志写入异常: code=%s error=%s", code, exc)
        write_progress(ctx.runtime, run_id_str, ctx.progress)
        try:
            ctx.db.commit()
        except Exception:
            ctx.db.rollback()
        if detail:
            try:
                publish_run_detail_updated(ctx.db, ctx.run, [detail])
            except Exception:
                pass

    def on_detail_failed(task_info: dict[str, Any], error: str) -> None:
        detail = active_indexed_detail(task_info)
        if detail:
            detail.status = "crawl_failed"
            detail.error = error[:500]
            detail.crawled_at = datetime.now()
        increment_progress(ctx.progress, "failed")
        write_progress(ctx.runtime, str(ctx.run.id), ctx.progress)
        ctx.db.commit()
        if detail:
            publish_run_detail_updated(ctx.db, ctx.run, [detail])
        append_run_log_for_run(
            ctx.db, ctx.run, f"详情失败: {task_info.get('code') or task_info.get('url')}: {error}", "ERROR",
            **detail_log_context(task_info, detail, detail_status="crawl_failed"),
        )

    def on_item_already_exists(task_info: dict[str, Any]) -> None:
        detail = active_indexed_detail(task_info)
        code = task_info.get("code")
        was_skipped = detail is not None and detail.status == "skipped"
        if detail:
            detail.status = "skipped"
            detail.error = "already_exists"
            detail.crawled_at = detail.crawled_at or datetime.now()
            detail.saved_at = None
        append_source_task_id(ctx.db, code, ctx.task.id)
        if detail is not None and not was_skipped:
            increment_progress(ctx.progress, "skipped")
        write_progress(ctx.runtime, str(ctx.run.id), ctx.progress)
        ctx.db.commit()
        if detail:
            publish_run_detail_updated(ctx.db, ctx.run, [detail])
        append_run_log_for_run(
            ctx.db, ctx.run, f"跳过已存在影片并追加任务ID: {code}", "INFO",
            **detail_log_context(task_info, detail, detail_status="skipped"),
        )

    def log_callback(message: str, level: str = "INFO") -> None:
        append_run_log_for_run(ctx.db, ctx.run, message, level)

    def db_check_callback(codes: list[str]) -> set[str]:
        existing_codes = find_existing_movie_codes(ctx.db, codes)
        if existing_codes:
            changed_codes = append_source_task_ids_for_codes(ctx.db, existing_codes, ctx.task.id)
            append_run_log_for_run(ctx.db, ctx.run, f"列表阶段发现已存在影片 {len(existing_codes)} 条", "INFO")
            if changed_codes:
                append_run_log_for_run(ctx.db, ctx.run, f"列表阶段已存在影片追加任务ID {len(changed_codes)} 条", "INFO")
        return existing_codes

    def on_detail_check_callback(code: str) -> bool:
        exists = movie_code_exists(ctx.db, code)
        if exists:
            append_run_log_for_run(ctx.db, ctx.run, f"详情阶段跳过已存在影片: {code}", "INFO", code=code)
        return exists

    def stop_check() -> bool:
        return ctx.runtime.is_stop_requested(str(ctx.run.id))

    callbacks = CrawlCallbacks(
        on_item_saved=on_item_saved,
        on_detail_failed=on_detail_failed,
        on_item_already_exists=on_item_already_exists,
        log_callback=log_callback,
        on_detail_check_callback=on_detail_check_callback,
        stop_check=stop_check,
    )

    if include_list_callbacks:
        callbacks.on_tasks_batch_created = on_tasks_batch_created
        callbacks.db_check_callback = db_check_callback

    return callbacks
