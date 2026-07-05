from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass
class DownloadDiscoveryResult:
    found_files: list[dict]
    submit_task_exists: bool = False


def _log_search_result(context, result) -> None:
    context.log("INFO", "查找下载文件", result.log_context, step="waiting_download")


def is_submit_task_exists_error(error: Exception | str) -> bool:
    message = str(error)
    return "10008" in message or "任务已存在" in message


def recover_existing_downloaded_video_files(context, search_terms: list[str], task_download_folder: str, download_root: str) -> list[dict]:
    from backend.app.modules.storage.worker.file_finder import find_recovery_video_files

    movie_code = getattr(context.subtask, "movie_code", search_terms[0] if search_terms else "")
    result = find_recovery_video_files(
        provider=context.provider,
        search_terms=search_terms,
        task_download_folder=task_download_folder,
        download_root=download_root,
        movie_code=movie_code,
        config=context.config,
    )
    result.log_context["recovery_reason"] = "submit_task_exists"
    _log_search_result(context, result)
    return result.accepted_files


def poll_downloaded_video_files(context, search_terms: list[str], task_download_folder: str, download_root: str) -> list[dict]:
    from backend.app.modules.storage.worker.file_finder import find_listed_video_files

    config = context.config
    movie_code = getattr(context.subtask, "movie_code", search_terms[0] if search_terms else "")
    max_poll_count = int(config.get("download_max_poll_count", 10) or 10)
    poll_min = float(config.get("download_poll_interval_min", 5.0) or 0)
    poll_max = float(config.get("download_poll_interval_max", poll_min) or poll_min)
    if poll_max < poll_min:
        poll_max = poll_min

    for poll_index in range(1, max_poll_count + 1):
        result = find_listed_video_files(
            provider=context.provider,
            search_path=task_download_folder,
            search_scope="task_download_folder",
            movie_code=movie_code,
            task_download_folder=task_download_folder,
            config=config,
        )
        result.log_context["poll_index"] = poll_index
        result.log_context["max_poll_count"] = max_poll_count
        _log_search_result(context, result)
        if result.accepted_files:
            return result.accepted_files

        context.log(
            "INFO",
            f"轮询 #{poll_index}: 任务下载目录未发现可用视频文件，等待中",
            {"poll_index": poll_index, "max_poll_count": max_poll_count, "search_path": task_download_folder},
            step="waiting_download",
        )
        if poll_index < max_poll_count:
            time.sleep(random.uniform(poll_min, poll_max))

    context.log(
        "WARNING",
        f"轮询次数超过上限: {max_poll_count}/{max_poll_count}，任务目录未发现可用视频文件，跳过当前磁力",
        {"max_poll_count": max_poll_count, "task_download_folder": task_download_folder},
        step="waiting_download",
    )
    return []
