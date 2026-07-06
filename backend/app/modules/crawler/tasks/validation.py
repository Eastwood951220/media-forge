from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.modules.crawler.tasks.delete_service import VALID_DELETE_MODES


def check_urls_unique(urls) -> None:
    seen: set[str] = set()
    for entry in urls:
        if entry.url in seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"URL 重复: {entry.url}")
        seen.add(entry.url)


def ensure_delete_mode_supported(mode: str) -> None:
    if mode not in VALID_DELETE_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid delete mode: {mode}. Valid modes: {', '.join(VALID_DELETE_MODES)}",
        )
