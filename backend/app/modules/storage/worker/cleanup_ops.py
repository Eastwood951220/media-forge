from __future__ import annotations


def cleanup_download_folder(context, download_folder: str, config: dict) -> None:
    if download_folder and config.get("use_task_subfolder", True):
        try:
            context.provider.delete_file(download_folder)
            context.log("INFO", f"已清理下载目录: {download_folder}", step="cleanup_files")
        except Exception as exc:
            context.log("WARNING", f"清理下载目录失败 (非致命): {exc}", step="cleanup_files")
    context.log("INFO", "清理完成", step="cleanup_files")
