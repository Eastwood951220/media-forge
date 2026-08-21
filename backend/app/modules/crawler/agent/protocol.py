from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentEvent, CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.constants import (
    AGENT_MINIMUM_PROTOCOL_VERSION,
    AGENT_REQUIRED_CAPABILITIES,
)
from backend.app.modules.crawler.agent.cookie_sync import AgentCookie, sync_javdb_cookies
from backend.app.modules.crawler.agent.diagnostics import add_agent_event, commit_and_publish_agent_events
from backend.app.modules.crawler.agent.errors import agent_error_message
from backend.app.modules.crawler.agent.parser_bridge import AgentPageSnapshot
from backend.app.modules.crawler.agent.registry import AgentConnection, AgentConnectionRegistry
from backend.app.modules.crawler.agent.runtime import complete_work_item_from_snapshot
from backend.app.modules.crawler.agent.schemas import (
    AgentDiagnosticBatchPayload,
    AgentHelloPayload,
    AgentPageSnapshotPayload,
    AgentTaskEventPayload,
    AgentTaskFailedPayload,
)
from backend.app.modules.crawler.agent.work_items import (
    claim_next_work_item,
    mark_work_item_failed,
    mark_work_item_running,
)
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config


@dataclass
class AgentProtocolContext:
    websocket: WebSocket
    db: Session
    agent: CrawlerAgent
    connection: AgentConnection
    registry: AgentConnectionRegistry


async def handle_agent_hello(
    ctx: AgentProtocolContext,
    message: dict[str, Any],
) -> bool:
    """Validate the agent.hello handshake message.

    Returns ``True`` when the handshake is compatible and the agent is
    marked ready (online). Returns ``False`` when the protocol version or
    capabilities are insufficient — the function sends the error and
    closes the WebSocket before returning.
    """
    payload = AgentHelloPayload.model_validate(message.get("payload") or {})
    compatible = (
        payload.protocol_version >= AGENT_MINIMUM_PROTOCOL_VERSION
        and AGENT_REQUIRED_CAPABILITIES.issubset(payload.capabilities)
    )

    if not compatible:
        ctx.agent.status = "upgrade_required"
        ctx.agent.protocol_version = payload.protocol_version
        ctx.db.commit()
        await ctx.websocket.send_json({
            "id": f"err_{message.get('id')}",
            "type": "server.error",
            "payload": {
                "reason": "upgrade_required",
                "minimum_protocol_version": AGENT_MINIMUM_PROTOCOL_VERSION,
            },
        })
        await ctx.websocket.close()
        return False

    ctx.registry.mark_ready(
        str(ctx.agent.id),
        ctx.connection.generation,
        protocol_version=payload.protocol_version,
        capabilities=payload.capabilities,
    )
    ctx.agent.status = "online"
    ctx.agent.protocol_version = payload.protocol_version
    ctx.agent.version = payload.version or ctx.agent.version
    ctx.agent.last_seen_at = datetime.now(UTC)
    ctx.db.commit()
    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {"message_id": message.get("id")},
    })
    return True


# ── Dispatch ────────────────────────────────────────────────────────────────


async def dispatch_agent_message(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    """Route a validated agent message to its handler by type."""
    msg_type = message.get("type", "")

    handler = _HANDLERS.get(msg_type)
    if handler is not None:
        await handler(ctx, message)
        return

    await ctx.websocket.send_json({
        "id": f"err_{message.get('id')}",
        "type": "server.error",
        "payload": {"reason": f"unknown_message_type:{msg_type}"},
    })


# ── Per-type handlers ───────────────────────────────────────────────────────


async def _handle_task_request(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    config = read_crawler_runtime_config()
    item = claim_next_work_item(
        ctx.db,
        owner_id=str(ctx.agent.owner_id),
        agent_id=str(ctx.agent.id),
        execution_timeout_seconds=int(config.SECURITY_WAIT_SECONDS),
    )
    if item is None:
        events: list[CrawlerAgentEvent] = [
            add_agent_event(
                ctx.db,
                owner_id=uuid.UUID(str(ctx.agent.owner_id)),
                agent_id=uuid.UUID(str(ctx.agent.id)),
                source="backend",
                event_type="task_request_received",
                level="info",
                message="Chrome Agent 请求领取任务",
                retention_class="operational",
                phase="dispatch.claim",
            ),
            add_agent_event(
                ctx.db,
                owner_id=uuid.UUID(str(ctx.agent.owner_id)),
                agent_id=uuid.UUID(str(ctx.agent.id)),
                source="backend",
                event_type="task_none",
                level="info",
                message="Chrome Agent 请求领取任务，但暂无 pending 任务",
                retention_class="operational",
                phase="dispatch.claim",
                details={"status": "none"},
            ),
        ]
        commit_and_publish_agent_events(ctx.db, events)
        await ctx.websocket.send_json({
            "id": f"none_{message.get('id')}",
            "type": "task.none",
            "payload": {},
        })
    else:
        events = [
            add_agent_event(
                ctx.db,
                owner_id=uuid.UUID(str(ctx.agent.owner_id)),
                agent_id=uuid.UUID(str(ctx.agent.id)),
                source="backend",
                event_type="task_request_received",
                level="info",
                message="Chrome Agent 请求领取任务",
                retention_class="operational",
                run_id=item.run_id,
                work_item_id=item.id,
                phase="dispatch.claim",
            ),
            add_agent_event(
                ctx.db,
                owner_id=uuid.UUID(str(ctx.agent.owner_id)),
                agent_id=uuid.UUID(str(ctx.agent.id)),
                source="backend",
                event_type="task_claimed",
                level="info",
                message="Chrome Agent 已领取任务",
                retention_class="operational",
                run_id=item.run_id,
                work_item_id=item.id,
                attempt=item.attempt,
                phase="dispatch.claim",
                details={
                    "page_kind": item.page_kind,
                    "status": item.status,
                    "attempt": item.attempt,
                },
            ),
        ]
        commit_and_publish_agent_events(ctx.db, events)
        ctx.agent.status = "busy"
        ctx.db.commit()
        await ctx.websocket.send_json({
            "id": f"task_{item.id}",
            "type": "task.assigned",
            "payload": {
                "agent_task_id": str(item.id),
                "run_id": str(item.run_id),
                "detail_task_id": str(item.detail_task_id) if item.detail_task_id else None,
                "url_entry_id": str(item.url_entry_id) if item.url_entry_id else None,
                "page_kind": item.page_kind,
                "url": item.url,
                "attempt": item.attempt,
                "execution_deadline_at": (
                    item.claimed_until.isoformat() if item.claimed_until else None
                ),
            },
        })


async def _handle_task_event(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    payload = AgentTaskEventPayload.model_validate(message.get("payload") or {})
    item: CrawlerAgentWorkItem | None = ctx.db.get(
        CrawlerAgentWorkItem, payload.agent_task_id
    )
    ignored = (
        item is None
        or item.assigned_agent_id != uuid.UUID(str(ctx.agent.id))
        or item.attempt != payload.attempt
    )

    if not ignored and item.status == "assigned":
        try:
            mark_work_item_running(
                ctx.db,
                work_item_id=item.id,
                agent_id=uuid.UUID(str(ctx.agent.id)),
                attempt=payload.attempt,
                phase=payload.phase,
            )
        except ValueError:
            ignored = True

    events: list[CrawlerAgentEvent] = []
    if not ignored:
        ev = add_agent_event(
            ctx.db,
            owner_id=uuid.UUID(str(ctx.agent.owner_id)),
            agent_id=uuid.UUID(str(ctx.agent.id)),
            work_item_id=item.id,
            attempt=payload.attempt,
            source="agent",
            event_type="task_progress",
            retention_class="operational",
            phase=payload.phase,
            level=payload.level,
            message=payload.message,
            details=payload.details,
        )
        events.append(ev)
        commit_and_publish_agent_events(ctx.db, events)

    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {"message_id": message.get("id"), "ignored": ignored},
    })


async def _handle_task_failed(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    payload = AgentTaskFailedPayload.model_validate(message.get("payload") or {})
    item: CrawlerAgentWorkItem | None = ctx.db.get(
        CrawlerAgentWorkItem, payload.agent_task_id
    )
    ignored = (
        item is None
        or item.assigned_agent_id != uuid.UUID(str(ctx.agent.id))
        or item.attempt != payload.attempt
    )

    if not ignored:
        try:
            mark_work_item_failed(
                ctx.db,
                work_item_id=item.id,
                reason=agent_error_message(payload.code),
                agent_id=uuid.UUID(str(ctx.agent.id)),
                attempt=payload.attempt,
            )
        except ValueError:
            ignored = True

    events: list[CrawlerAgentEvent] = []
    if not ignored:
        ev = add_agent_event(
            ctx.db,
            owner_id=uuid.UUID(str(ctx.agent.owner_id)),
            agent_id=uuid.UUID(str(ctx.agent.id)),
            work_item_id=item.id,
            attempt=payload.attempt,
            source="agent",
            event_type="task_failed",
            retention_class="operational",
            phase=payload.phase,
            level="error",
            message=payload.message,
            details={"reason": payload.code},
        )
        events.append(ev)
        commit_and_publish_agent_events(ctx.db, events)

    ctx.agent.last_seen_at = datetime.now(UTC)
    ctx.agent.status = "online"
    ctx.db.commit()

    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {"message_id": message.get("id"), "ignored": ignored},
    })


async def _handle_page_snapshot(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    try:
        payload = AgentPageSnapshotPayload.model_validate(message.get("payload") or {})
    except Exception:
        raw_payload = message.get("payload") or {}
        agent_task_id = str(raw_payload.get("agent_task_id", ""))
        await ctx.websocket.send_json({
            "id": f"err_{message.get('id')}",
            "type": "server.error",
            "payload": {"agent_task_id": agent_task_id, "reason": "invalid_payload"},
        })
        return
    agent_task_id = str(payload.agent_task_id)

    # Parse snapshot for validation
    snapshot = AgentPageSnapshot.model_validate(payload.snapshot)

    existing_item: CrawlerAgentWorkItem | None = ctx.db.get(
        CrawlerAgentWorkItem, payload.agent_task_id
    )
    ignored = (
        existing_item is None
        or existing_item.assigned_agent_id != uuid.UUID(str(ctx.agent.id))
        or existing_item.attempt != payload.attempt
        or existing_item.status not in {"pending", "assigned", "running"}
    )

    # Cookie sync from snapshot payload
    if payload.cookies:
        cookies = [AgentCookie.model_validate(c) for c in payload.cookies]
        sync_javdb_cookies(cookies)
        ctx.agent.last_cookie_sync_at = datetime.now(UTC)

    if not ignored:
        try:
            _, ignored = complete_work_item_from_snapshot(
                ctx.db,
                work_item_id=agent_task_id,
                agent_id=str(ctx.agent.id),
                attempt=payload.attempt,
                snapshot=snapshot,
            )
        except Exception as exc:
            ctx.agent.last_seen_at = datetime.now(UTC)
            ctx.agent.status = "online"
            ctx.db.commit()
            await ctx.websocket.send_json({
                "id": f"ack_{message.get('id')}",
                "type": "server.ack",
                "payload": {
                    "message_id": message.get("id"),
                    "agent_task_id": agent_task_id,
                    "accepted": False,
                    "ignored": False,
                    "error_reason": agent_error_message(str(exc)),
                },
            })
            return

    ctx.agent.status = "online"
    ctx.agent.last_seen_at = datetime.now(UTC)
    ctx.db.commit()

    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {
            "agent_task_id": agent_task_id,
            "ignored": ignored,
        },
    })


async def _handle_diagnostics_batch(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    payload = AgentDiagnosticBatchPayload.model_validate(message.get("payload") or {})
    events: list[CrawlerAgentEvent] = []
    for event in payload.events:
        try:
            ev = add_agent_event(
                ctx.db,
                owner_id=uuid.UUID(str(ctx.agent.owner_id)),
                agent_id=uuid.UUID(str(ctx.agent.id)),
                source=event.get("source", "agent"),
                event_type=event.get("event_type", "diagnostic"),
                level=event.get("level", "info"),
                message=event.get("message", ""),
                retention_class=event.get("retention_class", "operational"),
                run_id=(
                    uuid.UUID(event["run_id"])
                    if event.get("run_id")
                    else None
                ),
                work_item_id=(
                    uuid.UUID(event["work_item_id"])
                    if event.get("work_item_id")
                    else None
                ),
                attempt=event.get("attempt"),
                phase=event.get("phase"),
                details=event.get("details"),
            )
            events.append(ev)
        except Exception:
            pass
    if events:
        commit_and_publish_agent_events(ctx.db, events)
    else:
        ctx.db.commit()

    ctx.agent.last_seen_at = datetime.now(UTC)
    ctx.db.commit()

    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {"message_id": message.get("id"), "accepted": len(events)},
    })


async def _handle_cookie_sync(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    payload = message.get("payload") or {}
    cookies = [
        AgentCookie.model_validate(c)
        for c in payload.get("cookies", [])
    ]
    result = sync_javdb_cookies(cookies)
    ctx.agent.last_cookie_sync_at = datetime.now(UTC)
    ctx.agent.last_seen_at = datetime.now(UTC)
    ctx.db.commit()
    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {
            "message_id": message.get("id"),
            "accepted": result.accepted,
            "rejected": result.rejected,
            "cookie_names": result.cookie_names,
        },
    })


async def _handle_heartbeat(ctx: AgentProtocolContext, message: dict[str, Any]) -> None:
    ctx.registry.touch(str(ctx.agent.id))
    ctx.agent.last_seen_at = datetime.now(UTC)
    ctx.db.commit()
    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {"message_id": message.get("id")},
    })


_HANDLERS: dict[str, Any] = {
    "agent.task_request": _handle_task_request,
    "agent.task_event": _handle_task_event,
    "agent.task_failed": _handle_task_failed,
    "agent.page_snapshot": _handle_page_snapshot,
    "agent.diagnostics_batch": _handle_diagnostics_batch,
    "agent.cookie_sync": _handle_cookie_sync,
    "agent.heartbeat": _handle_heartbeat,
}
