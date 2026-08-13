from __future__ import annotations

import asyncio
import uuid
from queue import Empty

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db, get_redis
from backend.app.core.security import decode_access_token
from backend.app.modules.crawler.tasks.runtime_status import build_task_runtime_snapshot_event
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.schemas import make_realtime_event
from backend.app.modules.realtime.sse import format_sse_comment, format_sse_event
from backend.app.repositories.user import UserRepository

router = APIRouter(prefix="/api/events", tags=["realtime-events"])

KEEPALIVE_SECONDS = 20
QUEUE_POLL_SECONDS = 0.5


def authenticate_stream_user(token: str | None, db: Session):
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = UserRepository(db).get_by_username(str(username))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


async def build_owner_event_stream(db: Session, owner_id: str):
    """Subscribe to the event bus and yield events, publishing a snapshot after system.connected.

    Args:
        db: Database session (used to build the initial snapshot).
        owner_id: The owner ID to subscribe for.

    Yields:
        Formatted SSE event strings.
    """
    queue = event_bus.subscribe(owner_id)
    last_keepalive = asyncio.get_running_loop().time()
    try:
        yield format_sse_event(
            make_realtime_event(
                event="system.connected",
                scope="system",
                owner_id=owner_id,
                payload={"message": "connected"},
            )
        )
        snapshot_event = build_task_runtime_snapshot_event(db, uuid.UUID(owner_id))
        yield format_sse_event(snapshot_event)
        while True:
            try:
                event = queue.get_nowait()
                yield format_sse_event(event)
                continue
            except Empty:
                pass

            now = asyncio.get_running_loop().time()
            if now - last_keepalive >= KEEPALIVE_SECONDS:
                last_keepalive = now
                yield format_sse_comment("keepalive")

            await asyncio.sleep(QUEUE_POLL_SECONDS)
    finally:
        event_bus.unsubscribe(owner_id, queue)


@router.get("/stream")
def event_stream(
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user = authenticate_stream_user(token, db)
    owner_id = str(user.id)

    event_bus.configure_redis(get_redis)

    return StreamingResponse(
        build_owner_event_stream(db, owner_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
