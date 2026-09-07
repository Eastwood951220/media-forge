from __future__ import annotations

from pathlib import PurePosixPath


def storage_task_root_from_attempt(task_download_folder: str) -> str:
    normalized = str(PurePosixPath(task_download_folder))
    path = PurePosixPath(normalized)
    if path.name.startswith("attempt_"):
        return str(path.parent)
    return normalized


def normalize_storage_operation_path(path: str, config: dict) -> str:
    if not path:
        return ""
    normalized = str(PurePosixPath(path))
    for root_key in ("download_root_folder", "target_folder"):
        root = str(config.get(root_key) or "")
        if not root or root == "/":
            continue
        marker = str(PurePosixPath(root))
        index = normalized.find(marker)
        end_index = index + len(marker)
        if index > 0 and (end_index == len(normalized) or normalized[end_index] == "/"):
            return normalized[index:]
    return normalized
