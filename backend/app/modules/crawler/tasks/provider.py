from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def open_delete_provider(mode: str) -> Iterator[object | None]:
    """Yield a cloud storage provider when *mode* requires one.

    For ``task_movies_and_cloud`` the provider is created from the current
    storage configuration.  For all other modes ``None`` is yielded so
    callers can use a single ``with`` block regardless of mode.
    """
    if mode != "task_movies_and_cloud":
        yield None
        return

    from backend.app.modules.storage.config.service import StorageConfigService

    config_service = StorageConfigService()
    config = config_service.get_raw_config()
    client = config_service.provider_factory.create(config)
    provider = config_service.gateway_class(client)
    try:
        yield provider
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
