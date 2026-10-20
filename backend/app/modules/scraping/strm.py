from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

REQUEST_TIMEOUT_SECONDS = 30.0
BODY_EXCERPT_LIMIT = 300


@dataclass
class StrmRunResult:
    success: bool
    status_code: int | None
    message: str


_HTTPX_API_KEY_PATTERN = re.compile(r"(api_key=)[^&\s]+")


class _RedactApiKeyFilter(logging.Filter):
    """Redact the api_key query parameter from httpx request log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple):
            return True
        args = list(record.args)
        changed = False
        for index, value in enumerate(args):
            if isinstance(value, httpx.URL):
                text = str(value)
                redacted = _HTTPX_API_KEY_PATTERN.sub(r"\1***", text)
                if redacted != text:
                    args[index] = redacted
                    changed = True
        if changed:
            record.args = tuple(args)
        return True


logging.getLogger("httpx").addFilter(_RedactApiKeyFilter())


def _redact(text: str, api_key: str) -> str:
    if api_key:
        return text.replace(api_key, "***")
    return text


def _excerpt(response: httpx.Response) -> str:
    try:
        text = response.text
    except Exception:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) > BODY_EXCERPT_LIMIT:
        return collapsed[:BODY_EXCERPT_LIMIT] + "..."
    return collapsed


def _message(status_code: int | None, body: str) -> str:
    message = f"HTTP {status_code}" if status_code is not None else "HTTP 请求失败"
    if body:
        message = f"{message}: {body}"
    return message


def run_strm_generation(
    config: Mapping[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
) -> StrmRunResult:
    base_url = str(config.get("base_url") or "").strip().rstrip("/")
    api_key = str(config.get("api_key") or "")
    directory_id = config.get("directory_id")
    url = f"{base_url}/api/sync/path/start"

    try:
        with httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            transport=transport,
        ) as client:
            response = client.post(
                url,
                params={"api_key": api_key},
                json={"id": directory_id},
            )
            response.raise_for_status()
            return StrmRunResult(
                success=True,
                status_code=response.status_code,
                message=_redact(_message(response.status_code, _excerpt(response)), api_key),
            )
    except httpx.HTTPStatusError as exc:
        return StrmRunResult(
            success=False,
            status_code=exc.response.status_code,
            message=_redact(
                _message(exc.response.status_code, _excerpt(exc.response)),
                api_key,
            ),
        )
    except httpx.HTTPError as exc:
        return StrmRunResult(
            success=False,
            status_code=None,
            message=_redact(f"{type(exc).__name__}: {exc}", api_key),
        )
    except Exception as exc:
        return StrmRunResult(
            success=False,
            status_code=None,
            message=_redact(f"{type(exc).__name__}: {exc}", api_key),
        )
