from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.parser_bridge import (
    AgentPageSnapshot,
    parse_agent_detail_snapshot,
    parse_agent_list_snapshot,
)
from backend.app.modules.crawler.agent.work_items import (
    is_work_item_completable,
    mark_work_item_failed,
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
    if not is_work_item_completable(item):
        return item
    try:
        if item.page_kind == "list":
            item.result_json = {"tasks": parse_agent_list_snapshot(snapshot)}
        elif item.page_kind == "detail":
            item.result_json = {"detail": parse_agent_detail_snapshot(snapshot)}
        else:
            raise ValueError(f"unsupported_page_kind:{item.page_kind}")
    except Exception as exc:
        mark_work_item_failed(db, item, str(exc))
        raise
    item.status = "completed"
    item.error_reason = None
    item.claimed_until = None
    db.commit()
    db.refresh(item)
    return item


def execute_agent_crawl(
    db: Session,
    run,  # CrawlRun
    task,  # CrawlTask
    runtime,  # Any
    *,
    detail_only: bool = False,
    selected_task_url_ids: list | None = None,
) -> dict:
    raise RuntimeError(
        "JavDB Agent runtime is configured but Agent work execution is not available in this task"
    )
