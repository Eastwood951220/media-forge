from pathlib import PurePosixPath


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
