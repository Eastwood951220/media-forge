# Storage ListSubFiles Download Polling Design

## Context

Storage subtasks currently mix `SearchFiles` and recursive `list_files` when polling for downloaded video files. The latest log shows the first magnet already downloaded matching files under `/云下载/storage_子任务id`, but the worker rejected them because `SearchFiles` returned `[Search]` virtual paths and `GetOriginalPath` resolved them to `/115open/云下载/...`.

That resolved path was treated as outside the task download folder, then later accepted from `/云下载` root search. Rename then failed because CloudDrive2 operations received a path that was effectively doubled to `/115open/115open/...`. The failure caused the worker to continue to later magnets even though the first magnet had usable data.

## Goal

The normal download polling path must use real CloudDrive2 directory entries only. It should detect files that already exist inside `/云下载/storage_子任务id` and its subfolders, process them immediately, and stop trying additional magnets once the subtask succeeds or is skipped.

## Non-Goals

- Do not remove the recovery capability for existing CloudDrive2 tasks entirely.
- Do not change movie code parsing, suffix rules, storage mode selection, or target location rules beyond what is needed for reliable file discovery.
- Do not add unrelated storage features.

## Proposed Behavior

### Normal Magnet Polling

After a magnet is submitted, the worker polls only the task download folder:

1. Search root: `/云下载/storage_子任务id`
2. Method: `ListSubFileRequest` through the existing `provider.list_files()` / CloudDrive2 `GetSubFiles` wrapper
3. Recursion: walk child directories under the same task download folder
4. Accepted files: real video files that match configured extensions, minimum size, and the movie code
5. Rejected files: log explicit reasons such as extension mismatch, below minimum size, movie code mismatch, duplicate path, recursion limit, or list error

`SearchFiles` must not be called during this normal polling path. This prevents `[Search]` virtual paths, mounted search folders, and `/115open/...` resolved paths from entering rename, move, or copy operations.

### Poll Success

If recursive listing finds usable video files:

1. Stop the current poll loop immediately.
2. Continue to `scan_files`, `select_videos`, `rename_files`, `move_files`, `verify_result`, and `cleanup_files`.
3. If move/copy determines all target files already exist, mark the subtask as skipped.
4. Whether the subtask becomes completed or skipped, do not attempt later magnets.

### Poll Exhaustion

If recursive listing finds no usable video file after the configured download poll count:

1. Treat the current magnet attempt as failed.
2. Start the next magnet only if the subtask has not exceeded the configured maximum magnet attempts.
3. Do not search `/云下载` root as part of the normal success path.

### Recovery Search

`SearchFiles + GetOriginalPath` is reserved for recovery flows only:

- CloudDrive2 reports that the offline download task already exists.
- The worker is explicitly trying to recover a previously downloaded file after the task download folder could not provide usable files.

Recovery search order:

1. Recursively list `/云下载/storage_子任务id` first.
2. Only if that fails, search or list `/云下载` root according to the recovery helper.
3. Any search result must be resolved through `GetOriginalPath`.
4. Resolved paths must be converted or normalized to a CloudDrive2 operation path before rename, move, or copy.
5. Virtual paths containing `[Search]` are never accepted.

## Logging

Each download polling attempt should write a structured log entry with:

- `search_method`: `list_sub_files`
- `search_path`: the task download folder
- `current_path`: the directory currently being listed
- `search_scope`: `task_download_folder`
- `poll_index`
- `max_poll_count`
- `raw_entries`: direct entries returned by `ListSubFileRequest`
- `accepted_files`
- `rejected_files`

Recovery search logs should use a distinct `search_scope`, such as `recovery_task_download_folder` or `recovery_download_root`, so the task timeline makes it clear whether a result came from normal polling or recovery.

## Error Handling

- A `ListSubFileRequest` failure for one directory is logged with `reason=list_error` and should not crash the worker unless the root task download folder cannot be listed repeatedly through the configured poll count.
- Recursive traversal must track visited directory paths to avoid infinite loops and recursion depth errors.
- Directory paths outside `/云下载/storage_子任务id` are rejected in normal polling.
- Paths with provider-specific mount prefixes such as `/115open/...` must not be passed directly to rename, move, or copy unless the CloudDrive2 gateway explicitly expects that format.

## Testing

Add or update backend tests around the storage worker file discovery helpers:

1. A real nested file under `/云下载/storage_子任务id/ACZD-165/hhd800.com@ACZD-165.mp4` is accepted by `ListSubFileRequest` recursion.
2. `SearchFiles` is not called during normal download polling.
3. A `[Search]` virtual path is rejected outside recovery.
4. Duplicate real paths are accepted once and do not produce `-CD2` or `-CD3` for a single real video.
5. When usable files are found on the first magnet, later magnets are not attempted.
6. When all target files already exist, the subtask is marked skipped and later magnets are not attempted.
7. Recursive listing cannot exceed visited-path protection or trigger maximum recursion depth errors.

## Acceptance Criteria

- The log scenario where the first magnet has `ACZD-165` data under `/云下载/storage_子任务id` succeeds or skips without trying later magnets.
- Normal polling logs show `search_method=list_sub_files`, not `search_files`.
- Rename, move, and copy operate on real CloudDrive2 paths, never `[Search]` paths.
- `/115open/115open/...` path construction no longer occurs.
- The task timeline still shows the same storage steps: prepare, submit magnet, waiting download, scan files, select videos, rename files, move files, verify result, cleanup files, done.
