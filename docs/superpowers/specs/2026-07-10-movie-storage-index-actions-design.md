# Movie Storage Index Actions Design

## Context

Storage index refresh currently lives on the storage configuration page:

- `frontend/src/pages/storage/config/StorageConfigPage.tsx`
- `frontend/src/api/storage/storageIndex/index.ts`
- `backend/app/modules/storage/index/router.py`
- `backend/app/modules/storage/index/refresh.py`
- `backend/app/modules/storage/index/store.py`

The movie list currently has one toolbar action, `同步存储状态`, which calls
`/api/content/movies/storage-sync` through `syncMovieStorageStatus()`. The
backend sync service currently prefers the storage index but falls back to
CloudDrive2 for a single movie when the index is missing.

The storage index file is currently JSONL. The new requirement is to move index
actions into the movie list, support full and incremental index refreshes,
make normal storage sync read only from the index, and add a per-row CD2 sync
action that refreshes one movie directly from CloudDrive2 and updates the index.

## Goals

- Move storage index controls out of storage configuration and into the movie
  list.
- Add a movie-list Dropdown for `全量索引` and `增量索引`.
- Store the index as a tree JSON document instead of JSONL.
- Full index refresh scans:
  - the configured target folder's child folders;
  - each child folder's child folders;
  - videos inside those second-level folders.
- Incremental index refresh lists category folders and code folders, skips code
  folders already present in the old index tree, and scans videos only inside
  newly discovered code folders.
- Normal movie-list storage sync reads only the local index file and never calls
  CloudDrive2.
- CD2 sync is a single-row table action only. It does not support bulk sync or
  filter-wide sync.
- CD2 sync updates both the movie storage status and the storage index tree.

## Non-Goals

- No database schema changes.
- No background job queue for index refresh.
- No multi-row CD2 sync.
- No CloudDrive2 sync in the movie-list toolbar.
- No changes to storage task push behavior.

## UX Design

### Storage Configuration Page

Remove the `存储索引` card from `StorageConfigPage`. The page remains focused on
provider connection, directory, execution, and filtering settings.

### Movie List Toolbar

Add a toolbar Dropdown named `存储索引` with two actions:

- `全量索引`
- `增量索引`

Keep the existing storage status sync behavior in the toolbar, but rename the
button to `索引同步` to make the data source explicit. This action supports the
current selection/filter behavior and reads only the local index.

### Movie List Row Actions

Add a single-row action named `CD2同步` in the movie table operation column.
It calls a direct CloudDrive2 sync endpoint for that row only. It is not
available as a bulk action.

After a successful row CD2 sync, refresh the movie list so the row's
`storage_status` and `storage_summary` are visible.

## Backend Design

### Index Tree Format

Replace JSONL storage with one tree JSON file at the existing
`RuntimeConfigPaths.storage_index_file` path. The default filename can remain
`storage_index.jsonl` during implementation for compatibility with current
path plumbing, but the file content becomes JSON. A later cleanup may rename
the file to `.json`.

Tree shape:

```json
{
  "version": 1,
  "target_folder": "/Movies",
  "indexed_at": "2026-07-10T00:00:00+00:00",
  "categories": {
    "巨乳|熟女|BBW": {
      "path": "/Movies/巨乳|熟女|BBW",
      "code_folders": {
        "ALDN-206-U": {
          "path": "/Movies/巨乳|熟女|BBW/ALDN-206-U",
          "code": "ALDN-206",
          "videos": [
            {
              "path": "/Movies/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4",
              "file_name": "ALDN-206-U.mp4",
              "size": 524288000,
              "indexed_at": "2026-07-10T00:00:00+00:00"
            }
          ]
        }
      }
    }
  }
}
```

`StorageIndexStore.load_index_by_code()` remains the stable read interface for
movie sync. It flattens the tree into `dict[str, list[StorageIndexRecord]]`.

### Full Refresh

`StorageIndexRefreshService.refresh(config, provider, mode="full")`:

1. Writes running metadata with `force_refresh_mode="full"`.
2. Starts an empty tree.
3. Lists `target_folder`.
4. For each child directory, treats it as a storage category.
5. Lists each category directory.
6. For each second-level directory, treats it as a code folder.
7. Lists each code folder and stores matching videos.
8. Replaces the index tree atomically and writes completed metadata.

### Incremental Refresh

`StorageIndexRefreshService.refresh(config, provider, mode="incremental")`:

1. Loads the existing completed index tree. If none exists, behaves as full
   refresh.
2. Lists `target_folder`.
3. Lists every category directory to discover code folders.
4. If a code folder path already exists in the old tree, skips listing videos
   inside that code folder.
5. If a code folder path is new, lists videos inside it and appends them to the
   tree.
6. Writes the merged tree atomically and updates metadata.

This still touches category and code-folder listings because that is required
to discover new data, but it does not traverse old code-folder video contents.

### Index Sync

`/api/content/movies/storage-sync` becomes index-only:

- selected movie IDs: match selected movies against `StorageIndexStore.load_index_by_code()`;
- no selection: match filtered movie set against the same index;
- if the index is missing or not completed, return an error telling the user to
  build the storage index first;
- do not call `StorageConfigService.open_provider()` and do not access CD2.

### Single-Row CD2 Sync

Add a direct-sync endpoint for one movie:

`POST /api/content/movies/{movie_id}/storage-sync/cd2`

Behavior:

1. Load the movie.
2. Open CloudDrive2 through `StorageConfigService`.
3. Run the existing direct scan logic for that one movie.
4. Update the movie storage status.
5. Upsert found locations into the storage index tree.
6. Commit and publish the existing movie storage realtime update.

If no locations are found, update the movie status to `not_stored`. Do not
remove existing unrelated index records unless they match the same movie code
and scanned target folders.

## Frontend Design

### API

Update `frontend/src/api/storage/storageIndex/index.ts`:

- `refreshStorageIndex(mode: 'full' | 'incremental')`.

Update `frontend/src/api/movie/index.ts`:

- keep `syncMovieStorageStatus(payload)` for index sync;
- add `syncMovieStorageStatusFromCd2(movieId: string)`.

### Movie List

`MovieListPage` toolbar:

- Dropdown button `存储索引`
  - `全量索引`
  - `增量索引`
- Button `索引同步`
  - Uses current selected rows or filters.
  - Shows success count from the index-only sync response.

Movie table row action:

- Button `CD2同步`
  - Calls `syncMovieStorageStatusFromCd2(record.id)`.
  - Shows row/action loading if local patterns support it; otherwise global
    message feedback is acceptable.
  - Reloads the list after success.

Storage config page:

- Remove index status loading and refresh UI.
- Keep connection test and save behavior unchanged.

## Error Handling

- Index sync without a completed index returns a clear backend error. The
  frontend displays it through the existing request error path.
- Full or incremental index refresh writes `failed` metadata when refresh
  raises.
- Incremental refresh falls back to full only when no completed tree exists.
- CD2 row sync errors do not modify the movie status or index tree unless the
  scan completed and the result is known.

## Testing

Backend:

- Full refresh writes tree JSON and `load_index_by_code()` flattens it.
- Incremental refresh skips old code folders and scans only new code folders.
- `/api/storage/index/refresh` accepts `mode=full` and `mode=incremental`.
- `/api/content/movies/storage-sync` never opens CD2 and fails when index is
  missing.
- `POST /api/content/movies/{movie_id}/storage-sync/cd2` scans one movie and
  upserts found locations into the tree.

Frontend:

- Storage config page no longer renders `存储索引`.
- Movie list renders `存储索引` Dropdown with `全量索引` and `增量索引`.
- Toolbar `索引同步` calls the index-sync API.
- Row `CD2同步` calls the single-movie CD2 API.
- No bulk CD2 action appears when rows are selected.

## Acceptance Criteria

- Users manage full and incremental storage indexes from the movie list.
- Normal movie-list storage sync uses only the local tree index.
- CD2 sync exists only as a per-row operation.
- CD2 sync updates the movie and the index tree.
- Incremental index refresh does not scan videos inside old code folders.
- Storage configuration no longer contains storage index controls.
