from __future__ import annotations


def mark_subtask_skipped_for_existing_targets(context, existing_result, expected_name: str) -> None:
    skipped_files = [
        {
            "name": existing_result.source_name or expected_name,
            "skip_reason": "target_exists",
            "existing_targets": [item["path"] for item in existing_result.existing_files],
        }
    ]
    context.subtask.status = "skipped"
    context.subtask.skip_reason = "target_exists"
    context.subtask.moved_files = []
    context.subtask.skipped_files = skipped_files
    context.subtask.result = {"status": "skipped", "reason": "target_exists", "files": skipped_files}
    context.log(
        "INFO",
        "目标文件已全部存在，子任务标记为跳过",
        {"skipped_files": skipped_files, "target_paths": existing_result.checked_targets},
        step="move_files",
        event="subtask_skipped",
    )
    context.publish_subtask()


def mark_subtask_success_from_existing_targets(context, copied_files: list[dict], existing_result, magnet: dict) -> None:
    context.subtask.renamed_files = []
    context.subtask.moved_files = copied_files
    context.subtask.skipped_files = []
    context.subtask.result = {
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


def mark_subtask_skipped_for_move_result(context, reason: str, skipped_files: list[dict], target_paths: list[str]) -> None:
    context.subtask.status = "skipped"
    context.subtask.skip_reason = reason
    context.subtask.result = {"status": "skipped", "reason": reason, "files": skipped_files}
    message = "目标文件已全部存在，子任务标记为跳过" if reason == "target_exists" else "重命名目标已存在，子任务标记为跳过"
    context.log(
        "INFO",
        message,
        {"skipped_files": skipped_files, "target_paths": target_paths},
        step="move_files",
        event="subtask_skipped",
    )
    context.publish_subtask()
