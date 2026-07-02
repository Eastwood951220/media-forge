from __future__ import annotations

from pathlib import Path
from typing import Any

from scraper.config.settings import RUN_DATA_DIR
from shared.logging.jsonl import append_jsonl_log, build_log_entry, delete_jsonl_logs, load_jsonl_logs

RUN_LOG_DIR = str(RUN_DATA_DIR / "logs" / "crawler" / "runs")


def run_log_filename(run_id: str) -> str:
    return f"{run_id}.jsonl"


def build_run_log(level: str, message: str, **context: Any) -> dict[str, Any]:
    return build_log_entry(
        level=level,
        component="crawler.run",
        event="run_log",
        message=message,
        **context,
    )


def append_run_log(run_id: str, entry: dict[str, Any]) -> None:
    append_jsonl_log(RUN_LOG_DIR, run_log_filename(run_id), entry)


def load_run_logs(run_id: str) -> list[dict[str, Any]]:
    return load_jsonl_logs(RUN_LOG_DIR, run_log_filename(run_id))


def delete_run_logs(run_id: str) -> bool:
    path = Path(RUN_LOG_DIR) / run_log_filename(run_id)
    existed = path.exists()
    delete_jsonl_logs(RUN_LOG_DIR, run_log_filename(run_id))
    return existed
