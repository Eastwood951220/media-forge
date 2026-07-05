from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def _log_path(subtask_id: str) -> Path:
    root = Path(os.getenv("APP_DATA_DIR", "data")) / "logs/storage/tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{subtask_id}.jsonl"


def write_storage_subtask_log(
    subtask_id: str,
    level: str,
    message: str,
    context: dict | None = None,
    *,
    step: str | None = None,
    step_label: str | None = None,
    event: str | None = None,
) -> dict:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "context": context or {},
    }
    if step:
        entry["step"] = step
    if step_label:
        entry["step_label"] = step_label
    if event:
        entry["event"] = event
    with _log_path(subtask_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_storage_subtask_logs(subtask_id: str) -> list[dict]:
    path = _log_path(subtask_id)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def delete_storage_subtask_log(subtask_id: str) -> bool:
    path = _log_path(subtask_id)
    if not path.exists():
        return False
    path.unlink()
    return True
