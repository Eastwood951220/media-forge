from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask


def _detail_identity_filter(run_id: uuid.UUID, item: dict[str, Any]):
    code = item.get("code")
    source_url = item.get("url") or item.get("source_url")
    if code:
        return (CrawlRunDetailTask.run_id == run_id) & (CrawlRunDetailTask.code == str(code))
    return (CrawlRunDetailTask.run_id == run_id) & (CrawlRunDetailTask.source_url == str(source_url or ""))


def upsert_detail_task(
    db: Session,
    *,
    run: CrawlRun,
    task_name: str,
    item: dict[str, Any],
) -> CrawlRunDetailTask | None:
    existing = db.scalar(select(CrawlRunDetailTask).where(_detail_identity_filter(run.id, item)).limit(1))
    if existing is not None:
        return None
    is_skipped = item.get("status") == "skipped"
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task_name,
        code=item.get("code"),
        source_url=item.get("url") or item.get("source_url") or "",
        source_name=item.get("name") or item.get("source_name") or "",
        source_url_name=item.get("_task_url_name"),
        task_url=item.get("_task_url"),
        task_final_url=item.get("_task_final_url"),
        task_url_type=item.get("_task_url_type"),
        status="skipped" if is_skipped else "pending_crawl",
        error=item.get("reason") if is_skipped else None,
        created_at=datetime.now(),
    )
    db.add(detail)
    db.flush()
    return detail


def claim_next_pending_detail(db: Session, run_id: uuid.UUID) -> CrawlRunDetailTask | None:
    detail = db.scalar(
        select(CrawlRunDetailTask)
        .where(
            CrawlRunDetailTask.run_id == run_id,
            CrawlRunDetailTask.status == "pending_crawl",
        )
        .order_by(CrawlRunDetailTask.created_at.asc())
        .limit(1)
    )
    if detail is None:
        return None
    detail.status = "crawling"
    detail.error = None
    db.commit()
    db.refresh(detail)
    return detail


def reset_crawling_details_to_pending(db: Session, run: CrawlRun) -> list[CrawlRunDetailTask]:
    details = (
        db.query(CrawlRunDetailTask)
        .filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "crawling")
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
