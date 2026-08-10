from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.parser_bridge import (
    AgentPageSnapshot,
    parse_agent_detail_snapshot,
    parse_agent_list_snapshot,
)


def complete_work_item_from_snapshot(
    db: Session,
    *,
    work_item_id: str,
    snapshot: AgentPageSnapshot,
) -> CrawlerAgentWorkItem:
    item = db.get(CrawlerAgentWorkItem, uuid.UUID(work_item_id))
    if item is None:
        raise ValueError("agent_work_item_not_found")
    if item.page_kind == "list":
        item.result_json = {"tasks": parse_agent_list_snapshot(snapshot)}
    elif item.page_kind == "detail":
        item.result_json = {"detail": parse_agent_detail_snapshot(snapshot)}
    else:
        raise ValueError(f"unsupported_page_kind:{item.page_kind}")
    item.status = "completed"
    item.error_reason = None
    item.claimed_until = None
    db.commit()
    db.refresh(item)
    return item
