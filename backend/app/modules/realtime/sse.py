from __future__ import annotations

import json

from backend.app.modules.realtime.schemas import RealtimeEvent


def format_sse_event(event: RealtimeEvent) -> str:
    data = event.model_dump(mode="json")
    return (
        f"id: {event.id}\n"
        f"event: {event.event}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def format_sse_comment(comment: str) -> str:
    return f": {comment}\n\n"
