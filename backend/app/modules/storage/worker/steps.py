from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import PurePosixPath

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.download import (
    is_submit_task_exists_error,
    poll_downloaded_video_files,
    recover_existing_downloaded_video_files,
)
from backend.app.modules.storage.worker.file_ops import (
    cleanup_download_folder,
    move_renamed_videos,
    rename_selected_videos,
    scan_found_files,
    verify_moved_files,
)
from backend.app.modules.storage.worker.results import (
    mark_subtask_skipped_for_existing_targets,
    mark_subtask_skipped_for_move_result,
    mark_subtask_success_from_existing_targets,
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
        if not is_submit_task_exists_error(exc):
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
                mark_subtask_skipped_for_existing_targets(context, existing_result, preview_name)
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
                mark_subtask_success_from_existing_targets(context, copied_files, existing_result, magnet)
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
        mark_subtask_skipped_for_move_result(context, "target_exists", skipped_files, target_paths)
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True

    if move_result.all_rename_name_exists:
        mark_subtask_skipped_for_move_result(context, "rename_name_exists", skipped_files, target_paths)
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
