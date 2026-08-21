from __future__ import annotations

import uuid
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
    status: Literal["not_configured", "offline", "online", "busy", "error", "upgrade_required"]
    agent_id: str | None = None
    name: str | None = None
    protocol_version: int | None = None
    connected_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_cookie_sync_at: datetime | None = None
    version: str | None = None
    current_work_item: dict[str, Any] | None = None
    pending_count: int = 0
    active_count: int = 0


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


# ── Protocol 2 message schemas ──────────────────────────────────────────────

class AgentHelloPayload(BaseModel):
    protocol_version: int
    version: str = Field(max_length=50)
    capabilities: set[str] = Field(default_factory=set)


class AgentEnvelope(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentTaskEventPayload(BaseModel):
    agent_task_id: uuid.UUID
    attempt: int = Field(ge=1)
    phase: str = Field(min_length=1, max_length=100)
    level: Literal["info", "warning", "error"] = "info"
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)


class AgentTaskFailedPayload(BaseModel):
    agent_task_id: uuid.UUID
    attempt: int = Field(ge=1)
    phase: str = Field(min_length=1, max_length=100)
    code: Literal[
        "agent_tab_create_failed",
        "agent_page_load_failed",
        "agent_detail_dom_not_ready",
        "agent_content_script_unavailable",
        "agent_snapshot_failed",
    ]
    message: str = Field(min_length=1, max_length=500)


class AgentPageSnapshotPayload(BaseModel):
    agent_task_id: uuid.UUID
    attempt: int = Field(ge=1)
    snapshot: dict[str, Any]
    cookies: list[dict[str, Any]] = Field(default_factory=list)


class AgentDiagnosticBatchPayload(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
