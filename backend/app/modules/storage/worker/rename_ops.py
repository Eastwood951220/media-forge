from __future__ import annotations

from pathlib import PurePosixPath


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
    from backend.app.modules.storage.tasks.policies import (
        build_video_filename,
        order_selected_videos_for_rename,
    )

    ordered_videos = order_selected_videos_for_rename(selected_videos)
    renamed = []
    total = len(ordered_videos)
    for index, video in enumerate(ordered_videos):
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
