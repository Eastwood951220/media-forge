from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket


@dataclass
class AgentConnection:
    agent_id: str
    owner_id: str
    websocket: WebSocket
    connected_at: datetime
    last_seen_at: datetime


class AgentConnectionRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connections: dict[str, AgentConnection] = {}

    async def connect(self, *, agent_id: str, owner_id: str, websocket: WebSocket) -> AgentConnection:
        connection = AgentConnection(
            agent_id=agent_id,
            owner_id=owner_id,
            websocket=websocket,
            connected_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
        async with self._lock:
            self._connections[agent_id] = connection
        return connection

    async def disconnect(self, agent_id: str) -> None:
        async with self._lock:
            self._connections.pop(agent_id, None)

    async def touch(self, agent_id: str) -> None:
        async with self._lock:
            connection = self._connections.get(agent_id)
            if connection:
                connection.last_seen_at = datetime.now(UTC)

    async def send(self, agent_id: str, message_type: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            connection = self._connections.get(agent_id)
        if connection:
            await connection.websocket.send_json({
                "id": f"srv_{uuid.uuid4().hex}",
                "type": message_type,
                "payload": payload,
            })


agent_registry = AgentConnectionRegistry()
