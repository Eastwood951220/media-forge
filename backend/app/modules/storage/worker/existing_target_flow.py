from __future__ import annotations

from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.results import (
    mark_subtask_skipped_for_existing_targets,
    mark_subtask_success_from_existing_targets,
)
from backend.app.modules.storage.worker.target_files import (
    copy_existing_target_to_missing_targets,
    find_existing_target_files,
)
from backend.app.modules.storage.worker.verify_ops import verify_moved_files


def handle_existing_target_fallback(
    context,
    magnet: dict,
    preview_name: str,
    target_paths: list[str],
    download_folder: str,
    config: dict,
) -> bool | None:
    subtask = context.subtask
    expected_names = [preview_name]
    existing_result = find_existing_target_files(context.provider, target_paths, expected_names)
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
    return None
