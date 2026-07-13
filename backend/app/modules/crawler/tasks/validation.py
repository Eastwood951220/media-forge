from __future__ import annotations

from urllib.parse import urlparse

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


def normalize_temporary_detail_urls(detail_urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    if not detail_urls:
        raise ValueError("至少需要 1 条详情页 URL")
    if len(detail_urls) > 50:
        raise ValueError("临时任务最多支持 50 条详情页 URL")
    for index, raw_url in enumerate(detail_urls, start=1):
        url = str(raw_url or "").strip()
        if not url:
            raise ValueError(f"第 {index} 条详情页 URL 不能为空")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"javdb.com", "www.javdb.com"} or not parsed.path.startswith("/v/"):
            raise ValueError(f"第 {index} 条不是有效的 JavDB 详情页 URL")
        if url in seen:
            raise ValueError(f"第 {index} 条详情页 URL 重复")
        seen.add(url)
        normalized.append(url)
    return normalized
