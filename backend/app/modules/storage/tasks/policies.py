from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

CHINESE_TAG_KEYWORDS = ("字幕", "中文字幕", "中字", "中文")
UNCENSORED_TAG_KEYWORDS = ("破解", "无码", "无码破解")

VR_TAG_PATTERN = re.compile(r"(^|[^a-z0-9])vr([^a-z0-9]|$)", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"\d+|[A-Za-z]+|[^A-Za-z\d]+")


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
    bare_part = re.search(r"(?:^|[_.\-\s])0*(\d+)(?=[_.\-\s]\d+(?:$|[_.\-\s])|$)", stem)
    if bare_part:
        return int(bare_part.group(1))
    return index + 1


def _tokenize_filename_stem(filename: str) -> list[str | int]:
    stem = PurePosixPath(str(filename or "")).stem
    tokens: list[str | int] = []
    for token in TOKEN_PATTERN.findall(stem):
        if token.isdigit():
            tokens.append(int(token))
        else:
            tokens.append(token.lower())
    return tokens


def natural_filename_sort_key(filename: str) -> tuple:
    tokens = _tokenize_filename_stem(filename)
    normalized = tuple((0, token) if isinstance(token, int) else (1, token) for token in tokens)
    suffix = PurePosixPath(str(filename or "")).suffix.lower()
    return normalized, suffix, str(filename or "").lower()


def _all_same_except_position(token_rows: list[list[str | int]], position: int) -> bool:
    for candidate_position in range(max(len(row) for row in token_rows)):
        if candidate_position == position:
            continue
        values = {
            row[candidate_position] if candidate_position < len(row) else None
            for row in token_rows
        }
        if len(values) > 1:
            return False
    return True


def _differing_numeric_position(token_rows: list[list[str | int]]) -> int | None:
    if len(token_rows) <= 1:
        return None
    max_length = max(len(row) for row in token_rows)
    for position in range(max_length):
        values = [
            row[position] if position < len(row) else None
            for row in token_rows
        ]
        unique_values = set(values)
        if len(unique_values) <= 1:
            continue
        if all(isinstance(value, int) for value in values) and _all_same_except_position(token_rows, position):
            return position
    return None


def _batch_difference_sort_key(video: dict, position: int) -> tuple:
    name = str(video.get("name") or "")
    tokens = _tokenize_filename_stem(name)
    part = tokens[position] if position < len(tokens) else 0
    numeric_part = part if isinstance(part, int) else 0
    return numeric_part, natural_filename_sort_key(name), str(video.get("path") or "").lower()


def order_selected_videos_for_rename(videos: list[dict]) -> list[dict]:
    token_rows = [_tokenize_filename_stem(str(video.get("name") or "")) for video in videos]
    differing_position = _differing_numeric_position(token_rows)
    if differing_position is not None:
        return sorted(videos, key=lambda video: _batch_difference_sort_key(video, differing_position))
    return sorted(
        videos,
        key=lambda video: (
            natural_filename_sort_key(str(video.get("name") or "")),
            str(video.get("path") or "").lower(),
        ),
    )


def build_video_filename(movie_code: str, original_name: str, tags: list[str], index: int, total: int) -> str:
    ext = PurePosixPath(original_name).suffix
    base = f"{movie_code.upper()}{derive_code_suffix(tags)}"
    if total <= 1:
        return f"{base}{ext}"
    return f"{base}-CD{infer_disc_number(original_name, index)}{ext}"


def code_folder_from_filename(filename: str) -> str:
    stem = PurePosixPath(filename).stem
    return re.sub(r"-CD\d+$", "", stem, flags=re.IGNORECASE)


def is_vr_movie_tags(tags: list[str]) -> bool:
    for tag in tags or []:
        if not isinstance(tag, str):
            continue
        normalized = tag.strip()
        if not normalized:
            continue
        if normalized.lower() == "vr":
            return True
        if normalized.upper().startswith("VR") and len(normalized) > 2:
            return True
        if VR_TAG_PATTERN.search(normalized):
            return True
    return False


def insert_vr_directory(target_path: str, code_folder: str) -> str:
    path = PurePosixPath(target_path)
    if path.name != code_folder:
        return str(path / "VR" / code_folder)
    parent = path.parent
    if parent.name.upper() == "VR":
        return str(path)
    return str(parent / "VR" / path.name)


QUALITY_TOKEN_PATTERN = re.compile(
    r"(?i)(^|[\s._\-\[\]()])(?:8k|4k|2k|uhd|fhd|hd|2160p|1440p|1080p|720p)(?=$|[\s._\-\[\]()])"
)
SEPARATOR_PATTERN = re.compile(r"[\s._\-\[\]()]+")


def quality_dedupe_key(filename: str) -> str:
    stem = PurePosixPath(str(filename or "")).stem.lower()
    without_quality = QUALITY_TOKEN_PATTERN.sub(" ", stem)
    normalized = SEPARATOR_PATTERN.sub("_", without_quality).strip("_")
    return normalized or stem


def _video_sort_key(video: dict) -> tuple[int, str, str]:
    return (
        -int(video.get("size") or 0),
        str(video.get("name") or "").lower(),
        str(video.get("path") or "").lower(),
    )


def dedupe_quality_variants(videos: list[dict]) -> tuple[list[dict], list[dict]]:
    groups: dict[str, list[dict]] = {}
    for video in videos:
        key = quality_dedupe_key(str(video.get("name") or ""))
        if not key:
            key = str(video.get("path") or id(video))
        groups.setdefault(key, []).append(video)

    kept_by_identity: set[int] = set()
    dropped: list[dict] = []
    for key, group in groups.items():
        winner = sorted(group, key=_video_sort_key)[0]
        kept_by_identity.add(id(winner))
        if len(group) <= 1:
            continue
        for item in group:
            if item is winner:
                continue
            dropped.append(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "size": int(item.get("size") or 0),
                    "dedupe_group_key": key,
                    "kept_name": winner.get("name"),
                    "reason": "duplicate_quality_smaller_size",
                }
            )

    kept = [video for video in videos if id(video) in kept_by_identity]
    return kept, dropped
