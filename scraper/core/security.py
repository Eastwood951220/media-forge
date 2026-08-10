from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SECURITY_KEYWORDS = [
    "captcha",
    "cloudflare",
    "verify you are human",
    "security check",
    "access denied",
    "too many requests",
    "human verification",
    "人机验证",
    "安全验证",
    "访问过于频繁",
    "请完成安全检查",
]


@dataclass(frozen=True)
class AccessState:
    ok: bool
    status_code: int | None
    reason: str
    message: str


def _coerce_status(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def get_response_status(page) -> int | None:
    for attr in ("status_code", "status"):
        status = _coerce_status(getattr(page, attr, None))
        if status is not None:
            return status

    response = getattr(page, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            status = _coerce_status(getattr(response, attr, None))
            if status is not None:
                return status

    metadata = getattr(page, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("status_code", "status"):
            status = _coerce_status(metadata.get(key))
            if status is not None:
                return status

    return None


def _extract_page_text(page) -> str:
    text = getattr(page, "text", "") or ""

    if callable(text):
        text = text() or ""

    if not text and hasattr(page, "css"):
        try:
            text = " ".join(page.css("body ::text, body::text").getall())
        except Exception:
            text = ""

    if not text and hasattr(page, "xpath"):
        try:
            text = " ".join(page.xpath("//text()").getall())
        except Exception:
            text = ""

    return str(text)


def detect_access_state(page) -> AccessState:
    status_code = get_response_status(page)
    if status_code == 403:
        return AccessState(
            ok=False,
            status_code=status_code,
            reason="http_403",
            message="JavDB 返回 403，后端爬虫会话被拒绝，请在浏览器完成验证后重新导出 Cookie",
        )
    if status_code == 429:
        return AccessState(
            ok=False,
            status_code=status_code,
            reason="http_429",
            message="JavDB 返回 429，请降低并发或延长请求间隔后重试",
        )

    lower_text = _extract_page_text(page).lower()
    if any(keyword.lower() in lower_text for keyword in SECURITY_KEYWORDS):
        return AccessState(
            ok=False,
            status_code=status_code,
            reason="security_keywords",
            message="JavDB 触发安全验证，请刷新 Cookie 或完成浏览器验证",
        )

    return AccessState(ok=True, status_code=status_code, reason="ok", message="ok")


def is_security_check_page(page) -> bool:
    return not detect_access_state(page).ok
