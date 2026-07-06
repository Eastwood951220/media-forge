from __future__ import annotations

from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState

ProgressState = dict[str, int]


def new_progress() -> ProgressState:
    return {"total": 0, "saved": 0, "failed": 0, "skipped": 0, "save_failed": 0}


def increment_progress(progress: ProgressState, key: str, amount: int = 1) -> None:
    progress[key] = int(progress.get(key, 0)) + amount


def write_progress(runtime: CrawlerRuntimeState, run_id: str, progress: ProgressState) -> None:
    runtime.write_progress(run_id, progress)
