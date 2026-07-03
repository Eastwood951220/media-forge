# Storage Push Tasks Design

## Context

Media Forge is migrating and optimizing storage push behavior from the
original Jav Scrapling project. The current project already has:

- CloudDrive2 storage configuration and gateway wiring.
- movie records with `source_task_ids`, magnets, weights, selected magnet flags,
  and `storage_summary`.
- crawler run records backed by PostgreSQL, Redis runtime state, stop/restart
  controls, and realtime EventSource updates.
- a generic `/api/events/stream` event bus for user-scoped realtime events.

This design adds storage push tasks without introducing unrelated product
features. It preserves the original storage worker pipeline where useful, but
adapts the model to the new requirements: every single or batch push creates a
main task, and every selected movie creates one independent subtask.

## Goals

- Add single and batch storage push flows from the movie list.
- Create a main task for every push request, including single movie pushes.
- Create one subtask per selected movie, including skipped subtasks.
- Run all storage work through Redis-backed task dispatch.
- Track main task totals: total, success, failed, skipped.
- Support main task stop and restart, following crawler run record patterns.
- Push realtime status to movie list, main task list, main task detail, and
  subtask detail through EventSource.
- Reuse and improve the original Jav Scrapling storage worker steps.
- Use CloudDrive2 search and original-path APIs when recovering existing files.

## Non-Goals

- No new media sources or crawler features.
- No speculative storage providers beyond the existing CloudDrive2 integration.
- No hard interruption of a currently executing storage subtask.
- No background scheduler beyond Redis dispatch for explicitly created tasks.

## Data Model

Add `storage_main_tasks`:

- `id`: UUID primary key, exposed as the main task id.
- `alias`: user-provided alias or generated alias.
- `display_name`: alias used in lists.
- `source`: `single` or `batch`.
- `storage_mode`: `single` or `multiple`.
- `status`: `queued`, `running`, `stopping`, `stopped`, `completed`, `failed`.
- `total_count`, `success_count`, `failed_count`, `skipped_count`.
- `config_snapshot`: storage config at task creation.
- `created_by`: user id.
- `queued_at`, `started_at`, `finished_at`.
- `error_message`.

Add `storage_sub_tasks`:

- `id`: UUID primary key, exposed as the subtask id.
- `main_task_id`: foreign key to `storage_main_tasks`.
- `movie_id`: foreign key to `movies`.
- `movie_code`, `movie_title`.
- `status`: `queued`, `running`, `skipped`, `completed`, `failed`.
- `step`: `prepare`, `submit_magnet`, `cloud_download`, `scan_files`,
  `select_main_video`, `rename_files`, `move_files`, `verify_result`,
  `cleanup_files`, `completed`.
- `storage_mode`: copied from the main task.
- `selected_storage_location`: single-mode chosen target location, if any.
- `target_locations`: resolved storage locations for this movie.
- `download_path`: `download_root_folder/storage_<subtask_id>`.
- `target_paths`: final target directories.
- `magnet_attempts`: ordered attempts with magnet id/url, tags, weight, status,
  error, source path, selected files, and timestamps.
- `current_magnet_id`, `current_magnet_url`.
- `renamed_files`, `moved_files`, `skipped_files`.
- `result`: final files and verification details.
- `skip_reason` and `error_message`.
- `queued_at`, `started_at`, `finished_at`.

Add indexes for main task status/created time, subtask main/status, subtask
movie/status, and subtask created time.

The `movies.storage_summary` field remains the movie-facing denormalized state.
It is updated when subtask state changes and stores at least:

- `last_main_task_id`
- `last_sub_task_id`
- `last_status`
- `current_step`
- `storage_mode`
- `target_locations`
- `final_files`
- `error_message`
- `updated_at`

## Storage Configuration

Keep existing storage configuration fields, including:

- `download_root_folder`
- `target_folder`
- `download_max_poll_count`
- `minimum_video_size_mb`
- `video_extensions`

Add:

- `magnet_max_attempts_per_subtask`: maximum number of magnet candidates a
  subtask may try. This works alongside `download_max_poll_count`, which limits
  polling for each individual magnet.

## Task Creation

Both single and batch push use the same backend task creation service.

Default alias format:

`云存储_YYYYMMDDHHMMSS_<unique_sequence>`

Every selected movie creates a subtask. Movies that cannot run still create a
subtask with status `skipped`, so the main task accurately records what the user
selected.

Creation-time skipped reasons include:

- movie is marked as skipped.
- an active storage subtask already exists for the movie.
- movie is already completed and the request does not request a repush.
- no usable magnet exists.
- no `source_task_ids`.
- no related crawler task has a usable `storage_location`.

The service snapshots storage config, movie fields, magnet candidates, source
task ids, and resolved storage locations when creating tasks. Later config
changes do not alter already-created tasks.

## Storage Modes

`single` means the movie should have one final copy in cloud storage.

- Single movie push shows a target folder dropdown in the confirmation modal.
- The dropdown options come from the movie `source_task_ids`, mapped to each
  related crawler task's `storage_location`.
- The default dropdown value is the first usable `storage_location`.
- Batch push does not ask per-row target choices. Each movie defaults to its
  first usable `storage_location`.
- If the selected/default target already contains the expected final files, the
  subtask is marked `skipped` with reason `target_exists`.

`multiple` means every usable `storage_location` from the movie's
`source_task_ids` must contain a final copy.

- Locations are resolved by loading related crawler tasks and reading
  `storage_location`.
- Empty values are ignored.
- Duplicate locations are removed while preserving order.
- If all target locations already contain the expected final files, the subtask
  is marked `skipped` with reason `all_targets_exist`.
- If only some targets already contain files, the worker fills only the missing
  targets.

## Target Path Rules

Final target directory:

`target_folder / storage_location / code_folder`

`code_folder` is derived from the final base filename without the `-CDn` part.

Examples:

- `ABC-123-C.mp4` moves to `target_folder/storage_location/ABC-123-C/`.
- `ABC-123-C-CD1.mp4` and `ABC-123-C-CD2.mp4` move to
  `target_folder/storage_location/ABC-123-C/`.

The move step checks and creates missing parent folders from root to target. It
then verifies the target directory exists before copying or moving files.

## Magnet Candidate Order

For each subtask:

1. Try the selected best magnet first, if the movie has `MovieMagnet.selected`.
2. If that magnet fails, exclude it from remaining candidates.
3. Try the remaining magnets ordered by `weight` descending.
4. Stop immediately after one magnet completes the required pipeline.
5. Fail the subtask only after all allowed candidates fail or
   `magnet_max_attempts_per_subtask` is reached.

A magnet is successful only if the worker downloads or finds files and then
identifies at least one main video. Merely finding files in the download folder
is not enough.

## Worker Pipeline

The storage worker claims main tasks from Redis and processes queued subtasks in
order.

Subtask steps:

1. `prepare`
   - Validate movie id and task snapshot.
   - Resolve target paths from storage mode and locations.
   - Build the download path:
     `download_root_folder/storage_<subtask_id>`.
   - Build ordered magnet candidates.
   - Check whether required target files already exist.
   - Mark the subtask skipped before download when single mode's selected
     target already has the final files or multiple mode has all final targets.

2. `submit_magnet`
   - Ensure the download folder exists.
   - Submit the current magnet through CloudDrive2 offline download.
   - If CloudDrive2 reports the task already exists, enter existing-file
     recovery instead of failing immediately.

3. `cloud_download`
   - Poll the subtask download folder up to `download_max_poll_count`.
   - Poll intervals use the configured min/max delay.
   - Download timeout or empty folder after the limit fails the current magnet
     attempt, not necessarily the whole subtask.

4. `scan_files`
   - Scan downloaded files recursively.
   - Record all files, directories, sizes, extensions, and source paths.
   - An empty scan fails the current magnet attempt.

5. `select_main_video`
   - Filter by configured video extensions and minimum video size.
   - Select one or more main videos.
   - If no main video is identified, fail the current magnet attempt and try the
     next magnet.

6. `rename_files`
   - Rename selected videos according to the naming policy.
   - Preserve idempotency when a target filename already exists.

7. `move_files`
   - Ensure every target parent and final folder exists.
   - Check every target for the expected final files.
   - Skip copy/move for files already present and valid.
   - In multiple mode, copy to all missing targets except the last missing
     target, then move to the last missing target.
   - In single mode, move to the selected/default target if that target is
     missing the expected files.

8. `verify_result`
   - Confirm required target files exist in all required target folders.
   - Multiple mode requires every target location to have the final files.
   - Single mode requires one final target to have the final files.

9. `cleanup_files`
   - Delete the subtask temporary folder when possible.
   - Cleanup errors are logged but do not turn an otherwise successful subtask
     into a failure.

10. `completed`
    - Mark the subtask completed and update main task counts.

## Existing File Recovery

When `submit_magnet` fails because CloudDrive2 reports that the offline task
already exists, the worker searches for reusable source files before moving to
the next magnet.

Search order:

1. Download root and its subfolders.
2. Related `storage_location` folders and their subfolders, in resolved target
   order.

Preferred lookup uses CloudDrive2 search APIs:

- `GetSearchResults(SearchRequest)` searches by movie code, expected base
  filename, final filenames, and current magnet name where useful.
- If a returned `CloudDriveFile` is a search result path, call
  `GetOriginalPath(FileRequest)` to get the real original path.
- Candidate files are filtered by extension, size, movie code/name match, and
  main-video selection rules.

Fallback lookup uses recursive `GetSubFiles` traversal when search is
unavailable or returns no usable files.

The CloudDrive2 integration should expose this through the shared gateway by
adding `search_files(...)` and `get_original_path(...)` methods. Storage worker
code should depend on the gateway interface, not directly on generated gRPC
stubs.

If a reusable source file is found, the worker continues with target existence
checks, folder creation, copy/move, and verification. If no usable source file
is found in order, the current magnet attempt fails and the worker tries the
next magnet candidate.

For multiple mode, the worker fills missing target locations in order. If all
target locations already have valid final files, the subtask is skipped. If no
source can be found for the missing targets after all magnet candidates are
exhausted, the subtask fails.

## Naming Policy

Movie codes are normalized to uppercase.

Suffix rules are based on the successful magnet's tags:

- Tags containing `字幕`, `中文字幕`, `中字`, or `中文` add `-C`.
- Tags containing `破解`, `无码`, or `无码破解` add `-U`.
- Both groups present add `-UC`.

Examples:

- `abc-123` with Chinese subtitles becomes `ABC-123-C`.
- `abc-123` with uncensored tags becomes `ABC-123-U`.
- both become `ABC-123-UC`.

Multi-file naming:

- Detect `part1`, `part2`, `part3`, `cd1`, `cd2`, `disc1`, `disc2`, and simple
  `A`, `B`, `C` suffixes where they clearly denote split videos.
- Generate `-CD1`, `-CD2`, `-CD3`.
- If no disc number can be parsed, order selected videos by inferred source
  order and use their 1-based index.

Examples:

- `XXX.part1.mp4` -> `ABC-123-C-CD1.mp4`
- `XXX.part2.mp4` -> `ABC-123-C-CD2.mp4`

## Redis Runtime

Redis stores runtime-only state:

- queued main task ids.
- current main task id.
- stop flags by main task id.
- worker heartbeat and queue snapshot where needed.

PostgreSQL remains the source of truth for main task and subtask state.

Startup cleanup:

- queued/running/stopping main tasks from a previous backend process are marked
  `stopped`.
- running subtasks are reset to `queued` unless they already reached
  `completed` or `skipped`.
- Redis runtime keys are cleaned.

## Stop and Restart

Stop:

- Allowed for `queued`, `running`, and `stopping` main tasks.
- API sets the main task to `stopping` and writes a Redis stop flag.
- The current subtask is not interrupted.
- After the current subtask naturally completes, fails, or skips, the worker
  checks the stop flag.
- Remaining queued subtasks stay queued.
- Main task becomes `stopped`.

Restart:

- Allowed for `stopped` and `failed` main tasks.
- Clears the Redis stop flag.
- Resets failed and queued subtasks to `queued`.
- Keeps completed and skipped subtasks unchanged.
- Recomputes counts and re-enqueues the main task.

## API Surface

Add `backend/app/modules/storage/tasks/router.py`.

Endpoints:

- `POST /api/storage/tasks/push`
  - single push body: `movie_id`, optional `alias`, `storage_mode`,
    optional `selected_storage_location`.
- `POST /api/storage/tasks/batch`
  - batch body: `movie_ids`, optional `alias`, `storage_mode`.
- `GET /api/storage/tasks`
  - main task list with filters and pagination.
- `GET /api/storage/tasks/{main_task_id}`
  - main task detail with counts.
- `GET /api/storage/tasks/{main_task_id}/subtasks`
  - paginated subtask list.
- `GET /api/storage/tasks/subtasks/{subtask_id}`
  - subtask detail.
- `GET /api/storage/tasks/subtasks/{subtask_id}/logs`
  - subtask JSONL logs.
- `POST /api/storage/tasks/{main_task_id}/stop`
- `POST /api/storage/tasks/{main_task_id}/restart`

Responses should use the project standard success/paginated envelope.

## Realtime Events

Use `/api/events/stream`.

Add event names to frontend realtime types and client registration:

- `storage.main.updated`
- `storage.sub.updated`
- `storage.sub.log.appended`
- `storage.queue.updated`
- `movie.storage.updated`

Consumers:

- Movie list listens to `movie.storage.updated` and updates matching rows.
- Main task list listens to `storage.main.updated`.
- Main task detail listens to `storage.main.updated` and `storage.sub.updated`.
- Subtask detail listens to `storage.sub.updated` and
  `storage.sub.log.appended`.

Events include enough fields for incremental UI updates, but list/detail pages
fall back to refetching when receiving `system.resync_required`.

## Frontend UX

Movie list:

- Row action: `推送存储` or `重新推送`.
- Bulk action: `批量推送存储`.
- Confirmation modal includes alias input and storage mode dropdown.
- Single-row modal also includes target folder dropdown for single mode.
- Batch modal defaults every row to its first usable storage location in single
  mode.
- The modal shows selected count and skipped-rule summary.

Storage menu:

- Add `存储任务` under the existing `存储` menu.
- Keep `存储配置`.

Storage task list:

- Similar to crawler run records.
- Shows alias, status, total, success, failed, skipped, storage mode, created
  time, started time, finished time.
- Supports stop, restart, and detail actions.

Main task detail:

- Shows main task metadata, counts, status timeline, and subtask table.
- Subtask table shows movie code, status, current step, target locations,
  current magnet, error, and actions.

Subtask detail:

- Shows movie summary, target locations, download path, magnet attempts,
  selected files, renamed files, moved files, skipped files, errors, and logs.

## Error Handling

Run-time failures are recorded on the current magnet attempt and in subtask
logs. Failures that should move to the next magnet include:

- submit magnet failure.
- CloudDrive2 reports task exists but no reusable source file can be found.
- download polling exceeds `download_max_poll_count`.
- scan finds no files.
- main video selection finds no usable video.
- rename fails for all selected videos.
- move/copy cannot place required files.
- verification fails.

Subtask failure occurs only after allowed magnet candidates are exhausted.

Main task status is derived from subtasks:

- `completed`: no failed subtasks and no remaining queued/running subtasks.
- `failed`: at least one failed subtask and no remaining queued/running
  subtasks.
- `stopped`: stop was requested and there are remaining queued subtasks.

## Testing

Backend tests:

- main task creation for single and batch push.
- default alias generation.
- every selected movie creates a subtask.
- skipped subtask creation and main task skipped count.
- single mode target selection for single push.
- batch single mode default first storage location.
- single mode existing target marks subtask skipped.
- multiple mode target location resolution and de-duplication.
- magnet candidate order: selected first, then remaining by weight descending.
- `magnet_max_attempts_per_subtask` enforcement.
- `download_max_poll_count` per magnet enforcement.
- scan without main video switches to the next magnet.
- naming rules for uppercase code, `-C`, `-U`, `-UC`, and `-CDn`.
- existing target file skips move/copy.
- multiple mode all targets existing marks subtask skipped.
- parent and target folder creation order.
- existing offline task recovery through search and original path.
- fallback recursive lookup when search is unavailable.
- copy-to-N-minus-one and move-to-last behavior in multiple mode.
- stop behavior waits for current subtask completion.
- restart resets only queued/failed subtasks.
- realtime events are published.
- `movies.storage_summary` updates.

Frontend tests:

- single push modal target dropdown.
- storage mode default value.
- batch push payload.
- realtime movie row update.
- main task list stop/restart buttons.
- main task detail realtime count/subtask update.
- subtask detail log append.

Verification commands for implementation should include focused backend pytest
tests and frontend lint/build/test commands appropriate to the touched files.
