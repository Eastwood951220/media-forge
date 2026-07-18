# Storage Multi-Target Task Design

## Context

Storage subtasks currently log and execute with only one target path in some multi-disk cases. The worker already has multi-target primitives:

- downloaded files can be copied to all targets except the last target, then moved to the last target;
- when a magnet task already exists and one target already has the normalized file, the file can be copied to missing targets;
- when the movie library already has a valid stored file, the file can be copied to requested targets.

The observed failure is earlier in the flow: task creation can persist only one `target_locations` entry, so the worker only receives one target path. In particular, batch task target resolution currently truncates source-task locations to the first location.

## Goal

Make `storage_mode=multiple` consistently mean "store this movie into every storage location derived from its source crawler tasks", for both single push and batch push.

When a multi-target task is created, the subtask should immediately show all target directories. During execution:

- if a valid movie storage file already exists, copy it into missing target folders;
- if the magnet already exists and any target folder has the expected file, copy it into missing target folders;
- if the magnet downloads normally, rename the video, copy it to every target except the final target, and move it to the final target.

## Non-Goals

- Do not add new storage providers or CloudDrive2 behavior.
- Do not add a frontend target picker for batch mode.
- Do not change filename normalization, magnet ordering, video selection, or VR folder insertion rules.
- Do not overwrite existing target files.

## Chosen Approach

Use `storage_mode` as the source of truth for target resolution at task creation time.

`resolve_target_locations()` should accept `storage_mode` and apply these rules:

- `storage_mode=multiple`: return all unique `storage_location` values from the movie's source crawler tasks, preserving source-task order.
- `storage_mode=single` with `source=single` and a valid `selected_storage_location`: return only that selected location.
- `storage_mode=single` with `source=batch`: return only the first source-task location, preserving existing batch single-disk behavior.
- `storage_mode=single` with `source=single` and no selected location: return all source-task locations, preserving the current tested behavior.
- no source-task locations: return an empty list and let worker planning fall back to the existing default target folder.

This keeps the durable subtask state accurate before the worker starts, so task details and logs show multiple target locations from creation onward.

## Data Flow

1. The frontend submits `storage_mode` as `single` or `multiple`.
2. `StorageTaskService` passes `storage_mode` into `StorageTaskCreator`.
3. `StorageTaskCreator` passes `storage_mode`, `source`, and `selected_storage_location` into `resolve_target_locations()`.
4. The subtask persists the resolved `target_locations`.
5. The worker calls `plan_storage_attempt()`, which turns every `target_locations` entry into a concrete `target_paths` entry under configured `target_folder`.
6. Existing worker flows operate on all `target_paths`.

## Existing File Behavior

For existing movie storage files, `copy_from_existing_movie_storage()` remains responsible for finding a valid source file:

- first from `movie.storage_summary`;
- then by scanning configured movie target folders;
- skipping files already inside the requested targets when selecting a copy source.

Once a source is found, every missing target folder is created and receives a copy. Targets that already have a valid file are skipped and recorded in the result.

## Magnet-Exists Behavior

When CloudDrive2 reports that the magnet task already exists and no new downloaded files are found, `handle_existing_target_fallback()` checks every target folder for the expected normalized filename.

- If all targets already contain the file, the subtask is skipped with `target_exists`.
- If the subtask is `storage_mode=multiple` and at least one target contains the file, the first existing target is used as the copy source for all missing targets.
- If no target contains the expected file, the existing failure flow continues.

## Normal Download Behavior

After a successful download, selected videos are renamed as they are today. `move_renamed_videos()` then handles all target paths:

- creates each target folder when `auto_create_target_folder=true`;
- skips individual target files that already exist;
- copies to every target before the final target;
- moves the source file to the final target;
- records copied and moved paths for verification and task details.

The final target is intentionally the last resolved source-task location.

## Error Handling

The design preserves current conservative failure behavior:

- existing-storage copy failures are logged as warnings and the magnet flow continues;
- target existence checks tolerate provider lookup errors as missing targets;
- copy or move results must pass `verify_moved_files()`;
- verification checks both moved and copied paths;
- if no file is moved or copied, the subtask fails instead of reporting success.

Existing target files are never overwritten.

## Tests

Focused backend tests should cover:

- `resolve_target_locations()` returns all source-task locations for `storage_mode=multiple` in batch mode.
- `resolve_target_locations()` keeps batch `storage_mode=single` limited to the first source-task location.
- `resolve_target_locations()` keeps single push with a selected location limited to the selected location.
- task creation persists multiple `target_locations` for batch multi-disk tasks and logs the same list in creation context.
- worker planning uses every persisted `target_locations` entry when no `selected_storage_location` is present.
- existing multi-target worker tests continue to prove copy-to-missing-target behavior, normal download copy/move behavior, and single-mode non-copy behavior.

Suggested focused verification:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_task_service_units.py backend/tests/test_storage_tasks_api.py backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_target_files.py -q
```
