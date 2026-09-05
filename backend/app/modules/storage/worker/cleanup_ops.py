from __future__ import annotations

from pathlib import PurePosixPath


def _storage_subtask_folder(download_folder: str, download_root: str) -> str | None:
    folder = PurePosixPath(download_folder)
    root = PurePosixPath(download_root or "/Downloads")
    if folder == root:
        return None
    if folder.parent == root and folder.name.startswith("storage_"):
        return str(folder)
    if folder.parent.name.startswith("storage_") and folder.parent.parent == root:
        return str(folder.parent)
    return str(folder)


def cleanup_download_folder(context, download_folder: str, config: dict) -> None:
    if download_folder and config.get("use_task_subfolder", True):
        cleanup_folder = _storage_subtask_folder(
            download_folder,
            str(config.get("download_root_folder") or "/Downloads"),
        )
        if not cleanup_folder:
            context.log("INFO", "清理完成", step="cleanup_files")
            return
        try:
            context.provider.delete_file(cleanup_folder)
            context.log("INFO", f"已清理下载目录: {cleanup_folder}", step="cleanup_files")
        except Exception as exc:
            context.log("WARNING", f"清理下载目录失败 (非致命): {exc}", step="cleanup_files")
    context.log("INFO", "清理完成", step="cleanup_files")
