from __future__ import annotations

from pathlib import PurePosixPath


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
