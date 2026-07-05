from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.target_files import ensure_directory_chain


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


def target_files_exist(provider, target_folder: str, filenames: list[str]) -> bool:
    """Check if all target files exist in the folder."""
    try:
        existing = provider.list_files(target_folder)
        existing_names = {getattr(f, "name", "") for f in existing}
        return all(name in existing_names for name in filenames)
    except Exception:
        return False


def scan_found_files(found_files: list[dict]) -> list[dict]:
    return [
        {
            "name": file["name"],
            "path": file["path"],
            "size": int(file.get("size") or 0),
            "is_dir": bool(file.get("is_dir", False)),
        }
        for file in found_files
        if not file.get("is_dir", False) and "/[Search]" not in str(file.get("path", ""))
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
