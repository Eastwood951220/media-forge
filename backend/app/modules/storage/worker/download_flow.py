from __future__ import annotations

import time
from dataclasses import dataclass

from backend.app.modules.storage.worker.download import (
    is_submit_task_exists_error,
    poll_downloaded_video_files,
    recover_existing_downloaded_video_files,
)
from backend.app.modules.storage.worker.target_files import ensure_directory_chain


@dataclass
class DownloadFlowResult:
    found_files: list[dict]
    submit_task_exists: bool


def run_download_flow(context, magnet: dict, download_folder: str, download_root: str) -> DownloadFlowResult | None:
    provider = context.provider
    subtask = context.subtask
    magnet_url = magnet.get("magnet_url", "")
    context.set_step("submit_magnet")
    submit_task_exists = False
    try:
        context.log(
            "INFO",
            "准备提交磁力到 CloudDrive2",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder},
            step="submit_magnet",
        )
        ensure_directory_chain(provider, download_folder)
        result = provider.submit_offline_download(magnet_url, download_folder)
        context.log(
            "INFO",
            "磁力链接已提交",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder, "result_paths": getattr(result, "result_paths", [])},
            step="submit_magnet",
        )
        initial_wait = float(context.config.get("download_initial_wait_seconds", 60.0) or 0)
        if initial_wait > 0:
            context.log(
                "INFO",
                f"提交后等待 {initial_wait:g} 秒再首次查找视频",
                {"wait_seconds": initial_wait, "magnet_id": magnet.get("id"), "download_folder": download_folder},
                step="waiting_download",
            )
            time.sleep(initial_wait)
    except Exception as exc:
        if not is_submit_task_exists_error(exc):
            context.log("ERROR", f"提交磁力失败: {exc}", {"magnet_id": magnet.get("id")}, step="submit_magnet")
            return None
        submit_task_exists = True
        context.log("WARNING", "磁力链接已存在 (code 10008)，搜索现有下载中", {"magnet_id": magnet.get("id")}, step="submit_magnet")

    context.set_step("waiting_download")
    search_terms = [subtask.movie_code]
    if submit_task_exists:
        found_files = recover_existing_downloaded_video_files(
            context,
            search_terms=search_terms,
            task_download_folder=download_folder,
            download_root=download_root,
        )
    else:
        found_files = poll_downloaded_video_files(
            context,
            search_terms=search_terms,
            task_download_folder=download_folder,
            download_root=download_root,
        )
    return DownloadFlowResult(found_files=found_files, submit_task_exists=submit_task_exists)
