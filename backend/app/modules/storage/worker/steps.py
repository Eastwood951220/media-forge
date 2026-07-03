from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from pathlib import PurePosixPath

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log

logger = logging.getLogger(__name__)


def _subtask_log(context, level: str, message: str, extra: dict | None = None) -> None:
    subtask_id = getattr(context.subtask, "id", None)
    if subtask_id is None:
        return
    write_storage_subtask_log(str(subtask_id), level, message, extra or {})


def select_main_videos(files: list[dict], config: dict) -> list[dict]:
    extensions = {ext.lower() for ext in config.get("video_extensions", [])}
    minimum_size = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    videos = [
        file
        for file in files
        if PurePosixPath(file["name"]).suffix.lower() in extensions
        and int(file.get("size") or 0) >= minimum_size
    ]
    return sorted(videos, key=lambda file: (str(file["name"]).lower(), str(file["path"]).lower()))


def ensure_directory_chain(provider, folder_path: str) -> None:
    """Ensure all directories in the path exist."""
    provider.ensure_directory(folder_path)


def target_files_exist(provider, target_folder: str, filenames: list[str]) -> bool:
    """Check if all target files exist in the folder."""
    try:
        existing = provider.list_files(target_folder)
        existing_names = {getattr(f, "name", "") for f in existing}
        return all(name in existing_names for name in filenames)
    except Exception:
        return False


def poll_downloaded_video_files(context, search_terms: list[str], search_paths: list[str]) -> list[dict]:
    from backend.app.modules.storage.worker.file_finder import find_existing_video_files

    config = context.config
    max_poll_count = int(config.get("download_max_poll_count", 10) or 10)
    poll_min = float(config.get("download_poll_interval_min", 5.0) or 0)
    poll_max = float(config.get("download_poll_interval_max", poll_min) or poll_min)
    if poll_max < poll_min:
        poll_max = poll_min

    for poll_index in range(1, max_poll_count + 1):
        found_files = find_existing_video_files(context.provider, search_terms, search_paths, config)
        if found_files:
            _subtask_log(
                context,
                "INFO",
                "下载轮询发现可用视频文件",
                {
                    "poll_index": poll_index,
                    "max_poll_count": max_poll_count,
                    "file_count": len(found_files),
                    "search_paths": search_paths,
                },
            )
            return found_files

        _subtask_log(
            context,
            "INFO",
            "下载轮询未发现可用视频文件",
            {
                "poll_index": poll_index,
                "max_poll_count": max_poll_count,
                "search_paths": search_paths,
            },
        )
        if poll_index < max_poll_count:
            time.sleep(random.uniform(poll_min, poll_max))

    _subtask_log(
        context,
        "WARNING",
        "下载轮询达到最大次数，当前磁力失败",
        {
            "max_poll_count": max_poll_count,
            "search_paths": search_paths,
        },
    )
    return []


def execute_current_magnet_attempt(context, magnet: dict) -> bool:
    """Execute a single magnet download attempt. Returns True on success."""
    from backend.app.modules.storage.worker.file_finder import find_existing_video_files
    from backend.app.modules.storage.tasks.policies import build_video_filename

    subtask = context.subtask
    config = context.config
    provider = context.provider

    magnet_url = magnet.get("magnet_url", "")
    if not magnet_url:
        return False

    # Submit offline download
    download_root = config.get("download_root_folder", "/Downloads")
    download_folder = f"{download_root}/storage_{subtask.id}"

    try:
        _subtask_log(
            context,
            "INFO",
            "准备提交磁力到 CloudDrive2",
            {
                "magnet_id": magnet.get("id"),
                "download_folder": download_folder,
            },
        )
        ensure_directory_chain(provider, download_folder)
        result = provider.submit_offline_download(magnet_url, download_folder)
        _subtask_log(
            context,
            "INFO",
            "CloudDrive2 已接收磁力任务",
            {
                "magnet_id": magnet.get("id"),
                "download_folder": download_folder,
                "result_paths": getattr(result, "result_paths", []),
            },
        )
    except Exception as exc:
        logger.warning("Magnet download failed: %s", exc)
        _subtask_log(
            context,
            "ERROR",
            f"提交磁力失败: {exc}",
            {
                "magnet_id": magnet.get("id"),
                "download_folder": download_folder,
            },
        )
        return False

    if not result.success:
        logger.warning("Magnet download not successful: %s", result.error_message)
        _subtask_log(
            context,
            "WARNING",
            f"CloudDrive2 未接受磁力任务: {result.error_message}",
            {"magnet_id": magnet.get("id")},
        )
        return False

    # Wait for download and find files
    # In a real implementation, this would poll for download completion
    # For now, search for existing files
    search_terms = [subtask.movie_code]
    search_paths = [download_folder]

    found_files = poll_downloaded_video_files(context, search_terms, search_paths)
    if not found_files:
        _subtask_log(
            context,
            "WARNING",
            "未在下载目录找到可用视频文件",
            {"magnet_id": magnet.get("id"), "search_paths": search_paths},
        )
        return False

    # Select main videos
    main_videos = select_main_videos(found_files, config)
    if not main_videos:
        _subtask_log(
            context,
            "WARNING",
            "扫描到文件但未识别到主视频",
            {"magnet_id": magnet.get("id"), "file_count": len(found_files)},
        )
        return False

    # Build target filenames and move
    tags = magnet.get("tags", [])
    target_folder = config.get("target_folder", "/Movies")
    code_folder = build_video_filename(subtask.movie_code, main_videos[0]["name"], tags, 0, 1)
    from backend.app.modules.storage.tasks.policies import code_folder_from_filename
    code_dir = code_folder_from_filename(code_folder)
    final_folder = f"{target_folder}/{code_dir}"

    try:
        ensure_directory_chain(provider, final_folder)
    except Exception as exc:
        logger.warning("Failed to create target folder: %s", exc)
        return False

    # Move files
    renamed_files = []
    for i, video in enumerate(main_videos):
        new_name = build_video_filename(subtask.movie_code, video["name"], tags, i, len(main_videos))
        target_path = f"{final_folder}/{new_name}"
        try:
            provider.move_files([video["path"]], final_folder)
            renamed_files.append({"original": video["path"], "target": target_path})
        except Exception as exc:
            logger.warning("Failed to move file: %s", exc)
            _subtask_log(
                context,
                "ERROR",
                f"移动文件失败: {exc}",
                {"source": video["path"], "target_folder": final_folder},
            )
            return False

    subtask.renamed_files = renamed_files
    subtask.moved_files = renamed_files
    subtask.result = {"status": "success", "files": renamed_files}

    _subtask_log(
        context,
        "INFO",
        "磁力任务处理成功",
        {"magnet_id": magnet.get("id"), "files": renamed_files},
    )

    return True


def execute_subtask_pipeline(context) -> None:
    """Execute the full subtask pipeline."""
    from backend.app.modules.storage.tasks.policies import order_magnet_candidates

    subtask = context.subtask
    config = context.config

    subtask.status = "running"
    subtask.step = "prepare"
    subtask.started_at = datetime.now(timezone.utc)

    _subtask_log(context, "INFO", "存储子任务 pipeline 开始", {"movie_id": str(subtask.movie_id)})

    # Get magnets for this movie
    from shared.database.models.content import Movie
    movie = context.db.get(Movie, subtask.movie_id)
    if movie is None:
        subtask.status = "failed"
        subtask.error_message = "电影不存在"
        subtask.finished_at = datetime.now(timezone.utc)
        return

    magnets = [m for m in (movie.magnets or []) if m.magnet_url]
    if not magnets:
        subtask.status = "failed"
        subtask.error_message = "无可用磁力链接"
        subtask.finished_at = datetime.now(timezone.utc)
        return

    # Order magnets by priority
    max_attempts = config.get("magnet_max_attempts_per_subtask", 3)
    magnet_dicts = [
        {
            "id": str(m.id),
            "magnet_url": m.magnet_url,
            "tags": list(m.tags or []),
            "weight": m.weight,
            "selected": m.selected,
        }
        for m in magnets
    ]
    ordered = order_magnet_candidates(magnet_dicts, max_attempts)

    # Try each magnet
    for magnet in ordered:
        subtask.step = "cloud_download"
        subtask.current_magnet_id = magnet.get("id")
        subtask.current_magnet_url = magnet.get("magnet_url", "")

        _subtask_log(
            context,
            "INFO",
            "开始尝试磁力",
            {
                "magnet_id": magnet.get("id"),
                "weight": magnet.get("weight"),
                "selected": magnet.get("selected"),
            },
        )

        success = execute_current_magnet_attempt(context, magnet)

        _subtask_log(
            context,
            "INFO" if success else "WARNING",
            "磁力尝试完成" if success else "磁力尝试失败，准备尝试下一条",
            {"magnet_id": magnet.get("id"), "success": success},
        )

        attempt_record = {
            "magnet_id": magnet.get("id"),
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        attempts = list(subtask.magnet_attempts or [])
        attempts.append(attempt_record)
        subtask.magnet_attempts = attempts

        if success:
            subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            return

    # All magnets failed
    subtask.status = "failed"
    subtask.error_message = "所有磁力链接尝试均失败"
    subtask.finished_at = datetime.now(timezone.utc)
