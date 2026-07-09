# Storage Index Cache Sync Design

## Context

Manual storage status sync currently probes CloudDrive2 directories per movie. This is accurate for small selections, but it does not scale when a large batch contains many movies, categories, and known code-folder suffixes.

For example, syncing movies under `target_folder=/嘿嘿/日本` can expand into many remote directory listings:

```text
movie count * category count * suffix count
```

Using `forceRefresh=true` for every candidate directory can create thousands of CloudDrive2 refresh requests and cause request timeouts. Using only cached listings avoids the timeout but can miss files that were manually moved into cloud storage after CloudDrive2 cached the directory.

CloudDrive2's documented APIs do not expose a single method that returns a full recursive directory tree with file details:

- `GetSubFiles` lists one directory level.
- `GetSearchResults` searches by keyword.
- `GetDirCacheTable` returns cache metadata, not child file entries.
- `WalkThroughFolderTest` returns aggregate counts, not a tree.

Therefore, Media Forge should build its own local storage index by traversing CloudDrive2 in controlled batches, then use that index for bulk movie storage status sync.

## Goal

Make bulk movie storage status sync fast and stable by matching movies against a local CloudDrive storage index instead of refreshing thousands of remote directories during the sync request.

## Non-Goals

- Do not recursively force-refresh every movie or code-folder candidate during bulk sync.
- Do not depend on undocumented CloudDrive2 internals for file listings.
- Do not change storage task download, move, copy, rename, or target planning behavior.
- Do not require a frontend redesign; only add controls or status indicators directly needed for index refresh and sync clarity.

## Recommended Approach

Add a local storage index cache generated from CloudDrive2 `GetSubFiles` traversal.

The index refresh flow should:

1. Start at configured `target_folder`, such as `/嘿嘿/日本`.
2. List immediate category directories.
3. List code folders under each category.
4. List files under each code folder.
5. Record only video files that pass the existing extension and minimum-size rules.
6. Stream matching records into a temporary JSONL file while refresh is running.
7. Atomically replace the completed JSONL file only after the refresh finishes.

Bulk movie storage status sync should then:

1. Load the latest local index.
2. Match movie codes against indexed video paths and filenames.
3. Update `storage_summary.locations` without issuing per-movie CloudDrive directory listings.
4. Include index metadata in the response or logs, especially index creation time and whether the index was used.

Single-movie or small selected sync can still use remote lookup when needed, but remote force refresh must be bounded.

## Refresh Modes

### Normal Index Refresh

Use `forceRefresh=false` for traversal. This is the default and safe path for large libraries.

This mode is fast and avoids overloading CloudDrive2, but it may not immediately see manually moved files if CloudDrive2 still has stale directory cache.

### Targeted Forced Refresh

Use forced refresh only for bounded paths selected by the user or inferred from a small request:

- A single movie's expected category/code folders.
- One selected category folder.
- The target root and immediate categories only, with a strict limit.

Do not force-refresh every code folder in a large index refresh.

### Bulk Sync

Bulk sync must not force-refresh CloudDrive2. It should use the local index and report if the index is missing, stale, or still being built.

## Data Model

Use a local index file under runtime configuration storage. JSONL is preferred because it can be written and read incrementally:

```json
{"code":"ALDN-206","path":"/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4","target_folder":"/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U","storage_location":"巨乳|熟女|BBW","file_name":"ALDN-206-U.mp4","size":524288000,"indexed_at":"2026-07-09T00:00:00Z"}
```

Store index metadata separately or as a small companion JSON file:

```json
{"target_folder":"/嘿嘿/日本","started_at":"2026-07-09T00:00:00Z","completed_at":"2026-07-09T00:03:00Z","status":"completed","category_count":20,"code_folder_count":12000,"video_count":11800,"force_refresh_mode":"none"}
```

During refresh, write records to a temporary file:

```text
storage_index.jsonl.tmp
```

The running refresh should append each accepted video record to the temporary JSONL file and flush it promptly. This makes partial progress visible on disk and prevents a long HTTP request or process interruption from leaving no index data at all.

The completed index remains:

```text
storage_index.jsonl
```

Bulk movie storage sync must read only `storage_index.jsonl` when metadata status is `completed`. It must not use `storage_index.jsonl.tmp` for official storage status decisions, because the temporary file can represent a partial scan and would incorrectly mark unscanned movies as not stored.

The metadata file should expose running progress:

```json
{"target_folder":"/嘿嘿/日本","started_at":"2026-07-09T00:00:00Z","completed_at":null,"status":"running","category_count":8,"code_folder_count":4200,"video_count":4100,"current_path":"/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U","force_refresh_mode":"none"}
```

## Matching Rules

Reuse the current video validation rules:

- File extension must be in configured `video_extensions`.
- File size must be at least configured `minimum_video_size_mb`.
- File name should start with the movie code.

For folder variants, keep supporting known suffixes:

```text
CODE
CODE-C
CODE-U
CODE-UC
```

The index record should store the normalized base movie code separately so bulk sync can do direct dictionary lookup instead of scanning all indexed rows per movie.

## Error Handling

Index refresh should be resumable enough to avoid corrupting the existing usable index:

- Create or truncate `storage_index.jsonl.tmp` at refresh start.
- Append accepted video records to `storage_index.jsonl.tmp` as they are discovered.
- Write metadata with `status=running` while refresh is active, including current path and counters.
- Replace the previous completed index only after refresh completes.
- Delete stale temporary files after successful replacement.
- If refresh fails, keep the previous completed index available and record the failure in metadata.

Directory listing failures should be recorded with path and error message, then the refresh should continue where reasonable. A full target-root failure should fail the refresh.

Bulk sync behavior:

- If a completed index exists, use it.
- If no completed index exists, return a clear error asking the user to build the index first.
- If the index is stale, still allow sync but include stale-index metadata.

## API Surface

Add backend endpoints under the storage module:

- `POST /api/storage/index/refresh` starts or runs an index refresh.
- `GET /api/storage/index/status` returns metadata for the latest refresh.

Movie storage sync should accept or infer an index-backed mode for large batches. The default for bulk sync should be index-backed.

Small selected sync may continue to call remote lookup, but must avoid unlimited forced refresh.

## UI Behavior

Add minimal UI controls where storage sync is already exposed:

- Show storage index status: never built, running, completed, failed, completed time, video count.
- Add a button to refresh the storage index.
- When bulk syncing, show that results come from the local index and display the index timestamp.

No visual redesign is required.

## Testing

Backend tests should cover:

- Index refresh traverses `target_folder -> category -> code folder -> video file`.
- Index refresh streams accepted records to `storage_index.jsonl.tmp` while running.
- Index refresh replaces the completed index atomically only after completion.
- Bulk sync ignores `storage_index.jsonl.tmp` and reads only a completed `storage_index.jsonl`.
- Bulk movie storage sync uses the local index without calling per-movie remote listings.
- Missing index returns a clear error for index-backed bulk sync.
- Failed refresh preserves the previous completed index.
- Targeted single-movie forced refresh remains bounded.

Frontend tests should cover only the minimal status/control behavior if UI changes are added.

## Migration Notes

Existing `storage_summary` records remain valid. The local index is derived data and can be rebuilt at any time.

No database migration is required unless implementation chooses to store index metadata in PostgreSQL. File-based metadata is sufficient for the initial implementation.
