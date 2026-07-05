from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from pathlib import PurePosixPath

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.file_ops import (
    cleanup_download_folder,
    move_renamed_videos,
    rename_selected_videos,
    scan_found_files,
    verify_moved_files,
)
from backend.app.modules.storage.worker.target_files import (
    copy_existing_target_to_missing_targets,
    ensure_directory_chain,
    find_existing_target_files,
)
from backend.app.modules.storage.worker.timeline import classify_scanned_files

logger = logging.getLogger(__name__)


def _subtask_log(context, level: str, message: str, extra: dict | None = None) -> None:
    subtask_id = getattr(context.subtask, "id", None)
    if subtask_id is None:
        return
    write_storage_subtask_log(str(subtask_id), level, message, extra or {})


def _log_search_result(context, result) -> None:
    context.log(
        "INFO",
        "查找下载文件",
        result.log_context,
        step="waiting_download",
    )


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


def mark_subtask_skipped_for_existing_targets(context, existing_result, expected_name: str) -> None:
    skipped_files = [
        {
            "renamed_name": expected_name,
            "existing_targets": existing_result.existing_targets,
            "skip_reason": "target_exists",
        }
    ]
    context.subtask.status = "skipped"
    context.subtask.skip_reason = "target_exists"
    context.subtask.skipped_files = skipped_files
    context.subtask.result = {
        "status": "skipped",
        "reason": "target_exists",
        "files": skipped_files,
    }
    context.log(
        "INFO",
        "目标文件已全部存在，子任务标记为跳过",
        {
            "skipped_files": skipped_files,
            "target_paths": existing_result.checked_targets,
            "existing_targets": existing_result.existing_targets,
            "expected_names": existing_result.expected_names,
        },
        step="waiting_download",
        event="subtask_skipped",
    )
    context.publish_subtask()


def execute_current_magnet_attempt(context, magnet: dict) -> bool:
    """Execute a single magnet download attempt through the full step pipeline."""
    from backend.app.modules.storage.tasks.policies import build_video_filename, code_folder_from_filename

    subtask = context.subtask
    config = context.config
    provider = context.provider
    magnet_url = magnet.get("magnet_url", "")
    if not magnet_url:
        context.log("WARNING", "磁力缺少链接", {"magnet_id": magnet.get("id")}, step="prepare")
        return False

    download_root = config.get("download_root_folder", "/Downloads")
    download_folder = f"{download_root}/storage_{subtask.id}"
    subtask.download_path = download_folder

    context.set_step("prepare")
    tags = list(magnet.get("tags") or [])
    preview_name = build_video_filename(subtask.movie_code, f"{subtask.movie_code}.mp4", tags, 0, 1)
    code_folder = code_folder_from_filename(preview_name)
    target_root = config.get("target_folder", "/Movies")
    target_locations = list(subtask.target_locations or [])
    selected_location = getattr(subtask, "selected_storage_location", None) or ""
    if selected_location:
        target_paths = [f"{target_root}/{selected_location}/{code_folder}"]
    else:
        target_paths = [f"{target_root}/{location}/{code_folder}" for location in target_locations] or [f"{target_root}/{code_folder}"]
    subtask.target_paths = target_paths
    context.log(
        "INFO",
        f"准备完成: download={download_folder}, target={target_paths[-1]}, targets={target_paths}, suffix={preview_name.replace(subtask.movie_code.upper(), '').rsplit('.', 1)[0]}",
        {"download_path": download_folder, "target_paths": target_paths, "magnet_id": magnet.get("id")},
        step="prepare",
    )

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
    except Exception as exc:
        message = str(exc)
        if "10008" not in message and "任务已存在" not in message:
            context.log("ERROR", f"提交磁力失败: {exc}", {"magnet_id": magnet.get("id")}, step="submit_magnet")
            return False
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
    if not found_files:
        context.log(
            "WARNING",
            "未在下载目录找到可用视频文件",
            {"magnet_id": magnet.get("id"), "task_download_folder": download_folder, "download_root": download_root},
            step="waiting_download",
        )
        if submit_task_exists:
            expected_names = [preview_name]
            existing_result = find_existing_target_files(provider, target_paths, expected_names)
            context.log(
                "INFO",
                "检查目标目录是否已存在视频文件",
                {
                    "search_method": "list_sub_files",
                    "storage_mode": getattr(subtask, "storage_mode", ""),
                    "expected_names": expected_names,
                    "checked_targets": existing_result.checked_targets,
                    "existing_targets": existing_result.existing_targets,
                    "missing_targets": existing_result.missing_targets,
                    "source_path": existing_result.source_path,
                    "existing_files": existing_result.existing_files,
                },
                step="waiting_download",
            )
            if existing_result.all_targets_exist:
                subtask.status = "skipped"
                subtask.skip_reason = "target_exists"
                subtask.moved_files = []
                subtask.skipped_files = [
                    {
                        "name": existing_result.source_name or preview_name,
                        "skip_reason": "target_exists",
                        "existing_targets": [
                            item["path"]
                            for item in existing_result.existing_files
                        ],
                    }
                ]
                subtask.result = {
                    "status": "skipped",
                    "reason": "target_exists",
                    "files": subtask.skipped_files,
                }
                context.log(
                    "INFO",
                    "目标文件已全部存在，子任务标记为跳过",
                    {"skipped_files": subtask.skipped_files, "target_paths": target_paths},
                    step="move_files",
                    event="subtask_skipped",
                )
                context.publish_subtask()
                context.set_step("cleanup_files")
                cleanup_download_folder(context, download_folder, config)
                return True

            if getattr(subtask, "storage_mode", "") == "multiple" and existing_result.any_target_exists:
                copied_files = copy_existing_target_to_missing_targets(context, existing_result)
                subtask.renamed_files = []
                subtask.moved_files = copied_files
                subtask.skipped_files = []
                context.publish_subtask()
                context.set_step("verify_result")
                if not verify_moved_files(context, copied_files):
                    return False
                context.set_step("cleanup_files")
                cleanup_download_folder(context, download_folder, config)
                subtask.result = {
                    "status": "success",
                    "reason": "copied_from_existing_target",
                    "files": copied_files,
                    "existing_targets": existing_result.existing_targets,
                    "missing_targets": existing_result.missing_targets,
                }
                context.log(
                    "INFO",
                    "磁力任务处理成功",
                    {"magnet_id": magnet.get("id"), "files": copied_files, "reason": "copied_from_existing_target"},
                    step="cleanup_files",
                    event="magnet_success",
                )
                context.publish_subtask()
                return True
        return False

    total_size = sum(int(file.get("size") or 0) for file in found_files)
    context.log(
        "INFO",
        f"下载完成: 检测到 {len(found_files)} 个文件, 总大小 {total_size / (1024 * 1024):.1f} MB",
        {"file_count": len(found_files), "total_size": total_size},
        step="waiting_download",
    )

    context.set_step("scan_files")
    scanned = scan_found_files(found_files)
    context.log("INFO", f"扫描到 {len(scanned)} 个文件", {"file_count": len(scanned)}, step="scan_files")

    context.set_step("select_videos")
    classified = classify_scanned_files(scanned, config)
    context.log(
        "INFO",
        f"文件筛选: videos={len(classified.selected_videos)}, excluded={len(classified.excluded_files)}, subtitles={len(classified.subtitle_files)}, covers={len(classified.cover_files)}, other={len(classified.other_files)}",
        step="select_videos",
    )
    if not classified.selected_videos:
        context.log("WARNING", "扫描到文件但未识别到主视频", {"magnet_id": magnet.get("id"), "file_count": len(scanned)}, step="select_videos")
        return False

    context.set_step("rename_files")
    renamed_files = rename_selected_videos(context, classified.selected_videos, tags)

    context.set_step("move_files")
    move_result = move_renamed_videos(context, renamed_files, target_paths)
    moved_files = move_result.moved_files
    skipped_files = move_result.skipped_files
    subtask.renamed_files = renamed_files
    subtask.moved_files = moved_files
    subtask.skipped_files = skipped_files
    context.publish_subtask()
    if move_result.all_targets_exist:
        subtask.status = "skipped"
        subtask.skip_reason = "target_exists"
        subtask.result = {
            "status": "skipped",
            "reason": "target_exists",
            "files": skipped_files,
        }
        context.log(
            "INFO",
            "目标文件已全部存在，子任务标记为跳过",
            {"skipped_files": skipped_files, "target_paths": target_paths},
            step="move_files",
            event="subtask_skipped",
        )
        context.publish_subtask()
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True

    if move_result.all_rename_name_exists:
        subtask.status = "skipped"
        subtask.skip_reason = "rename_name_exists"
        subtask.result = {
            "status": "skipped",
            "reason": "rename_name_exists",
            "files": skipped_files,
        }
        context.log(
            "INFO",
            "重命名目标已存在，子任务标记为跳过",
            {"skipped_files": skipped_files, "target_paths": target_paths},
            step="move_files",
            event="subtask_skipped",
        )
        context.publish_subtask()
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True

    if not moved_files:
        context.log("WARNING", "没有文件完成移动或复制", {"skipped_files": skipped_files}, step="move_files")
        return False

    context.set_step("verify_result")
    if not verify_moved_files(context, moved_files):
        return False

    context.set_step("cleanup_files")
    cleanup_download_folder(context, download_folder, config)

    subtask.result = {"status": "success", "files": moved_files}
    context.log("INFO", "磁力任务处理成功", {"magnet_id": magnet.get("id"), "files": moved_files}, step="cleanup_files", event="magnet_success")
    return True


def execute_subtask_pipeline(context) -> None:
    """Execute the full subtask pipeline."""
    from backend.app.modules.storage.tasks.policies import order_magnet_candidates

    subtask = context.subtask
    config = context.config

    subtask.status = "running"
    subtask.step = "prepare"
    subtask.started_at = datetime.now(timezone.utc)
    context.publish_subtask()

    context.log("INFO", "存储子任务 pipeline 开始", {"movie_id": str(subtask.movie_id)})

    # Get magnets for this movie
    from shared.database.models.content import Movie
    movie = context.db.get(Movie, subtask.movie_id)
    if movie is None:
        subtask.status = "failed"
        subtask.error_message = "电影不存在"
        subtask.finished_at = datetime.now(timezone.utc)
        context.publish_subtask()
        return

    magnets = [m for m in (movie.magnets or []) if m.magnet_url]
    if not magnets:
        subtask.status = "failed"
        subtask.error_message = "无可用磁力链接"
        subtask.finished_at = datetime.now(timezone.utc)
        context.publish_subtask()
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
        subtask.step = "prepare"
        subtask.current_magnet_id = magnet.get("id")
        subtask.current_magnet_url = magnet.get("magnet_url", "")
        context.publish_subtask()

        context.log(
            "INFO",
            "开始尝试磁力",
            {
                "magnet_id": magnet.get("id"),
                "weight": magnet.get("weight"),
                "selected": magnet.get("selected"),
            },
        )

        success = execute_current_magnet_attempt(context, magnet)

        context.log(
            "INFO" if success else "WARNING",
            "磁力尝试完成" if success else "磁力尝试失败，准备尝试下一条",
            {"magnet_id": magnet.get("id"), "success": success},
        )

        attempt_record = {
            "magnet_id": magnet.get("id"),
            "success": success,
            "status": subtask.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        attempts = list(subtask.magnet_attempts or [])
        attempts.append(attempt_record)
        subtask.magnet_attempts = attempts

        if success:
            if subtask.status != "skipped":
                subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            context.publish_subtask()
            return

    # All magnets failed
    subtask.status = "failed"
    subtask.error_message = "所有磁力链接尝试均失败"
    subtask.finished_at = datetime.now(timezone.utc)
    context.publish_subtask()
