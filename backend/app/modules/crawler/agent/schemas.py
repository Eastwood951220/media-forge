from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentEventResponse(BaseModel):
    """Matching serialize_agent_event() — exposes details as `details` field."""

    id: str
    owner_id: str
    agent_id: str | None = None
    run_id: str | None = None
    work_item_id: str | None = None
    attempt: int | None = None
    source: str
    event_type: str
    phase: str | None = None
    level: str
    message: str
    details: dict[str, Any] | None = None
    retention_class: str
    created_at: str | None = None


class AgentEventPageResponse(BaseModel):
    rows: list[AgentEventResponse]
    next_cursor: str | None = None
    has_more: bool = False


class AgentStatusResponse(BaseModel):
    status: Literal["not_configured", "offline", "online", "busy", "error"]
    agent_id: str | None = None
    name: str | None = None
    last_seen_at: datetime | None = None
    last_cookie_sync_at: datetime | None = None
    version: str | None = None


class AgentTokenRotateResponse(BaseModel):
    token: str
    status: AgentStatusResponse


class AgentSessionCreateRequest(BaseModel):
    token: str
    version: str | None = None
    name: str | None = None


class AgentSessionCreateResponse(BaseModel):
    session: str
    expires_at: datetime


class AgentMessage(BaseModel):
    id: str
    type: str
    sent_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ServerMessage(BaseModel):
    id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
