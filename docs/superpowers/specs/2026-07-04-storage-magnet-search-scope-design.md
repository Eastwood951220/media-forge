# Storage Magnet Search Scope Design

## Goal

Fix storage subtask magnet execution so one magnet is fully processed before the next magnet is submitted, and make file discovery deterministic and auditable through detailed search logs.

## Problem

The attached log shows the first magnet for `ACZD-165` downloading and then discovering 25 video files. Many discovered files came from unrelated paths such as historical `storage_*` folders and `/云下载/[Search]` entries for other movie codes including `CHERD-105` and `MIDA-628`. Those files were then renamed as `ACZD-165-CD*` and moved into the target folder.

The current search flow is too broad. It can search `/云下载` and accept global search results before proving that the current magnet failed in the current subtask folder. The logs also do not show enough detail about search terms, search paths, raw search results, resolved original paths, and filtering decisions.

## Confirmed Behavior

For each storage subtask, the worker processes magnet candidates sequentially:

1. Submit one magnet.
2. Poll and search for files for that magnet.
3. Run scan, select, rename, move or copy, verify, and cleanup.
4. Stop the magnet loop if the magnet succeeds, is skipped due to existing targets, or reaches another terminal skipped state.
5. Try the next magnet only after the current magnet has failed.

The file search order is fixed:

1. Search `/云下载/storage_子任务id`.
2. If no usable file is found after the configured poll limit, search `/云下载`.

Root-folder search is a recovery path. It must not pull unrelated historical files into the current task.

## Search Rules

The worker searches with the current movie code as the primary search term. For example, task `ACZD-165` searches for `ACZD-165`.

Every search attempt logs:

- `search_term`: the string being searched.
- `search_path`: the CloudDrive2 path being searched.
- `search_scope`: `task_download_folder` or `download_root`.
- `search_method`: `search_files` or `recursive_list`.
- `raw_results`: file names and paths returned by CloudDrive2.
- `resolved_results`: original paths returned from `get_original_path` for CloudDrive2 search-result entries.
- `accepted_files`: files accepted as usable videos.
- `rejected_files`: files rejected with a reason.

Accepted files must satisfy all of these:

- The file extension is in `video_extensions`.
- The size is at least `minimum_video_size_mb`.
- The file belongs to the current movie code. A file whose name and resolved path only identify a different code is rejected.
- During task-folder search, the resolved path must stay under `/云下载/storage_子任务id`.
- During root-folder recovery search, global search results are allowed only when the resolved file path or name matches the current movie code. Files for other movie codes are rejected even if CloudDrive2 returns them.

Rejected files are logged with one of these reasons:

- `extension_not_allowed`
- `below_minimum_size`
- `movie_code_mismatch`
- `outside_task_download_folder`
- `search_error`
- `list_error`

## Polling Design

The poll loop searches one scope at a time:

1. For poll indexes `1..download_max_poll_count`, search only `/云下载/storage_子任务id`.
2. If no accepted file is found, run a root recovery search at `/云下载`.
3. If root recovery finds accepted files, continue the pipeline with those files.
4. If root recovery also finds no accepted files, the current magnet fails and the next magnet can start.

Root recovery should not reset or overlap with the current magnet submission. It runs after the task-folder poll has failed.

## Logging Examples

Task-folder search:

```json
{
  "message": "查找下载文件",
  "context": {
    "search_term": "ACZD-165",
    "search_path": "/云下载/storage_041e238f-4ce1-4845-84e1-7eaebdc8e14a",
    "search_scope": "task_download_folder",
    "search_method": "search_files",
    "raw_results": [
      {"name": "ACZD-165.mp4", "path": "/云下载/storage_041e238f-4ce1-4845-84e1-7eaebdc8e14a/ACZD-165.mp4", "size": 4770615244}
    ],
    "accepted_files": [
      {"name": "ACZD-165.mp4", "path": "/云下载/storage_041e238f-4ce1-4845-84e1-7eaebdc8e14a/ACZD-165.mp4", "size": 4770615244}
    ],
    "rejected_files": []
  }
}
```

Root recovery rejection:

```json
{
  "message": "查找下载文件",
  "context": {
    "search_term": "ACZD-165",
    "search_path": "/云下载",
    "search_scope": "download_root",
    "search_method": "search_files",
    "raw_results": [
      {"name": "MIDA-628.mp4", "path": "/云下载/[Search]MIDA-628/MIDA-628.mp4", "size": 1743419118}
    ],
    "resolved_results": [
      {"name": "MIDA-628.mp4", "path": "/云下载/storage_19ee55c5-15e7-4ca5-9fbd-dcf314d7abe9/MIDA-628/MIDA-628.mp4", "size": 1743419118}
    ],
    "accepted_files": [],
    "rejected_files": [
      {
        "name": "MIDA-628.mp4",
        "path": "/云下载/storage_19ee55c5-15e7-4ca5-9fbd-dcf314d7abe9/MIDA-628/MIDA-628.mp4",
        "reason": "movie_code_mismatch"
      }
    ]
  }
}
```

## Components

### Search Scope Planner

The worker builds two search scopes for each magnet:

- `task_download_folder`: `/云下载/storage_子任务id`
- `download_root`: `/云下载`

The task folder scope is always searched first. The root scope is searched only after task-folder polling fails.

### Search Logger

Search logging stays in backend storage task JSONL logs through `context.log`. The log payload is structured enough to support debugging without reading backend server logs.

### File Filter

The filter accepts only files that satisfy extension, size, scope, and movie-code checks. The filter returns both accepted and rejected files so logs can explain why each candidate did or did not continue through the pipeline.

### Magnet Loop

The magnet loop remains sequential. No second magnet is submitted until the first magnet returns a terminal result:

- success
- skipped
- failed after configured polling and processing attempts

## Error Handling

CloudDrive2 `search_files`, `get_original_path`, and `list_files` errors do not crash the whole subtask during search. They are logged as rejected search attempts with `search_error` or `list_error`, and the worker continues according to the configured search order.

If no accepted files are found after both scopes are searched, the current magnet fails and the worker may try the next magnet.

If accepted files are found but no main video can be selected, the current magnet fails and the worker may try the next magnet.

If the current magnet succeeds or is skipped due to existing target files, the worker stops and does not submit later magnets.

## Testing

Backend tests should cover:

- A magnet only searches `/云下载/storage_子任务id` during normal polling.
- Root `/云下载` search happens only after task-folder polling reaches the configured maximum.
- Search logs include term, path, scope, method, raw results, resolved results, accepted files, and rejected files.
- Root search rejects files whose name and resolved path belong to a different movie code.
- The magnet loop does not submit a second magnet while the first magnet is still polling.
- The magnet loop submits the second magnet only after the first magnet fails.
- The magnet loop stops after success or skipped terminal outcomes.

## Out of Scope

- Changing frontend UI for log display.
- Changing CloudDrive2 gateway method signatures.
- Changing storage configuration fields.
- Changing magnet weight ordering.
