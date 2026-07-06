from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from backend.app.modules.storage.worker.target_files import ensure_directory_chain


def _target_file_exists(provider, target_path: str) -> bool:
    try:
        found = provider.find_file(target_path)
        return bool(found and int(getattr(found, "size", 0) or 0) > 0)
    except Exception:
        return False


def _move_source_path(file_info: dict) -> str:
    return str(file_info.get("existing_path") or file_info.get("renamed_path") or file_info["path"])


def _move_file_name(file_info: dict) -> str:
    return str(file_info.get("renamed_name") or PurePosixPath(_move_source_path(file_info)).name)


def _target_file_path(target_folder: str, file_name: str) -> str:
    return str(PurePosixPath(target_folder) / file_name)


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

        src = _move_source_path(file_info)
        file_name = _move_file_name(file_info)
        if file_info.get("rename_name_exists"):
            context.log(
                "INFO",
                f"使用已存在的规范命名文件执行移动或复制: {file_name}",
                {"source": src, "targets": target_paths},
                step="move_files",
            )
        existing_targets = [
            _target_file_path(target, file_name)
            for target in target_paths
            if _target_file_exists(context.provider, _target_file_path(target, file_name))
        ]
        if len(existing_targets) == len(target_paths):
            skipped.append({**file_info, "skip_reason": "target_exists", "existing_targets": existing_targets})
            context.log("INFO", f"跳过已存在: {file_name}", {"existing_targets": existing_targets}, step="move_files")
            continue

        copied_paths = []
        for copy_target in copy_targets:
            copy_dst = _target_file_path(copy_target, file_name)
            if _target_file_exists(context.provider, copy_dst):
                copied_paths.append(copy_dst)
                context.log("INFO", f"跳过已存在: {file_name}", {"target": copy_dst}, step="move_files")
                continue
            context.provider.copy_file(src, copy_target)
            copied_paths.append(copy_dst)
            context.log("INFO", f"已复制: {file_name} → {copy_target}", step="move_files")

        move_dst = _target_file_path(move_target, file_name)
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
