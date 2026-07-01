"""Structured JSONL (JSON Lines) logging utilities."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def build_log_entry(
    level: str,
    component: str,
    event: str,
    message: str,
    **context: Any,
) -> dict[str, Any]:
    """Build a structured log entry dict."""
    return {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "level": level,
        "component": component,
        "event": event,
        "message": message,
        "context": context if context else {},
    }


def append_jsonl_log(log_dir: str, filename: str, entry: dict[str, Any]) -> None:
    """Append a log entry as a JSON line to a file."""
    path = Path(log_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def load_jsonl_logs(log_dir: str, filename: str) -> list[dict[str, Any]]:
    """Load all entries from a JSONL file."""
    path = Path(log_dir) / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def delete_jsonl_logs(log_dir: str, filename: str) -> None:
    """Delete a JSONL log file."""
    path = Path(log_dir) / filename
    if path.exists():
        os.remove(path)
