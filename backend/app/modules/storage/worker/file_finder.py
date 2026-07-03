from __future__ import annotations

from pathlib import PurePosixPath


def _file_to_dict(provider, file_obj) -> dict:
    path = getattr(file_obj, "full_path", "") or getattr(file_obj, "fullPathName", "")
    if getattr(file_obj, "is_search_result", False) or getattr(file_obj, "isSearchResult", False):
        original = provider.get_original_path(path)
        if original:
            path = original
    return {
        "name": getattr(file_obj, "name", "") or PurePosixPath(path).name,
        "path": path,
        "size": int(getattr(file_obj, "size", 0) or 0),
        "is_dir": bool(getattr(file_obj, "is_directory", False) or getattr(file_obj, "isDirectory", False)),
    }


def _is_usable_video(file_dict: dict, config: dict) -> bool:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    return ext in set(config.get("video_extensions", [])) and int(file_dict.get("size") or 0) >= min_bytes


def _recursive_list(provider, path: str, config: dict) -> list[dict]:
    found = []
    for entry in provider.list_files(path):
        item = _file_to_dict(provider, entry)
        if item["is_dir"]:
            found.extend(_recursive_list(provider, item["path"], config))
        elif _is_usable_video(item, config):
            found.append(item)
    return found


def find_existing_video_files(provider, search_terms: list[str], search_paths: list[str], config: dict) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    for path in search_paths:
        for term in search_terms:
            try:
                search_results = provider.search_files(term, path)
            except Exception:
                search_results = []
            for file_obj in search_results:
                item = _file_to_dict(provider, file_obj)
                if not item["is_dir"] and _is_usable_video(item, config) and item["path"] not in seen:
                    seen.add(item["path"])
                    results.append(item)
        if results:
            return results
    for path in search_paths:
        try:
            for item in _recursive_list(provider, path, config):
                if item["path"] not in seen:
                    seen.add(item["path"])
                    results.append(item)
        except Exception:
            continue
        if results:
            return results
    return results
