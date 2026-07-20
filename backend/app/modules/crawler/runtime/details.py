from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from scraper.tasks.task_utils import determine_source

UNFINISHED_DETAIL_STATUSES = {"pending_crawl", "crawling", "crawl_failed", "save_failed"}
RESTARTABLE_DETAIL_STATUSES = UNFINISHED_DETAIL_STATUSES
TERMINAL_DETAIL_STATUSES = {"saved", "skipped"}
DETAIL_PHASE_STARTED_STATUSES = {"saved", "crawl_failed", "save_failed"}
ENDED_RUN_STATUSES = {"completed", "failed", "stopped"}
DETAIL_RETRY_STATUS = "pending_crawl"


def has_detail_phase_started(db: Session, run: CrawlRun) -> bool:
    return db.query(CrawlRunDetailTask.id).filter(
        CrawlRunDetailTask.run_id == run.id,
        (
            CrawlRunDetailTask.status.in_(DETAIL_PHASE_STARTED_STATUSES)
            | CrawlRunDetailTask.crawled_at.isnot(None)
            | CrawlRunDetailTask.saved_at.isnot(None)
        ),
    ).first() is not None


def reset_unfinished_detail_tasks_to_pending(
    db: Session,
    run: CrawlRun,
) -> list[CrawlRunDetailTask]:
    details = (
        db.query(CrawlRunDetailTask)
        .filter(
            CrawlRunDetailTask.run_id == run.id,
            CrawlRunDetailTask.status.notin_(TERMINAL_DETAIL_STATUSES),
        )
        .order_by(CrawlRunDetailTask.created_at.asc())
        .all()
    )
    for detail in details:
        detail.status = "pending_crawl"
        detail.error = None
        detail.crawled_at = None
        detail.saved_at = None
    db.flush()
    return details


def clear_run_detail_tasks(db: Session, run: CrawlRun) -> None:
    db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).delete(synchronize_session=False)


def count_run_detail_tasks(db: Session, run_id: uuid.UUID, status: str | None = None) -> int:
    query = db.query(func.count(CrawlRunDetailTask.id)).filter(CrawlRunDetailTask.run_id == run_id)
    if status is not None:
        query = query.filter(CrawlRunDetailTask.status == status)
    return int(query.scalar() or 0)


def detail_row_to_task_info(detail: CrawlRunDetailTask) -> dict[str, Any]:
    return {
        "code": detail.code,
        "url": detail.source_url,
        "name": detail.source_name,
        "_task_url": detail.task_url,
        "_task_final_url": detail.task_final_url,
        "_task_url_type": detail.task_url_type,
        "_task_url_name": detail.source_url_name,
        "_task_source": determine_source(detail.source_url),
    }
