from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from backend.app.models.crawler_agent import CrawlerAgent
from backend.app.modules.crawler.agent.constants import (
    AGENT_MINIMUM_PROTOCOL_VERSION,
    AGENT_REQUIRED_CAPABILITIES,
)
from backend.app.modules.crawler.agent.registry import AgentConnection, AgentConnectionRegistry
from backend.app.modules.crawler.agent.schemas import AgentHelloPayload


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
    ctx.agent.version = payload.version or ctx.agent.version
    ctx.agent.last_seen_at = datetime.now(UTC)
    ctx.db.commit()
    await ctx.websocket.send_json({
        "id": f"ack_{message.get('id')}",
        "type": "server.ack",
        "payload": {"message_id": message.get("id")},
    })
    return True