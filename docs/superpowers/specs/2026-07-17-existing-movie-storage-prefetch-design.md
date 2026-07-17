# Existing Movie Storage Prefetch Design

## Problem

Storage subtasks currently submit or recover magnet downloads before checking whether the movie already exists in another storage location. When a task is meant to push an already-stored movie to a new location, the worker can waste time trying another magnet even though a valid source file is already available elsewhere.

Existing fallback logic only checks the current task target directories after a `submit_task_exists` recovery path fails to find downloaded files. It does not scan the movie's existing storage locations before submitting a magnet.

## Goals

- Before each magnet submission, check whether the task's movie already has a usable stored video in another storage location.
- If a valid source is found, copy it to the current task target directory or directories and skip magnet submission.
- Reuse existing provider copy and verification behavior.
- Keep normal magnet download behavior unchanged when no valid existing source is found.
- Avoid failing the task solely because an existing-storage copy attempt fails; log the failure and continue with the magnet attempt.

## Non-Goals

- Do not change magnet ordering or magnet scoring.
- Do not change task creation behavior or introduce a separate task type.
- Do not change frontend UI.
- Do not implement media-duration probing or content fingerprinting.

## Recommended Approach

Add a pre-submit existing-storage check inside the storage worker attempt flow:

1. `execute_subtask_pipeline` already loads the `Movie`; pass it into each `execute_current_magnet_attempt`.
2. After `plan_storage_attempt(...)` and before `run_download_flow(...)`, call a new helper that searches existing movie storage.
3. The helper should inspect the movie's current storage summary locations first, then fall back to the existing storage scan utilities if no usable location is present in the summary.
4. Ignore files already in the current task's target paths; only use external existing locations as copy sources.
5. Copy the selected source file to all target paths that do not already contain that file.
6. Verify copied targets using existing verification logic.
7. Mark the subtask successful with a reason such as `copied_from_existing_movie_storage`.

If the helper finds no source, or if copy/verification fails, the worker logs the condition and continues with the original magnet submission flow.

## Components

- `storage.worker.steps`
  - Pass the loaded `Movie` into `execute_current_magnet_attempt`.
  - Invoke the pre-submit helper after target planning and before download flow.

- `storage.worker.existing_movie_storage`
  - New focused helper module for finding usable existing movie files and copying them to the current targets.
  - Keeps the existing-target fallback module limited to checking the current target paths.

- `content.movies.storage_scan` and `content.movies.storage_status`
  - Reuse existing matching and scan behavior where practical.
  - Avoid duplicating video extension, minimum size, and movie-code matching rules.

## Data Flow

1. Worker loads the movie and ordered magnets.
2. For each magnet attempt, target planning determines the current task's desired target paths and preview filename.
3. Existing-storage prefetch checks movie summary locations and scan results for a usable source outside the current target paths.
4. If found, the provider copies that source to missing target folders.
5. The copied files are verified.
6. On success, the subtask completes and no magnet is submitted.
7. On miss or failure, the existing `submit_magnet -> waiting_download -> scan -> rename -> move -> verify -> cleanup` flow continues.

## Source Selection Rules

- A source must be a video file matching the movie code by existing storage scan rules.
- A source must meet configured video extension and minimum-size requirements.
- A source whose target folder is one of the current task target paths must not count as an external source.
- Prefer locations already recorded in `movie.storage_summary["locations"]`.
- If multiple valid sources exist, choose the first deterministic candidate sorted by target folder and file path.

## Error Handling

Existing-storage prefetch is opportunistic. Provider list/copy failures should be logged with enough context for diagnosis, then the worker should continue with magnet submission.

If copy succeeds but verification fails, the worker should log the verification failure and continue with magnet submission rather than failing the whole task immediately.

## Tests

Add focused backend tests for:

- A subtask copies from `movie.storage_summary["locations"]` before submitting a magnet.
- The pre-submit path does not submit a magnet when copy and verification succeed.
- Existing files in the current target path are ignored as copy sources.
- Copy failure or verification failure falls through to the normal magnet flow.
- No existing source preserves current magnet behavior.
