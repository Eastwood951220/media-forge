from __future__ import annotations

import re
from typing import Any


def parse_size_mb(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    size_text = str(value).strip().upper()
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|TB)?", size_text)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = match.group(2) or "MB"
    multipliers = {"KB": 1 / 1024, "MB": 1, "GB": 1024, "TB": 1024 * 1024}
    return number * multipliers.get(unit, 1)


def has_chinese_sub(magnet: dict[str, Any]) -> bool:
    if magnet.get("has_chinese_sub"):
        return True
    tags = magnet.get("tags") or []
    if any("字幕" in str(tag) or "中字" in str(tag) for tag in tags):
        return True
    title = (magnet.get("title") or magnet.get("name") or "").lower()
    return any(keyword in title for keyword in ["chs", "cht", "chinese", "中字", "中文", "字幕"])


def compute_magnet_weight(magnet: dict[str, Any]) -> int:
    has_sub = has_chinese_sub(magnet)
    size_mb = parse_size_mb(magnet.get("size") or magnet.get("size_text"))
    is_large_sub = has_sub and size_mb > 2048

    file_count = magnet.get("file_count")
    if isinstance(file_count, (int, float)) and file_count > 0:
        file_penalty = max(0, 10000 - int(file_count) * 100)
    else:
        file_penalty = 5000

    return int(is_large_sub * 100000 + has_sub * 10000 + min(size_mb, 50000) + file_penalty)
