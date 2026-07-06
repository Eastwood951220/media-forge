from __future__ import annotations

from backend.app.modules.storage.worker.file_candidates import append_candidate
from backend.app.modules.storage.worker.file_identity import resolve_file_candidate
from backend.app.modules.storage.worker.file_listing import find_listed_video_files, recursive_list
from backend.app.modules.storage.worker.file_result import ScopedSearchResult


def find_scoped_video_files(
    *,
    provider,
    search_terms: list[str],
    search_path: str,
    search_scope: str,
    movie_code: str,
    task_download_folder: str,
    config: dict,
) -> ScopedSearchResult:
    accepted: list[dict] = []
    rejected: list[dict] = []
    raw_results: list[dict] = []
    resolved_results: list[dict] = []
    original_path_results: list[dict] = []
    seen: set[str] = set()
    search_term = search_terms[0] if search_terms else movie_code

    try:
        search_results = provider.search_files(search_term, search_path)
    except Exception as exc:
        return ScopedSearchResult(
            accepted_files=[],
            log_context={
                "search_term": search_term,
                "search_path": search_path,
                "search_scope": search_scope,
                "search_method": "search_files",
                "raw_results": [],
                "resolved_results": [],
                "original_path_results": [],
                "accepted_files": [],
                "rejected_files": [{"name": "", "path": search_path, "size": 0, "reason": "search_error", "error": str(exc)}],
            },
        )

    for file_obj in search_results:
        raw_item, resolved, resolution_error, original_log = resolve_file_candidate(provider, file_obj)
        raw_results.append({key: raw_item[key] for key in ("name", "path", "size")})
        resolved_results.append({key: resolved[key] for key in ("name", "path", "size")})
        if original_log is not None:
            original_path_results.append(original_log)
        append_candidate(
            raw_candidate=raw_item,
            candidate=resolved,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
            resolution_error=resolution_error,
        )

    try:
        listed_files = recursive_list(provider, search_path, config)
    except Exception as exc:
        rejected.append({"name": "", "path": search_path, "size": 0, "reason": "list_error", "error": str(exc)})
        listed_files = []

    for listed in listed_files:
        raw_results.append({key: listed[key] for key in ("name", "path", "size")})
        resolved_results.append({key: listed[key] for key in ("name", "path", "size")})
        append_candidate(
            raw_candidate=listed,
            candidate=listed,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
        )

    return ScopedSearchResult(
        accepted_files=accepted,
        log_context={
            "search_term": search_term,
            "search_path": search_path,
            "search_scope": search_scope,
            "search_method": "search_files",
            "raw_results": raw_results,
            "resolved_results": resolved_results,
            "original_path_results": original_path_results,
            "accepted_files": accepted,
            "rejected_files": rejected,
        },
    )


def find_existing_video_files(provider, search_terms: list[str], search_paths: list[str], config: dict) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    movie_code = search_terms[0] if search_terms else ""
    task_download_folder = search_paths[0] if search_paths else "/"
    for path in search_paths:
        scoped = find_scoped_video_files(
            provider=provider,
            search_terms=search_terms,
            search_path=path,
            search_scope="download_root",
            movie_code=movie_code,
            task_download_folder=task_download_folder,
            config=config,
        )
        for item in scoped.accepted_files:
            if item["path"] not in seen:
                seen.add(item["path"])
                results.append(item)
        if results:
            return results
    return results


def find_recovery_video_files(
    *,
    provider,
    search_terms: list[str],
    task_download_folder: str,
    download_root: str,
    movie_code: str,
    config: dict,
) -> ScopedSearchResult:
    task_result = find_listed_video_files(
        provider=provider,
        search_path=task_download_folder,
        search_scope="recovery_task_download_folder",
        movie_code=movie_code,
        task_download_folder=task_download_folder,
        config=config,
    )
    if task_result.accepted_files:
        return task_result

    root_result = find_scoped_video_files(
        provider=provider,
        search_terms=search_terms,
        search_path=download_root,
        search_scope="recovery_download_root",
        movie_code=movie_code,
        task_download_folder=download_root,
        config=config,
    )
    return root_result
