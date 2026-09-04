from __future__ import annotations

from urllib.parse import urlparse


def detect_task_url_type(url: str, source: str | None = None) -> str | None:
    parsed = urlparse(url.strip())
    path = parsed.path or ""

    if path.startswith("/search"):
        return "search"
    if path.startswith("/actors/"):
        return "actors"
    if path.startswith("/series/"):
        return "series"
    if path.startswith("/makers/"):
        return "makers"
    if path.startswith("/directors/"):
        return "directors"
    if path.startswith("/video_codes/"):
        return "video_codes"
    if path.startswith("/lists/"):
        return "lists"
    if path == "/tags" or path.startswith("/tags/"):
        return "tags"
    if source == "javbus":
        return "detail"
    return None
