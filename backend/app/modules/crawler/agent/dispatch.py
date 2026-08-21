from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgentEvent, CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.diagnostics import (
    add_agent_event,
    commit_and_publish_agent_events,
)
from backend.app.modules.crawler.agent.registry import agent_registry


@dataclass(frozen=True)
class WorkItemWakeupResult:
    status: str
    event_type: str
    message: str


async def notify_work_item_available(
    db: Session,
    *,
    owner_id: uuid.UUID,
    work_item: CrawlerAgentWorkItem,
) -> WorkItemWakeupResult:
    payload = {
        "work_item_id": str(work_item.id),
        "run_id": str(work_item.run_id),
        "page_kind": work_item.page_kind,
    }
    try:
        sent = await agent_registry.send_to_ready_owner(
            str(owner_id),
            "task.available",
            payload,
        )
    except Exception as exc:
        result = WorkItemWakeupResult(
            status="send_failed",
            event_type="task_available_send_failed",
            message=f"Chrome Agent 通知失败: {exc}",
        )
        _record_wakeup_event(db, owner_id=owner_id, work_item=work_item, result=result, level="warning")
        return result

    if not sent:
        result = WorkItemWakeupResult(
            status="no_ready_agent",
            event_type="task_available_no_ready_agent",
            message="Chrome Agent 无 ready WebSocket，等待轮询领取",
        )
        _record_wakeup_event(db, owner_id=owner_id, work_item=work_item, result=result, level="warning")
        return result

    result = WorkItemWakeupResult(
        status="sent",
        event_type="task_available_sent",
        message="Chrome Agent 已通知领取任务",
    )
    _record_wakeup_event(db, owner_id=owner_id, work_item=work_item, result=result, level="info")
    return result


def _record_wakeup_event(
    db: Session,
    *,
    owner_id: uuid.UUID,
    work_item: CrawlerAgentWorkItem,
    result: WorkItemWakeupResult,
    level: str,
) -> CrawlerAgentEvent:
    event = add_agent_event(
        db,
        owner_id=owner_id,
        source="backend",
        event_type=result.event_type,
        level=level,
        message=result.message,
        retention_class="operational",
        run_id=work_item.run_id,
        work_item_id=work_item.id,
        phase="dispatch.wakeup",
        details={"page_kind": work_item.page_kind, "status": result.status},
    )
    commit_and_publish_agent_events(db, [event])
    return event
