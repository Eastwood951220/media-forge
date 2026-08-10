from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem


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
