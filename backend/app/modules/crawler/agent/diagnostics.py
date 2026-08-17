from __future__ import annotations

import base64
import json
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentEvent
from backend.app.modules.crawler.agent.constants import AGENT_EVENT_RETENTION_DAYS

logger = logging.getLogger(__name__)
MAX_EVENT_MESSAGE_LENGTH = 500
MAX_EVENT_DETAILS_BYTES = 4096
SENSITIVE_KEY_PARTS = (
    "token", "session", "cookie", "authorization", "html", "snapshot", "fragment",
)
ALLOWED_DETAIL_KEYS: frozenset[str] = frozenset({
    "duration_ms", "tab_id", "page_kind", "url", "status", "reason",
    "error_code", "retry_after_ms", "protocol_version", "extension_version",
    "capabilities", "attempt", "pending_count", "active_count",
})
_cleanup_lock = threading.Lock()
_next_cleanup_at: datetime | None = None


@dataclass(frozen=True)
class AgentEventPage:
    rows: list[CrawlerAgentEvent]
    next_cursor: str | None
    has_more: bool


def _safe_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if not details:
        return None
    safe: dict[str, Any] = {
        key: value
        for key, value in details.items()
        if key in ALLOWED_DETAIL_KEYS
        and not any(part in key.lower() for part in SENSITIVE_KEY_PARTS)
    }
    encoded = json.dumps(safe, ensure_ascii=False, default=str).encode("utf-8")
    return safe if len(encoded) <= MAX_EVENT_DETAILS_BYTES else {"reason": "details_truncated"}


def add_agent_event(
    db: Session,
    *,
    owner_id: uuid.UUID,
    source: str,
    event_type: str,
    level: str,
    message: str,
    retention_class: str,
    agent_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    work_item_id: uuid.UUID | None = None,
    attempt: int | None = None,
    phase: str | None = None,
    details: dict[str, Any] | None = None,
) -> CrawlerAgentEvent:
    event = CrawlerAgentEvent(
        owner_id=owner_id,
        agent_id=agent_id,
        run_id=run_id,
        work_item_id=work_item_id,
        attempt=attempt,
        source=source,
        event_type=event_type,
        phase=phase,
        level=level,
        message=str(message)[:MAX_EVENT_MESSAGE_LENGTH],
        details_json=_safe_details(details),
        retention_class=retention_class,
    )
    db.add(event)
    return event


def serialize_agent_event(event: CrawlerAgentEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "owner_id": str(event.owner_id),
        "agent_id": str(event.agent_id) if event.agent_id else None,
        "run_id": str(event.run_id) if event.run_id else None,
        "work_item_id": str(event.work_item_id) if event.work_item_id else None,
        "attempt": event.attempt,
        "source": event.source,
        "event_type": event.event_type,
        "phase": event.phase,
        "level": event.level,
        "message": event.message,
        "details": event.details_json,
        "retention_class": event.retention_class,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def commit_and_publish_agent_events(
    db: Session, events: list[CrawlerAgentEvent]
) -> None:
    from backend.app.modules.crawler.runtime.events import (
        publish_agent_event_created,
    )

    db.commit()
    for event in events:
        db.refresh(event)
        publish_agent_event_created(event)

    _maybe_cleanup_expired_events(db)


def _maybe_cleanup_expired_events(db: Session) -> None:
    """Guard opportunistic cleanup with a lock so it runs at most once per day."""
    global _next_cleanup_at  # noqa: PLW0603

    now = datetime.now(UTC)
    if _next_cleanup_at is not None and now < _next_cleanup_at:
        return

    with _cleanup_lock:
        if _next_cleanup_at is not None and now < _next_cleanup_at:
            return
        try:
            count = delete_expired_operational_events(db, now=now)
            if count:
                logger.info("Cleaned up %d expired operational events", count)
        except Exception:
            logger.warning("Failed to clean up expired operational events", exc_info=True)
        finally:
            _next_cleanup_at = now + timedelta(days=1)


def _decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not cursor:
        return None
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, id_str = raw.split(",", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


def _encode_cursor(created_at: datetime, event_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()},{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def list_agent_events(
    db: Session,
    *,
    owner_id: uuid.UUID,
    run_id: uuid.UUID | None = None,
    cursor: str | None = None,
    size: int = 50,
    level: str | None = None,
    source: str | None = None,
    phase: str | None = None,
    work_item_id: uuid.UUID | None = None,
) -> AgentEventPage:
    query = db.query(CrawlerAgentEvent).filter(
        CrawlerAgentEvent.owner_id == owner_id,
    )

    if run_id is not None:
        query = query.filter(CrawlerAgentEvent.run_id == run_id)
    if level is not None:
        query = query.filter(CrawlerAgentEvent.level == level)
    if source is not None:
        query = query.filter(CrawlerAgentEvent.source == source)
    if phase is not None:
        query = query.filter(CrawlerAgentEvent.phase == phase)
    if work_item_id is not None:
        query = query.filter(CrawlerAgentEvent.work_item_id == work_item_id)

    cursor_tuple = _decode_cursor(cursor)
    if cursor_tuple is not None:
        cursor_time, cursor_id = cursor_tuple
        query = query.filter(
            or_(
                CrawlerAgentEvent.created_at < cursor_time,
                (
                    (CrawlerAgentEvent.created_at == cursor_time)
                    & (CrawlerAgentEvent.id < cursor_id)
                ),
            )
        )

    query = query.order_by(
        CrawlerAgentEvent.created_at.desc(), CrawlerAgentEvent.id.desc()
    )

    rows = query.limit(size + 1).all()
    has_more = len(rows) > size
    if has_more:
        rows = rows[:size]

    next_cursor: str | None = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return AgentEventPage(rows=rows, next_cursor=next_cursor, has_more=has_more)


def delete_operational_events(
    db: Session, *, owner_id: uuid.UUID
) -> int:
    return (
        db.query(CrawlerAgentEvent)
        .filter(
            CrawlerAgentEvent.owner_id == owner_id,
            CrawlerAgentEvent.retention_class == "operational",
        )
        .delete(synchronize_session="fetch")
    )


def delete_expired_operational_events(
    db: Session, *, now: datetime | None = None
) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=AGENT_EVENT_RETENTION_DAYS)
    return (
        db.query(CrawlerAgentEvent)
        .filter(
            CrawlerAgentEvent.retention_class == "operational",
            CrawlerAgentEvent.created_at < cutoff,
        )
        .delete(synchronize_session="fetch")
    )