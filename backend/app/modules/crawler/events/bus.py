"""In-process EventBus for crawler SSE streaming.

Each connected client gets its own ``asyncio.Queue``.  Events published
via :meth:`EventBus.publish` are fanned-out to every subscribed queue.

Design notes
------------
- Module-level singleton ``event_bus`` — import and use directly.
- ``subscribe`` returns an ``asyncio.Queue``; caller reads from it.
- ``unsubscribe`` removes the queue; safe to call multiple times.
- ``publish`` is a regular ``def`` so sync runtime code can call it
  without awaiting (queues are thread-safe for simple ``put_nowait``).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from backend.app.modules.crawler.events.schemas import CrawlerEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Fan-out event bus backed by per-client asyncio queues."""

    def __init__(self) -> None:
        # client_id -> set of queues (a client may open multiple tabs)
        self._subscribers: dict[str, set[asyncio.Queue[CrawlerEvent | None]]] = {}

    # ---- Public API ----

    def subscribe(self, client_id: str | None = None) -> tuple[str, asyncio.Queue[CrawlerEvent | None]]:
        """Register a new client and return ``(client_id, queue)``.

        If *client_id* is ``None`` a random one is generated.
        """
        cid = client_id or uuid.uuid4().hex[:12]
        queue: asyncio.Queue[CrawlerEvent | None] = asyncio.Queue()
        self._subscribers.setdefault(cid, set()).add(queue)
        logger.debug("SSE client subscribed: %s (queues=%d)", cid, len(self._subscribers[cid]))
        return cid, queue

    def unsubscribe(self, client_id: str, queue: asyncio.Queue[CrawlerEvent | None]) -> None:
        """Remove a specific queue for *client_id*."""
        queues = self._subscribers.get(client_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self._subscribers.pop(client_id, None)
        logger.debug("SSE client unsubscribed: %s", client_id)

    def publish(self, event: CrawlerEvent) -> None:
        """Broadcast *event* to every subscribed queue (non-blocking).

        Silently drops the event for queues that are full (>1 000 items)
        to prevent a slow client from blocking the pipeline.
        """
        for client_id, queues in list(self._subscribers.items()):
            for queue in list(queues):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("SSE queue full for client %s, dropping event", client_id)

    @property
    def subscriber_count(self) -> int:
        """Total number of active client connections."""
        return sum(len(qs) for qs in self._subscribers.values())


# Module-level singleton
event_bus = EventBus()
