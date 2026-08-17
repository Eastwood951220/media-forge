from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.constants import AGENT_MAX_ATTEMPTS
from backend.app.modules.crawler.agent.errors import (
    AgentClaimTimeoutError,
    AgentExecutionTimeoutError,
    AgentWorkFailedError,
    AgentWorkStopped,
)

COMPLETABLE_WORK_ITEM_STATUSES = {"assigned", "running"}


def claim_next_work_item(
    db: Session,
    *,
    owner_id: str,
    agent_id: str,
    execution_timeout_seconds: int,
    now: datetime | None = None,
) -> CrawlerAgentWorkItem | None:
    now = now or datetime.now(UTC)
    item = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.owner_id == uuid.UUID(owner_id))
        .filter(CrawlerAgentWorkItem.status == "pending")
        .order_by(CrawlerAgentWorkItem.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if item is None:
        return None
    item.status = "assigned"
    item.assigned_agent_id = uuid.UUID(agent_id)
    item.assigned_at = now
    item.attempt += 1
    item.claimed_until = now + timedelta(seconds=execution_timeout_seconds)
    db.commit()
    db.refresh(item)
    return item


def mark_work_item_running(
    db: Session,
    *,
    work_item_id: uuid.UUID,
    agent_id: uuid.UUID,
    attempt: int,
    phase: str,
) -> CrawlerAgentWorkItem:
    item = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.id == work_item_id)
        .with_for_update()
        .first()
    )
    if item is None:
        raise ValueError(f"Work item {work_item_id} not found")
    if item.status != "assigned":
        raise ValueError(
            f"Cannot transition work item {work_item_id} from {item.status} to running"
        )
    if item.assigned_agent_id != agent_id or item.attempt != attempt:
        raise ValueError(
            f"Agent {agent_id} attempt {attempt} does not match work item "
            f"{work_item_id} (agent={item.assigned_agent_id}, attempt={item.attempt})"
        )
    item.status = "running"
    item.started_at = datetime.now(UTC)
    db.commit()
    db.refresh(item)
    return item


def release_agent_work_items(
    db: Session,
    *,
    agent_id: str,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    items = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.assigned_agent_id == uuid.UUID(agent_id))
        .filter(CrawlerAgentWorkItem.status.in_(["assigned", "running"]))
        .with_for_update()
        .all()
    )
    for item in items:
        if item.attempt >= AGENT_MAX_ATTEMPTS:
            item.status = "failed"
            item.error_reason = "agent_connection_lost"
            item.finished_at = now
            item.claimed_until = None
        else:
            item.status = "pending"
            item.assigned_agent_id = None
            item.assigned_at = None
            item.started_at = None
            item.claimed_until = None
    db.commit()


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
        if item.attempt >= AGENT_MAX_ATTEMPTS:
            item.status = "failed"
            item.error_reason = "agent_connection_lost"
            item.finished_at = current
        else:
            item.status = "pending"
        item.claimed_until = None
        item.assigned_agent_id = None
        item.assigned_at = None
        item.started_at = None
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
        queued_at=datetime.now(UTC),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def is_work_item_completable(item: CrawlerAgentWorkItem) -> bool:
    return item.status in COMPLETABLE_WORK_ITEM_STATUSES


def mark_work_item_failed(
    db: Session,
    *,
    work_item_id: uuid.UUID,
    reason: str,
    agent_id: uuid.UUID | None = None,
    attempt: int | None = None,
    now: datetime | None = None,
) -> CrawlerAgentWorkItem:
    now = now or datetime.now(UTC)
    item = db.get(CrawlerAgentWorkItem, work_item_id)
    if item is None:
        raise ValueError(f"Work item {work_item_id} not found")
    if agent_id is not None and item.assigned_agent_id != agent_id:
        raise ValueError(
            f"Agent {agent_id} does not own work item {work_item_id} "
            f"(owner={item.assigned_agent_id})"
        )
    if attempt is not None and item.attempt != attempt:
        raise ValueError(
            f"Attempt {attempt} does not match work item {work_item_id} "
            f"(current={item.attempt})"
        )
    item.status = "failed"
    item.error_reason = (reason or "agent_work_failed")[:100]
    item.claimed_until = None
    item.finished_at = now
    db.commit()
    db.refresh(item)
    return item


def wait_for_work_item_result(
    db: Session,
    item: CrawlerAgentWorkItem,
    *,
    runtime,
    run_id: str,
    claim_timeout_seconds: float,
    execution_timeout_seconds: float,
    poll_interval_seconds: float = 1.0,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> CrawlerAgentWorkItem:
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    start = clock()

    claim_deadline = start + claim_timeout_seconds
    execution_deadline = start + claim_timeout_seconds + execution_timeout_seconds

    while True:
        if runtime.is_stop_requested(run_id):
            raise AgentWorkStopped()

        db.refresh(item)

        if item.status == "completed":
            return item

        if item.status == "failed":
            raise AgentWorkFailedError(item.error_reason or "agent_work_failed")

        current = clock()

        if item.status == "pending":
            if current >= claim_deadline:
                mark_work_item_failed(
                    db, work_item_id=item.id, reason="agent_claim_timeout",
                )
                raise AgentClaimTimeoutError(
                    f"未在 {claim_timeout_seconds} 秒内领取任务"
                )

        elif item.status in ("assigned", "running"):
            if current >= execution_deadline:
                mark_work_item_failed(
                    db, work_item_id=item.id, reason="agent_execution_timeout",
                )
                raise AgentExecutionTimeoutError("页面执行超时")

        sleep(poll_interval_seconds)