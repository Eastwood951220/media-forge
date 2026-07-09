# Storage Sync Category Discovery Design

## Context

Manual movie storage status sync currently checks exact target folders derived from the configured storage target root, the movie source task storage location, and known code folder suffixes.

With `target_folder=/嘿嘿/日本`, a manually moved file at:

```text
/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4
```

can still show as `not_stored` because the sync path builder only checks folders shaped like:

```text
/嘿嘿/日本/<storage_location>/ALDN-206
/嘿嘿/日本/<storage_location>/ALDN-206-C
/嘿嘿/日本/<storage_location>/ALDN-206-U
/嘿嘿/日本/<storage_location>/ALDN-206-UC
```

If the real classification folder is not represented by the movie's source task storage location, the existing exact scan cannot discover the file.

## Goal

Make manual storage status sync recognize manually moved files that live one category directory below the configured target root, without changing storage task target planning or adding speculative storage features.

## Non-Goals

- Do not change how storage tasks download, move, copy, or rename files.
- Do not add frontend configuration for arbitrary scan depth.
- Do not relax video validation beyond the existing extension, minimum size, and movie-code prefix checks.
- Do not make sync recursively crawl the whole cloud drive.

## Recommended Approach

Keep the existing exact target-folder scan as the first pass. If that pass finds no matching videos, perform a bounded fallback discovery under the configured `target_folder`.

Fallback discovery:

1. List the configured target root, such as `/嘿嘿/日本`.
2. Consider only immediate child directories as category folders.
3. For each category folder, check known movie code folders: `CODE`, `CODE-C`, `CODE-U`, and `CODE-UC`.
4. List each matching code folder candidate and apply the existing `is_matching_video` validation.
5. Record any matches into `storage_summary.locations` with the actual discovered code folder as `target_folder`.

For the reported example, sync should discover:

```text
/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4
```

and mark the movie as `stored`.

## Data Flow

Manual sync continues to enter through `POST /api/content/movies/storage-sync`.

`sync_movies_storage_statuses` opens the configured CloudDrive2 provider and calls `sync_movie_storage_status` per movie. `sync_movie_storage_status` builds the exact candidate folders as it does now, then delegates scanning to the storage scan module.

The scan module should return:

- `checked_targets`: exact folders plus fallback candidate folders that were inspected.
- `found_locations`: discovered video locations, deduplicated later by existing `set_movie_storage_status`.

The persisted location for fallback discoveries should include:

- `path`: actual video path.
- `target_folder`: actual discovered code folder.
- `storage_location`: immediate category folder name, such as `巨乳|熟女|BBW`.
- `file_name`, `size`, `exists`, and `source` using the current shape.

## Error Handling

CloudDrive listing failures should remain non-fatal. A failure to list one exact folder, the target root, a category folder, or a code folder should skip that path and continue scanning remaining candidates.

If no matches are found after both exact scan and fallback discovery, the movie remains `not_stored`.

## Testing

Add backend tests around the existing movie storage sync coverage:

- A regression test where exact target folders are empty, `target_folder=/嘿嘿/日本`, and a category folder contains `ALDN-206-U/ALDN-206-U.mp4`; sync must mark the movie `stored`.
- Confirm `checked_targets` includes the discovered category/code folder candidate.
- Preserve the existing exact-folder behavior and video validation behavior.

## Implementation Notes

The change should stay in the storage status sync path:

- `backend/app/modules/content/movies/storage_scan.py` should own fallback category discovery.
- `backend/app/modules/content/movies/storage_status.py` should keep its public behavior and result shape.
- `backend/app/modules/content/movies/storage_locations.py` should keep exact target generation unchanged unless a small helper is needed for suffix reuse.

This keeps the change local to status synchronization and avoids changing task creation, worker planning, or CloudDrive configuration semantics.
