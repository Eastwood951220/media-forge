from __future__ import annotations

import random
import time
from dataclasses import dataclass

from backend.app.modules.storage.worker.file_finder import find_listed_video_files


@dataclass
class DownloadDiscoveryResult:
    found_files: list[dict]
    submit_task_exists: bool = False


def _log_search_result(context, result) -> None:
    context.log("INFO", "查找下载文件", result.log_context, step="waiting_download")


def _accepted_files_signature(files: list[dict]) -> tuple[tuple[str, str, int], ...]:
    return tuple(
        sorted(
            (
                str(file.get("path") or ""),
                str(file.get("name") or ""),
                int(file.get("size") or 0),
            )
            for file in files
        )
    )


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
    config = context.config
    movie_code = getattr(context.subtask, "movie_code", search_terms[0] if search_terms else "")
    max_poll_count = int(config.get("download_max_poll_count", 10) or 10)
    poll_min = float(config.get("download_poll_interval_min", 5.0) or 0)
    poll_max = float(config.get("download_poll_interval_max", poll_min) or poll_min)
    if poll_max < poll_min:
        poll_max = poll_min

    last_signature: tuple[tuple[str, str, int], ...] | None = None

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
            signature = _accepted_files_signature(result.accepted_files)
            if signature == last_signature:
                context.log(
                    "INFO",
                    f"文件列表已稳定: {len(result.accepted_files)} 个视频",
                    {"poll_index": poll_index, "file_count": len(result.accepted_files)},
                    step="waiting_download",
                )
                return result.accepted_files

            last_signature = signature
            context.log(
                "INFO",
                f"检测到 {len(result.accepted_files)} 个候选视频，等待文件列表稳定",
                {"poll_index": poll_index, "file_count": len(result.accepted_files)},
                step="waiting_download",
            )
        else:
            last_signature = None
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
