from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.timeline import classify_scanned_files

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
            return found_files

        context.log(
            "INFO",
            f"轮询 #{poll_index}: 目录为空，等待中",
            {"poll_index": poll_index, "max_poll_count": max_poll_count, "search_paths": search_paths},
            step="waiting_download",
        )
        if poll_index < max_poll_count:
            time.sleep(random.uniform(poll_min, poll_max))

    context.log(
        "WARNING",
        f"轮询次数超过上限: {max_poll_count}/{max_poll_count}，跳过当前磁力",
        {"max_poll_count": max_poll_count, "search_paths": search_paths},
        step="waiting_download",
    )
    return []


def scan_found_files(found_files: list[dict]) -> list[dict]:
    return [
        {
            "name": file["name"],
            "path": file["path"],
            "size": int(file.get("size") or 0),
            "is_dir": bool(file.get("is_dir", False)),
        }
        for file in found_files
        if not file.get("is_dir", False)
    ]


def is_rename_name_exists_error(error: Exception | str) -> bool:
    message = str(error)
    return (
        "20004" in message
        or "目录名称已存在" in message
        or "名称已存在" in message
        or "already exists" in message.lower()
    )


def _find_existing_rename_target(provider, path: str):
    try:
        return provider.find_file(path)
    except Exception:
        return None


def rename_selected_videos(context, selected_videos: list[dict], tags: list[str]) -> list[dict]:
    from backend.app.modules.storage.tasks.policies import build_video_filename

    renamed = []
    total = len(selected_videos)
    for index, video in enumerate(selected_videos):
        old_path = video["path"]
        new_name = build_video_filename(context.subtask.movie_code, video["name"], tags, index, total)
        new_path = str(PurePosixPath(old_path).parent / new_name)
        if PurePosixPath(old_path).name == new_name:
            renamed.append({**video, "renamed_path": old_path, "renamed_name": new_name})
            context.log("INFO", f"重命名: {video['name']} → {new_name}", step="rename_files")
            continue
        try:
            context.provider.rename_file(old_path, new_name)
            renamed.append({**video, "renamed_path": new_path, "renamed_name": new_name})
            context.log("INFO", f"重命名: {video['name']} → {new_name}", step="rename_files")
        except Exception as exc:
            if is_rename_name_exists_error(exc):
                existing = _find_existing_rename_target(context.provider, new_path)
                if existing is not None:
                    renamed.append({
                        **video,
                        "renamed_path": new_path,
                        "renamed_name": new_name,
                        "rename_name_exists": True,
                        "existing_path": new_path,
                    })
                    context.log(
                        "WARNING",
                        f"重命名目标已存在，复用已有文件: {video['name']} → {new_name}",
                        {"source": old_path, "existing_path": new_path},
                        step="rename_files",
                    )
                    continue
                context.log(
                    "WARNING",
                    f"重命名目标已存在但未能定位已有文件: {video['name']} → {new_name}",
                    {"source": old_path, "expected_path": new_path, "error": str(exc)},
                    step="rename_files",
                )
                renamed.append({
                    **video,
                    "rename_error": str(exc),
                    "rename_name_exists": True,
                    "renamed_name": new_name,
                })
                continue

            context.log("ERROR", f"重命名失败: {video['name']}: {exc}", step="rename_files")
            renamed.append({**video, "rename_error": str(exc)})
    return renamed


def _target_file_exists(provider, target_path: str) -> bool:
    try:
        found = provider.find_file(target_path)
        return bool(found and int(getattr(found, "size", 0) or 0) > 0)
    except Exception:
        return False


@dataclass
class MoveRenamedVideosResult:
    moved_files: list[dict]
    skipped_files: list[dict]
    all_targets_exist: bool = False
    all_rename_name_exists: bool = False


def move_renamed_videos(context, renamed_files: list[dict], target_paths: list[str]) -> MoveRenamedVideosResult:
    moved: list[dict] = []
    skipped: list[dict] = []
    copy_targets = target_paths[:-1] if len(target_paths) > 1 else []
    move_target = target_paths[-1]

    if context.config.get("auto_create_target_folder", True):
        for target_path in target_paths:
            ensure_directory_chain(context.provider, target_path)
            context.log("INFO", f"已创建文件夹: {target_path}", step="move_files")

    for file_info in renamed_files:
        if file_info.get("rename_error"):
            if file_info.get("rename_name_exists"):
                skipped.append({**file_info, "skip_reason": "rename_name_exists"})
                context.log(
                    "WARNING",
                    f"跳过重命名目标已存在的文件: {file_info['name']}",
                    {"rename_error": file_info.get("rename_error"), "renamed_name": file_info.get("renamed_name")},
                    step="move_files",
                )
                continue
            skipped.append({**file_info, "skip_reason": "rename_failed"})
            context.log("WARNING", f"跳过重命名失败的文件: {file_info['name']}", step="move_files")
            continue

        src = file_info.get("renamed_path") or file_info["path"]
        file_name = PurePosixPath(src).name
        existing_targets = [str(PurePosixPath(target) / file_name) for target in target_paths if _target_file_exists(context.provider, str(PurePosixPath(target) / file_name))]
        if len(existing_targets) == len(target_paths):
            skipped.append({**file_info, "skip_reason": "target_exists", "existing_targets": existing_targets})
            context.log("INFO", f"跳过已存在: {file_name}", {"existing_targets": existing_targets}, step="move_files")
            continue

        copied_paths = []
        for copy_target in copy_targets:
            copy_dst = str(PurePosixPath(copy_target) / file_name)
            if _target_file_exists(context.provider, copy_dst):
                copied_paths.append(copy_dst)
                context.log("INFO", f"跳过已存在: {file_name}", {"target": copy_dst}, step="move_files")
                continue
            context.provider.copy_file(src, copy_target)
            copied_paths.append(copy_dst)
            context.log("INFO", f"已复制: {file_name} → {copy_target}", step="move_files")

        move_dst = str(PurePosixPath(move_target) / file_name)
        if _target_file_exists(context.provider, move_dst):
            moved.append({**file_info, "moved_path": move_dst, "copied_paths": copied_paths})
            context.log("INFO", f"跳过已存在: {file_name}", {"target": move_dst}, step="move_files")
            continue
        context.provider.move_files([src], move_target)
        moved.append({**file_info, "moved_path": move_dst, "copied_paths": copied_paths})
        context.log("INFO", f"已移动: {file_name} → {move_target}", step="move_files")

    all_targets_exist = bool(renamed_files) and len(skipped) == len(renamed_files) and all(
        item.get("skip_reason") == "target_exists"
        for item in skipped
    )
    all_rename_name_exists = bool(renamed_files) and len(skipped) == len(renamed_files) and all(
        item.get("skip_reason") == "rename_name_exists"
        for item in skipped
    )
    return MoveRenamedVideosResult(
        moved_files=moved,
        skipped_files=skipped,
        all_targets_exist=all_targets_exist,
        all_rename_name_exists=all_rename_name_exists,
    )


def verify_moved_files(context, moved_files: list[dict]) -> bool:
    all_ok = True
    for video in moved_files:
        paths_to_verify = []
        moved_path = video.get("moved_path") or video.get("target")
        if moved_path:
            paths_to_verify.append(("moved", moved_path))
        for copied_path in video.get("copied_paths", []):
            paths_to_verify.append(("copied", copied_path))

        if not paths_to_verify:
            all_ok = False
            context.log("ERROR", f"验证失败: {video.get('name')} 无任何目标路径", step="verify_result")
            continue

        expected_size = int(video.get("size") or 0)
        for label, path in paths_to_verify:
            info = context.provider.find_file(path)
            if not info:
                all_ok = False
                context.log("ERROR", f"验证失败: {label} 文件不存在 {path}", step="verify_result")
                continue
            actual_size = int(getattr(info, "size", 0) or 0)
            if expected_size > 0 and abs(actual_size - expected_size) > 1024:
                all_ok = False
                context.log(
                    "ERROR",
                    f"验证失败: {label} 大小不匹配 {PurePosixPath(path).name} (expected={expected_size}, actual={actual_size})",
                    step="verify_result",
                )

    if all_ok:
        context.log("INFO", "验证通过: 所有文件完整 (含复制目标)", step="verify_result")
    return all_ok


def cleanup_download_folder(context, download_folder: str, config: dict) -> None:
    if download_folder and config.get("use_task_subfolder", True):
        try:
            context.provider.delete_file(download_folder)
            context.log("INFO", f"已清理下载目录: {download_folder}", step="cleanup_files")
        except Exception as exc:
            context.log("WARNING", f"清理下载目录失败 (非致命): {exc}", step="cleanup_files")
    context.log("INFO", "清理完成", step="cleanup_files")


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
        context.log("WARNING", "磁力链接已存在 (code 10008)，搜索现有下载中", {"magnet_id": magnet.get("id")}, step="submit_magnet")

    context.set_step("waiting_download")
    search_terms = [subtask.movie_code]
    search_paths = [download_folder, download_root, *target_paths]
    found_files = poll_downloaded_video_files(context, search_terms, search_paths)
    if not found_files:
        context.log("WARNING", "未在下载目录找到可用视频文件", {"magnet_id": magnet.get("id"), "search_paths": search_paths}, step="waiting_download")
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
