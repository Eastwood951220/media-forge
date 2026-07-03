"""SSE streaming endpoint for crawler real-time events.

Clients connect to ``GET /api/crawler/stream?token=<jwt>`` and receive
a continuous stream of ``CrawlerEvent`` objects encoded as SSE ``data:``
frames.

Authentication uses a query-parameter token because the browser
``EventSource`` API does not support custom headers.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter

from backend.app.core.security import decode_access_token
from backend.app.modules.crawler.events.bus import event_bus
from backend.app.modules.crawler.events.schemas import CrawlerEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["crawler-events"])

# TypeAdapter for serializing discriminated union
_event_adapter = TypeAdapter(CrawlerEvent)

# Reconnection gap recommended to clients (ms)
RECONNECT_MS = 3_000


@router.get("/api/crawler/stream")
async def stream_crawler_events(
    token: str = Query(..., description="JWT access token"),
) -> StreamingResponse:
    """Stream crawler events as Server-Sent Events.

    The client must pass its JWT in the ``token`` query parameter.
    The connection stays open until the client disconnects or the
    server sends a ``close`` control frame.
    """
    # -- Validate token --
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    # -- Subscribe to event bus --
    client_id, queue = event_bus.subscribe()

    async def event_generator():
        """Yield SSE-formatted messages until client disconnects."""
        try:
            # Send initial retry hint
            yield f"retry: {RECONNECT_MS}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send heartbeat to detect stale connections
                    yield ": heartbeat\n\n"
                    continue

                if event is None:
                    # Control signal: close the stream
                    break

                # Serialize event to JSON
                data = _event_adapter.dump_json(event).decode("utf-8")
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            logger.debug("SSE stream cancelled for client %s", client_id)
        finally:
            event_bus.unsubscribe(client_id, queue)
            logger.debug("SSE stream closed for client %s", client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
