"""SSE event schemas for crawler real-time streaming.

Uses Pydantic v2 discriminated unions for type-safe event serialization.
All events include a ``type`` literal tag so the frontend can narrow types.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ---- Base ----


class CrawlerEventBase(BaseModel):
    """Common fields shared by every crawler SSE event."""

    timestamp: datetime = Field(default_factory=datetime.now)


# ---- Run events ----


class RunStatusEvent(CrawlerEventBase):
    """Emitted when a crawl run changes status (running / completed / failed / stopped)."""

    type: Literal["run:status"] = "run:status"
    run_id: str
    status: str
    task_name: str = ""
    error: str | None = None


class RunProgressEvent(CrawlerEventBase):
    """Emitted on every progress tick during a crawl run."""

    type: Literal["run:progress"] = "run:progress"
    run_id: str
    total: int = 0
    saved: int = 0
    failed: int = 0
    skipped: int = 0
    save_failed: int = 0


class RunLogEvent(CrawlerEventBase):
    """Emitted for each log entry produced by a crawl run."""

    type: Literal["run:log"] = "run:log"
    run_id: str
    level: str = "INFO"
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


# ---- Task events ----


class TaskStatusEvent(CrawlerEventBase):
    """Emitted when an individual detail task changes status."""

    type: Literal["task:status"] = "task:status"
    run_id: str
    code: str | None = None
    source_url: str = ""
    status: str
    error: str | None = None


# ---- Discriminated union ----

CrawlerEvent = Annotated[
    Union[RunStatusEvent, RunProgressEvent, RunLogEvent, TaskStatusEvent],
    Field(discriminator="type"),
]
