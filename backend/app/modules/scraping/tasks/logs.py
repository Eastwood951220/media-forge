from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _log_path(item_id: str) -> Path:
    root = Path(os.getenv("APP_DATA_DIR", "data")) / "logs/scraping/tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{item_id}.jsonl"


def write_scraping_item_log(
    item_id: str,
    level: str,
    message: str,
    *,
    step: str | None = None,
    context: dict | None = None,
) -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "context": context or {},
    }
    if step:
        entry["step"] = step
    with _log_path(item_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_scraping_item_logs(item_id: str) -> list[dict]:
    entries: list[dict] = []
    try:
        with _log_path(item_id).open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    except OSError:
        return []
    return entries
