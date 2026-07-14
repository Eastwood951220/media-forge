from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.modules.crawler.runtime.details import (
    ENDED_RUN_STATUSES,
    RESTARTABLE_DETAIL_STATUSES,
    clear_run_detail_tasks,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)


def ensure_run_can_restart(db: Session, run: CrawlRun) -> None:
    if run.status not in {"stopped", "failed"}:
        raise ValueError("只能重启已停止或失败的运行")
    if run.task_id is not None:
        return
    restartable_count = (
        db.query(CrawlRunDetailTask)
        .filter(
            CrawlRunDetailTask.run_id == run.id,
            CrawlRunDetailTask.status.in_(RESTARTABLE_DETAIL_STATUSES),
        )
        .count()
    )
    if restartable_count == 0:
        raise ValueError("没有关联任务或未完成子任务，无法重启")


def prepare_run_for_restart(db: Session, run: CrawlRun) -> None:
    if has_detail_phase_started(db, run):
        reset_unfinished_detail_tasks_to_pending(db, run)
    else:
        clear_run_detail_tasks(db, run)
    run.status = "queued"
    run.queued_at = datetime.now()
    run.started_at = None
    run.finished_at = None
    run.result = None
    run.error = None


def select_retry_details(
    db: Session,
    run: CrawlRun,
    *,
    detail_ids: list[uuid.UUID] | None,
    retry_all: bool,
) -> tuple[list[CrawlRunDetailTask], str]:
    if run.status not in ENDED_RUN_STATUSES:
        raise ValueError("运行中不能重试失败子任务")

    if retry_all:
        details = (
            db.query(CrawlRunDetailTask)
            .filter(
                CrawlRunDetailTask.run_id == run.id,
                CrawlRunDetailTask.status == "crawl_failed",
            )
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        retry_label = "全部失败"
    else:
        if not detail_ids:
            raise ValueError("请选择要重新爬取的失败子任务")
        details = (
            db.query(CrawlRunDetailTask)
            .filter(CrawlRunDetailTask.id.in_(detail_ids))
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        found_ids = {detail.id for detail in details}
        missing_ids = [detail_id for detail_id in detail_ids if detail_id not in found_ids]
        if missing_ids:
            raise ValueError("包含无效的子任务选择")
        retry_label = "选中项" if len(details) > 1 else "单条"

    if not details:
        raise ValueError("没有爬取失败的子任务可重试")
    for detail in details:
        if detail.run_id != run.id:
            raise ValueError("包含不属于当前运行的子任务")
        if detail.status != "crawl_failed":
            raise ValueError("只能重试 crawl_failed 状态的子任务")
    return details, retry_label


def mark_details_for_retry(details: list[CrawlRunDetailTask]) -> None:
    for detail in details:
        detail.status = "pending_crawl"
        detail.error = None
        detail.item_data = None
        detail.crawled_at = None
        detail.saved_at = None
