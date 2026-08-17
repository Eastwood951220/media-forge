"""Startup normalization for crawler agent state.

When the backend restarts, any Agent that was marked ``online`` or ``busy``
can no longer be trusted: its WebSocket connection is gone and its process
may have died.  Likewise, any work item that was ``assigned`` or ``running``
is never going to complete for the previous backend instance.  This module
cleans both tables up so the system starts from a known, safe state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def normalize_agent_state_on_startup(db: "Session") -> tuple[int, int]:
    """Mark stale agents offline and terminalize active work items.

    Returns ``(offline_agent_count, failed_work_item_count)``.
    """
    from sqlalchemy import update

    from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentWorkItem

    now = datetime.now(UTC)

    offline_count = (
        db.query(CrawlerAgent)
        .filter(CrawlerAgent.status.in_(["online", "busy"]))
        .update({"status": "offline"}, synchronize_session="fetch")
    )

    failed_count = (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.status.in_(["assigned", "running"]))
        .update(
            {
                "status": "failed",
                "error_reason": "agent_backend_restarted",
                "finished_at": now,
                "claimed_until": None,
            },
            synchronize_session="fetch",
        )
    )

    db.commit()
    return offline_count, failed_count
