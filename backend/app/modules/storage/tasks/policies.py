from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

CHINESE_TAG_KEYWORDS = ("字幕", "中文字幕", "中字", "中文")
UNCENSORED_TAG_KEYWORDS = ("破解", "无码", "无码破解")


def generate_default_alias(now: datetime, sequence: int) -> str:
    return f"云存储_{now.strftime('%Y%m%d%H%M%S')}_{sequence:04d}"


def order_magnet_candidates(magnets: list[dict], max_attempts: int) -> list[dict]:
    selected = [m for m in magnets if m.get("selected")]
    selected_first = selected[:1]
    selected_ids = {m.get("id") for m in selected_first}
    remaining = [m for m in magnets if m.get("id") not in selected_ids]
    remaining.sort(key=lambda item: int(item.get("weight") or 0), reverse=True)
    return [*selected_first, *remaining][:max_attempts]


def derive_code_suffix(tags: list[str]) -> str:
    has_chinese = any(keyword in tag for tag in tags for keyword in CHINESE_TAG_KEYWORDS)
    has_uncensored = any(keyword in tag for tag in tags for keyword in UNCENSORED_TAG_KEYWORDS)
    if has_chinese and has_uncensored:
        return "-UC"
    if has_chinese:
        return "-C"
    if has_uncensored:
        return "-U"
    return ""


def infer_disc_number(original_name: str, index: int) -> int:
    stem = PurePosixPath(original_name).stem
    match = re.search(r"(?:part|cd|disc)[_.\-\s]?0*(\d+)", stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    letter = re.search(r"(?:^|[_.\-\s])([ABC])(?:$|[_.\-\s])", stem, re.IGNORECASE)
    if letter:
        return ord(letter.group(1).upper()) - ord("A") + 1
    return index + 1


def build_video_filename(movie_code: str, original_name: str, tags: list[str], index: int, total: int) -> str:
    ext = PurePosixPath(original_name).suffix
    base = f"{movie_code.upper()}{derive_code_suffix(tags)}"
    if total <= 1:
        return f"{base}{ext}"
    return f"{base}-CD{infer_disc_number(original_name, index)}{ext}"


def code_folder_from_filename(filename: str) -> str:
    stem = PurePosixPath(filename).stem
    return re.sub(r"-CD\d+$", "", stem, flags=re.IGNORECASE)
