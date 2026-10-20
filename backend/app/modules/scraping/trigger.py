from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.scraping.config import ScrapingConfigService, validate_run_config
from backend.app.modules.scraping.strm import run_strm_generation
from shared.database.session import get_session_factory

logger = logging.getLogger(__name__)

PENDING_STATUSES = ("queued", "running", "stopping")

_generation_lock = threading.Lock()
_generation = 0


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _next_generation() -> int:
    global _generation
    with _generation_lock:
        _generation += 1
        return _generation


def _is_current_generation(generation: int) -> bool:
    with _generation_lock:
        return generation == _generation


def _is_storage_idle(runtime: Any, is_worker_idle: Callable[[], bool]) -> bool:
    if not is_worker_idle():
        return False
    try:
        if runtime.pending_main_task_count() > 0:
            return False
    except Exception:
        logger.warning(
            "Cannot confirm the storage queue is empty; skipping STRM generation",
            exc_info=True,
        )
        return False
    try:
        factory = get_session_factory()
        with factory() as session:
            pending = (
                session.query(StorageMainTask.id)
                .filter(StorageMainTask.status.in_(PENDING_STATUSES))
                .first()
            )
        return pending is None
    except Exception:
        logger.warning(
            "Cannot confirm storage tasks are idle; skipping STRM generation",
            exc_info=True,
        )
        return False


def _run_after_delay(
    generation: int,
    delay_seconds: int,
    runtime: Any,
    is_worker_idle: Callable[[], bool],
) -> None:
    try:
        _sleep(delay_seconds)
        if not _is_current_generation(generation):
            logger.info("Skipping STRM generation: a newer storage drain scheduled it")
            return
        if not _is_storage_idle(runtime, is_worker_idle):
            logger.info("Skipping STRM generation: storage is still busy")
            return

        config = ScrapingConfigService().get_raw_config()
        reason = validate_run_config(config)
        if reason is not None:
            logger.info("Skipping STRM generation: %s", reason)
            return

        if not _is_current_generation(generation) or not is_worker_idle():
            logger.info("Skipping STRM generation: storage became busy during the final check")
            return

        result = run_strm_generation(config)
        if result.success:
            logger.info("STRM generation triggered: %s", result.message)
        else:
            logger.warning("STRM generation failed: %s", result.message)
    except Exception:
        logger.exception("STRM generation check failed")


def schedule_strm_after_storage_drain(
    runtime: Any,
    *,
    is_worker_idle: Callable[[], bool],
) -> None:
    try:
        config = ScrapingConfigService().get_raw_config()
        reason = validate_run_config(config)
        if reason is not None:
            logger.info("Not scheduling STRM generation: %s", reason)
            return

        generation = _next_generation()
        delay = int(config.get("trigger_delay_seconds") or 30)
        thread = threading.Thread(
            target=_run_after_delay,
            args=(generation, delay, runtime, is_worker_idle),
            daemon=True,
            name=f"strm-trigger-{generation}",
        )
        thread.start()
    except Exception:
        logger.exception("Failed to schedule STRM generation")
