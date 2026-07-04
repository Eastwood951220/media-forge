# Storage Search Real Path Dedupe Design

## Goal

Prevent one real CloudDrive2 file from being accepted multiple times through search-result virtual paths, which causes a single video to be renamed as `-CD1`, `-CD2`, and `-CD3`.

## Problem

The attached log shows one actual `ACZD-165` video being discovered three times:

- `/云下载/storage_d124ebff-94f0-444b-af07-ce95362fcc7d/[Search]ACZD-165/hhd800.com@ACZD-165.mp4`
- `/云下载/storage_d124ebff-94f0-444b-af07-ce95362fcc7d/[Search]ACZD-165/ACZD-165/hhd800.com@ACZD-165.mp4`
- `/云下载/storage_d124ebff-94f0-444b-af07-ce95362fcc7d/ACZD-165/hhd800.com@ACZD-165.mp4`

The current code accepts all three because it deduplicates by path string. Since the strings differ, `accepted_files` contains three records. The rename step then receives `total=3`, so `build_video_filename` uses multi-disc naming and generates `ACZD-165-CD1.mp4`, `ACZD-165-CD2.mp4`, and `ACZD-165-CD3.mp4`.

This is incorrect. Search result paths under `[Search]` are virtual CloudDrive2 paths and must not be used for rename, move, copy, verification, or cleanup decisions.

## Source API

CloudDrive2 documents `GetOriginalPath` as the API to obtain the original path for a search result file:

- File: `docs/CloudDrive2_gRPC_API_Guide_zh-CN.md`
- Section: `GetOriginalPath`
- Description: `获取搜索结果文件的原始路径。`

The storage worker already exposes this through `provider.get_original_path(path)`.

## Design

### Real Path Required

Every CloudDrive2 search result must be normalized before it can become an accepted file.

If a result has `is_search_result=True`, `isSearchResult=True`, or its path contains `/[Search]`, the worker calls:

```python
provider.get_original_path(raw_path)
```

The result is accepted only if the returned original path is non-empty and does not contain `/[Search]`.

If the original path is empty, reject the result with reason `missing_original_path`.

If the original path still contains `/[Search]`, reject the result with reason `virtual_search_path`.

Non-search results that already have real paths can be evaluated directly, but they are still deduplicated against resolved search results.

### Deduplication

Deduplication uses the resolved real path. The first accepted file for a resolved path is kept. Later results with the same resolved path are rejected with reason `duplicate_resolved_path`.

This means the three `ACZD-165` records in the log become one accepted file and two rejected duplicate records.

### Search Logs

Search logs must show both the CloudDrive2 result and the normalized decision:

- `raw_results`: original CloudDrive2 search or list result.
- `resolved_results`: normalized path after `GetOriginalPath`.
- `accepted_files`: deduplicated real files.
- `rejected_files`: rejected candidates and reasons.

Rejected entries should include:

- `name`
- `raw_path`
- `resolved_path`
- `size`
- `reason`

The new rejection reasons are:

- `missing_original_path`
- `virtual_search_path`
- `duplicate_resolved_path`

Existing reasons remain valid:

- `extension_not_allowed`
- `below_minimum_size`
- `movie_code_mismatch`
- `outside_task_download_folder`
- `search_error`
- `list_error`

### Downstream Behavior

`accepted_files` must never contain `/[Search]`.

`scan_files`, `select_videos`, `rename_files`, `move_files`, `verify_result`, and `cleanup_files` operate only on real paths.

If the deduplicated result contains one real video, `rename_selected_videos` receives `total=1`, so `build_video_filename` returns `ACZD-165.mp4` instead of `ACZD-165-CD1.mp4`.

Only multiple distinct real video files can trigger `-CD1`, `-CD2`, and later disc suffixes.

## Acceptance Criteria

- Search-result paths under `[Search]` must call `provider.get_original_path`.
- A search-result item with no original path must be rejected.
- A search-result item whose original path still contains `/[Search]` must be rejected.
- Multiple results resolving to the same real path must produce one accepted file.
- Duplicate resolved paths must be logged as `duplicate_resolved_path`.
- `accepted_files` in search logs must contain only real paths.
- A single real accepted file must be renamed without `-CD1`, `-CD2`, or `-CD3`.
- Distinct real video files still use existing multi-disc naming.

## Testing

Backend tests should cover:

- `find_scoped_video_files` calls `get_original_path` for `[Search]` results.
- `find_scoped_video_files` rejects a search result when `get_original_path` returns an empty string.
- `find_scoped_video_files` rejects a search result when `get_original_path` returns another `[Search]` path.
- `find_scoped_video_files` deduplicates three records that resolve to the same real path.
- Search log context contains `raw_path`, `resolved_path`, and `duplicate_resolved_path`.
- `rename_selected_videos` receives one accepted file after dedupe and generates a non-CD filename.

## Out of Scope

- Changing CloudDrive2 gateway method signatures.
- Changing magnet ordering.
- Changing storage task UI.
- Changing filename suffix rules for real multi-file videos.
