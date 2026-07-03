from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

PIPELINE_STEPS = [
    "prepare",
    "submit_magnet",
    "waiting_download",
    "scan_files",
    "select_videos",
    "rename_files",
    "move_files",
    "verify_result",
    "cleanup_files",
]

STEP_LABELS = {
    "prepare": "准备任务",
    "submit_magnet": "提交磁力",
    "waiting_download": "云端下载",
    "scan_files": "扫描文件",
    "select_videos": "识别主视频",
    "rename_files": "重命名",
    "move_files": "移动文件",
    "verify_result": "校验结果",
    "cleanup_files": "清理临时文件",
    "done": "完成",
}

SUBTITLE_EXTENSIONS = frozenset({".srt", ".ass", ".ssa", ".sub", ".sup", ".idx"})
COVER_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp"})


@dataclass
class ClassifiedFiles:
    selected_videos: list[dict] = field(default_factory=list)
    excluded_files: list[dict] = field(default_factory=list)
    subtitle_files: list[dict] = field(default_factory=list)
    cover_files: list[dict] = field(default_factory=list)
    other_files: list[dict] = field(default_factory=list)


def classify_scanned_files(scanned: list[dict], config: dict) -> ClassifiedFiles:
    result = ClassifiedFiles()
    video_exts = {str(ext).lower() for ext in config.get("video_extensions", [])}
    min_size = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    excluded_keywords = [str(item).lower() for item in config.get("excluded_filename_keywords", [])]

    for file_info in scanned:
        name = str(file_info["name"])
        ext = PurePosixPath(name).suffix.lower()
        lower_name = name.lower()
        size = int(file_info.get("size") or 0)
        if any(keyword in lower_name for keyword in excluded_keywords):
            result.excluded_files.append(file_info)
        elif ext in video_exts and size >= min_size:
            result.selected_videos.append({**file_info, "video_type": "main"})
        elif ext in video_exts:
            result.excluded_files.append(file_info)
        elif ext in SUBTITLE_EXTENSIONS:
            result.subtitle_files.append(file_info)
        elif ext in COVER_EXTENSIONS:
            result.cover_files.append(file_info)
        else:
            result.other_files.append(file_info)

    return result
