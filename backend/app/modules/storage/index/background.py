from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.index.refresh import StorageIndexRefreshService
from backend.app.modules.storage.index.store import StorageIndexStore

logger = logging.getLogger(__name__)

_refresh_lock = threading.Lock()
_refresh_running = False


class StorageIndexAlreadyRunningError(RuntimeError):
    pass


def _set_running(value: bool) -> None:
    global _refresh_running
    with _refresh_lock:
        _refresh_running = value


def start_storage_index_refresh(
    mode: str,
    service_factory: Callable[[], StorageConfigService],
) -> dict:
    global _refresh_running
    with _refresh_lock:
        metadata = StorageIndexStore().read_metadata()
        if _refresh_running or metadata.status == "running":
            raise StorageIndexAlreadyRunningError("存储索引任务正在进行中")
        _refresh_running = True

    thread = threading.Thread(
        target=_run_refresh,
        args=(mode, service_factory),
        daemon=True,
        name=f"storage-index-refresh-{mode}",
    )
    thread.start()
    return {
        "started": True,
        "mode": mode,
        "status": "running",
        "message": "存储索引任务启动成功",
    }


def _run_refresh(mode: str, service_factory: Callable[[], StorageConfigService]) -> None:
    try:
        service = service_factory()
        with service.open_provider() as (config, provider):
            StorageIndexRefreshService().refresh(config, provider, mode=mode)
    except Exception:
        logger.exception("Storage index refresh failed")
    finally:
        _set_running(False)
