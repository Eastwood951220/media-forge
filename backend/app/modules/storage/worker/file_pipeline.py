from __future__ import annotations

from backend.app.modules.storage.tasks.policies import dedupe_quality_variants
from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.file_ops import scan_found_files
from backend.app.modules.storage.worker.move_ops import move_renamed_videos
from backend.app.modules.storage.worker.rename_ops import rename_selected_videos
from backend.app.modules.storage.worker.results import mark_subtask_skipped_for_move_result
from backend.app.modules.storage.worker.timeline import classify_scanned_files
from backend.app.modules.storage.worker.verify_ops import verify_moved_files


def run_found_files_pipeline(
    context,
    magnet: dict,
    found_files: list[dict],
    target_paths: list[str],
    download_folder: str,
    config: dict,
) -> bool:
    subtask = context.subtask
    tags = list(magnet.get("tags") or [])
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

    selected_videos, dropped_quality_variants = dedupe_quality_variants(classified.selected_videos)
    if dropped_quality_variants:
        context.log(
            "INFO",
            "清晰度重复筛选",
            {
                "kept_files": [
                    {"name": item.get("name"), "path": item.get("path"), "size": int(item.get("size") or 0)}
                    for item in selected_videos
                ],
                "dropped_files": dropped_quality_variants,
            },
            step="select_videos",
        )
    else:
        selected_videos = classified.selected_videos

    if not selected_videos:
        context.log("WARNING", "扫描到文件但未识别到主视频", {"magnet_id": magnet.get("id"), "file_count": len(scanned)}, step="select_videos")
        return False

    context.set_step("rename_files")
    renamed_files = rename_selected_videos(context, selected_videos, tags)

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
