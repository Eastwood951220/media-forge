from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class RealtimeEvent(BaseModel):
    id: str
    event: str
    scope: str
    resource_id: str | None = None
    owner_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


def make_realtime_event(
    *,
    event: str,
    scope: str,
    owner_id: str,
    resource_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RealtimeEvent:
    created_at = datetime.now(UTC)
    return RealtimeEvent(
        id=f"{created_at.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
        event=event,
        scope=scope,
        resource_id=resource_id,
        owner_id=owner_id,
        payload=payload or {},
        created_at=created_at,
    )


def realtime_event_to_json(event: RealtimeEvent) -> str:
    return event.model_dump_json()


def realtime_event_from_json(data: str | bytes) -> RealtimeEvent:
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return RealtimeEvent.model_validate_json(data)
