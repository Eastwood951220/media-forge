from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.errors import (
    AgentWorkFailedError,
    AgentWorkStopped,
    AgentWorkTimeoutError,
)

COMPLETABLE_WORK_ITEM_STATUSES = {"pending", "assigned", "running"}


def claim_next_work_item(
    db: Session,
    *,
    owner_id: str,
    agent_id: str,
    lease_seconds: int = 120,
) -> CrawlerAgentWorkItem | None:
    item = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.owner_id == uuid.UUID(owner_id))
        .filter(CrawlerAgentWorkItem.status == "pending")
        .order_by(CrawlerAgentWorkItem.created_at.asc())
        .first()
    )
    if item is None:
        return None
    item.status = "assigned"
    item.assigned_agent_id = uuid.UUID(agent_id)
    item.attempt += 1
    item.claimed_until = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(item)
    return item


def expire_stale_work_items(db: Session, *, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    items = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.status.in_(["assigned", "running"]))
        .filter(CrawlerAgentWorkItem.claimed_until.isnot(None))
        .filter(CrawlerAgentWorkItem.claimed_until < current)
        .all()
    )
    for item in items:
        item.status = "pending"
        item.claimed_until = None
        item.assigned_agent_id = None
    db.commit()
    return len(items)


def create_work_item(
    db: Session,
    *,
    owner_id,
    run_id,
    task_id,
    page_kind: str,
    url: str,
    detail_task_id=None,
    url_entry_id=None,
) -> CrawlerAgentWorkItem:
    item = CrawlerAgentWorkItem(
        owner_id=owner_id,
        run_id=run_id,
        task_id=task_id,
        detail_task_id=detail_task_id,
        url_entry_id=url_entry_id,
        page_kind=page_kind,
        url=url,
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def is_work_item_completable(item: CrawlerAgentWorkItem) -> bool:
    return item.status in COMPLETABLE_WORK_ITEM_STATUSES


def mark_work_item_failed(
    db: Session,
    item: CrawlerAgentWorkItem,
    reason: str,
) -> CrawlerAgentWorkItem:
    item.status = "failed"
    item.error_reason = (reason or "agent_work_failed")[:100]
    item.claimed_until = None
    db.commit()
    db.refresh(item)
    return item


def wait_for_work_item_result(
    db: Session,
    item: CrawlerAgentWorkItem,
    *,
    runtime,
    run_id: str,
    timeout_seconds: float,
    poll_interval_seconds: float = 1.0,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> CrawlerAgentWorkItem:
    now = now or time.monotonic
    sleep = sleep or time.sleep
    deadline = now() + timeout_seconds

    while True:
        if runtime.is_stop_requested(run_id):
            raise AgentWorkStopped()
        expire_stale_work_items(db)
        db.refresh(item)
        if item.status == "completed":
            return item
        if item.status == "failed":
            raise AgentWorkFailedError(item.error_reason or "agent_work_failed")
        if now() >= deadline:
            mark_work_item_failed(db, item, "agent_work_timeout")
            raise AgentWorkTimeoutError()
        sleep(poll_interval_seconds)
