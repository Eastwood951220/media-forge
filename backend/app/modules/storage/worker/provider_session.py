from __future__ import annotations

from datetime import datetime, timezone

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log


def open_storage_provider(provider_factory, config: dict):
    from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway

    client = provider_factory.create(config)
    return client, CloudDrive2Gateway(client)


def close_storage_provider(client) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def mark_provider_creation_failed(subtask, main_task_id: str, error: Exception) -> None:
    subtask.status = "failed"
    subtask.error_message = f"创建 CloudDrive2 客户端失败: {error}"
    subtask.finished_at = datetime.now(timezone.utc)
    write_storage_subtask_log(
        str(subtask.id),
        "ERROR",
        f"创建 CloudDrive2 客户端失败: {error}",
        {"main_task_id": main_task_id},
    )
