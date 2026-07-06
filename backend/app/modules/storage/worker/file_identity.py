from __future__ import annotations

from pathlib import PurePosixPath


def raw_file_to_dict(file_obj) -> dict:
    path = getattr(file_obj, "full_path", "") or getattr(file_obj, "fullPathName", "")
    return {
        "name": getattr(file_obj, "name", "") or PurePosixPath(path).name,
        "path": path,
        "size": int(getattr(file_obj, "size", 0) or 0),
        "is_dir": bool(getattr(file_obj, "is_directory", False) or getattr(file_obj, "isDirectory", False)),
    }


def is_virtual_search_path(path: str) -> bool:
    return "/[Search]" in str(PurePosixPath(path))


def is_search_result(file_obj, raw_item: dict) -> bool:
    return bool(
        getattr(file_obj, "is_search_result", False)
        or getattr(file_obj, "isSearchResult", False)
        or is_virtual_search_path(raw_item["path"])
    )


def resolve_file_candidate(provider, file_obj) -> tuple[dict, dict, str | None, dict | None]:
    raw_item = raw_file_to_dict(file_obj)
    resolved_item = dict(raw_item)
    if not is_search_result(file_obj, raw_item):
        if is_virtual_search_path(raw_item["path"]):
            return raw_item, resolved_item, "virtual_search_path", None
        return raw_item, resolved_item, None, None

    try:
        original = provider.get_original_path(raw_item["path"])
        original_log = {
            "name": raw_item["name"],
            "raw_path": raw_item["path"],
            "original_path": original,
        }
    except Exception as exc:
        original = ""
        original_log = {
            "name": raw_item["name"],
            "raw_path": raw_item["path"],
            "original_path": "",
            "error": str(exc),
        }
    if not original:
        resolved_item["path"] = ""
        return raw_item, resolved_item, "missing_original_path", original_log
    resolved_item["path"] = original
    resolved_item["name"] = PurePosixPath(original).name
    if is_virtual_search_path(original):
        return raw_item, resolved_item, "virtual_search_path", original_log
    return raw_item, resolved_item, None, original_log


def file_to_dict(provider, file_obj) -> dict:
    raw_item, resolved_item, reason, _original_log = resolve_file_candidate(provider, file_obj)
    if reason is not None:
        return {
            **resolved_item,
            "resolution_error": reason,
            "raw_path": raw_item["path"],
            "resolved_path": resolved_item["path"],
        }
    return resolved_item
