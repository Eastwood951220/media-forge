from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from fastapi import WebSocket


@dataclass
class AgentConnection:
    agent_id: str
    owner_id: str
    websocket: WebSocket
    generation: str
    connected_at: datetime
    last_seen_at: datetime
    ready: bool = False
    protocol_version: int | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    loop: asyncio.AbstractEventLoop | None = None


class AgentConnectionRegistry:
    """A generation-safe registry for agent WebSocket connections.

    Each connection carries a unique ``generation`` UUID hex string.
    ``connect()`` returns the replaced connection (or ``None``), and
    ``disconnect_if_current()`` only removes the entry when the caller
    provides the current generation — so an old-connection disconnect
    after a reconnect is a safe no-op.

    Uses ``threading.RLock`` so synchronous workers can also query
    readiness (e.g. ``has_ready_owner()``) while the async router holds
    the same lock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._connections: dict[str, AgentConnection] = {}

    def connect(
        self, *, agent_id: str, owner_id: str, websocket: WebSocket
    ) -> tuple[AgentConnection, AgentConnection | None]:
        """Register a new connection, returning ``(connection, replaced)``.

        If an older connection for ``agent_id`` exists it is returned as
        ``replaced`` — the caller should close the old WebSocket.
        """
        connection = AgentConnection(
            agent_id=agent_id,
            owner_id=owner_id,
            websocket=websocket,
            generation=uuid.uuid4().hex,
            connected_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
        try:
            connection.loop = asyncio.get_running_loop()
        except RuntimeError:
            # Sync test/worker context: keep loop None and allow direct sends
            # from whichever loop invokes send_to_ready_owner().
            pass
        with self._lock:
            replaced = self._connections.get(agent_id)
            self._connections[agent_id] = connection
        return connection, replaced

    def current(self, agent_id: str) -> AgentConnection | None:
        """Return the current connection for ``agent_id`` or ``None``."""
        with self._lock:
            return self._connections.get(agent_id)

    def disconnect_if_current(self, agent_id: str, generation: str) -> AgentConnection | None:
        """Remove and return the connection only when its generation matches.

        Returns ``None`` when there is no connection or the generation
        is stale — a safe no-op for old-connection disconnect calls after
        a reconnect has already replaced the entry.
        """
        with self._lock:
            current = self._connections.get(agent_id)
            if current is None or current.generation != generation:
                return None
            return self._connections.pop(agent_id)

    def touch(self, agent_id: str) -> None:
        """Update ``last_seen_at`` for the current connection."""
        with self._lock:
            connection = self._connections.get(agent_id)
            if connection is not None:
                connection.last_seen_at = datetime.now(UTC)

    def mark_ready(
        self,
        agent_id: str,
        generation: str,
        *,
        protocol_version: int,
        capabilities: set[str] = frozenset(),
    ) -> bool:
        """Mark a connection as ready if the generation still matches.

        Returns ``True`` when the connection was marked ready, ``False``
        when the generation is stale (replaced connection).
        """
        with self._lock:
            connection = self._connections.get(agent_id)
            if connection is None or connection.generation != generation:
                return False
            connection.ready = True
            connection.protocol_version = protocol_version
            connection.capabilities = frozenset(capabilities)
            return True

    def has_ready_owner(self, owner_id: str) -> bool:
        """Return ``True`` when the owner has at least one ready connection."""
        with self._lock:
            return any(
                conn.ready and conn.owner_id == owner_id
                for conn in self._connections.values()
            )

    async def send(
        self, agent_id: str, message_type: str, payload: dict[str, Any]
    ) -> None:
        """Send a JSON message on the current connection for ``agent_id``."""
        with self._lock:
            connection = self._connections.get(agent_id)
        if connection is not None:
            await connection.websocket.send_json({
                "id": f"srv_{uuid.uuid4().hex}",
                "type": message_type,
                "payload": payload,
            })

    async def send_to_ready_owner(
        self, owner_id: str, message_type: str, payload: dict[str, Any]
    ) -> bool:
        """Send a JSON message to one ready connection for an owner.

        Returns ``False`` when the owner has no ready connection. When the
        caller runs in a different event loop than the one the connection was
        created on (e.g. a crawler worker thread), the send is bridged back to
        the connection's own loop with ``run_coroutine_threadsafe``.
        """
        with self._lock:
            connection = next(
                (
                    conn
                    for conn in self._connections.values()
                    if conn.ready and conn.owner_id == owner_id
                ),
                None,
            )
        if connection is None:
            return False
        message = {
            "id": f"srv_{uuid.uuid4().hex}",
            "type": message_type,
            "payload": payload,
        }
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        loop = connection.loop
        if loop is not None and running_loop is not None and loop is not running_loop:
            future = asyncio.run_coroutine_threadsafe(
                connection.websocket.send_json(message), loop
            )
            await asyncio.wrap_future(future)
        else:
            await connection.websocket.send_json(message)
        return True


agent_registry = AgentConnectionRegistry()