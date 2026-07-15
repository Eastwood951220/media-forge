# Storage VR Target And Quality Dedupe Design

## Goal

Update storage tasks so VR movies are stored under a `VR` subdirectory of their resolved category path, and so one magnet that contains duplicate quality variants of the same video keeps only the largest variant before rename and move.

Example target path change:

- Non-VR: `/嘿嘿/日本/巨乳/XXX`
- VR: `/嘿嘿/日本/巨乳/VR/XXX`

Example duplicate quality files:

- `XXX_1_8K.mp4`
- `XXX_1_HD.mp4`

These represent the same video at different qualities. The storage task should keep the largest file and skip the smaller variants.

## Current Context

The storage worker pipeline is already split into focused modules:

- `backend/app/modules/storage/worker/steps.py` controls the magnet attempt flow and already loads the `Movie`.
- `backend/app/modules/storage/worker/target_planning.py` computes download and target paths.
- `backend/app/modules/storage/worker/file_pipeline.py` runs scan, select, rename, move, verify, and cleanup.
- `backend/app/modules/storage/tasks/policies.py` contains filename and storage policy helpers.
- `backend/app/modules/storage/worker/timeline.py` classifies scanned files into selected videos, excluded files, subtitles, covers, and other files.

The existing flow is:

1. Submit one magnet.
2. Poll or recover downloaded files.
3. Scan files.
4. Select main videos by extension and minimum size.
5. Rename selected videos.
6. Move or copy renamed videos to target paths.
7. Verify and clean up.

The design keeps that flow and adds narrowly scoped policy steps.

## VR Target Rule

VR detection uses only `Movie.tags`.

`MovieMagnet.tags` must not be used for VR detection because magnet tags do not carry the VR category in this project. Magnet tags continue to drive the existing filename suffix behavior such as `-C`, `-U`, and `-UC`.

VR matching is case-insensitive and should avoid broad substring matches. It should match tags that are clearly VR tags, such as:

- `VR`
- `vr`
- `VR影片`

It should not match unrelated words merely because they contain the letters `vr`.

When a movie is VR, each resolved target folder inserts `VR` immediately before the code folder:

- `/Movies/日本/巨乳/XXX` becomes `/Movies/日本/巨乳/VR/XXX`
- `/Movies/中字/XXX` becomes `/Movies/中字/VR/XXX`

For multiple target locations, every target location receives the same `VR/<code_folder>` suffix. If the selected target location already ends with `VR`, the planner must not produce `VR/VR/<code_folder>`.

If `Movie.tags` is missing, empty, or contains non-string values, VR detection treats the movie as non-VR and the storage task continues normally.

## Quality Duplicate Rule

Quality duplicate filtering runs after main-video selection and before rename.

It receives `classified.selected_videos`, groups likely duplicate quality variants, and returns only the largest file in each group.

The grouping key is built from the file stem by removing quality tokens and normalizing separators. Initial quality tokens include:

- `8K`
- `4K`
- `2K`
- `UHD`
- `FHD`
- `HD`
- `2160P`
- `1440P`
- `1080P`
- `720P`

The matching should handle common separators around tokens, including `_`, `-`, `.`, spaces, and brackets.

The grouping must preserve true multi-part markers. It must not remove or merge markers such as:

- `CD1`, `CD2`
- `part1`, `part2`
- `disc1`, `disc2`

Examples:

- `XXX_1_8K.mp4` and `XXX_1_HD.mp4` normalize to the same key, so only the largest file remains.
- `XXX-CD1.mp4` and `XXX-CD2.mp4` normalize to different keys, so both remain and the existing multi-CD rename behavior continues.
- `XXX_part1_4K.mp4` and `XXX_part2_4K.mp4` remain separate parts because `part1` and `part2` are retained.

If a group has multiple files, the file with the largest numeric `size` wins. Missing or invalid size is treated as `0`. If a file normalizes to an empty key, it is treated as its own group and is not merged with unrelated files.

## Data Flow

`execute_subtask_pipeline` already loads the `Movie`. It should pass the movie's tags into the magnet attempt path planning layer.

The updated flow is:

1. Load the movie and ordered magnet attempts.
2. For the current magnet, compute target paths with `Movie.tags` and `MovieMagnet.tags` kept separate.
3. Plan download path, preview filename, code folder, and target paths.
4. If `Movie.tags` indicates VR, insert `VR` before the code folder in every target path.
5. Download or recover files as today.
6. Scan and classify files as today.
7. Apply quality duplicate filtering to selected main videos.
8. Rename only the retained videos using the current magnet tags.
9. Move or copy the renamed videos to the planned target paths.
10. Verify and clean up as today.

This keeps target planning, duplicate filtering, and filename suffix decisions separate.

## Components

### Storage Policy Helpers

Add pure helpers in `backend/app/modules/storage/tasks/policies.py` or a focused adjacent policy module:

- `is_vr_movie_tags(tags: list[str]) -> bool`
- `insert_vr_directory(target_path: str, code_folder: str) -> str`
- `quality_dedupe_key(filename: str) -> str`
- `dedupe_quality_variants(videos: list[dict]) -> tuple[list[dict], list[dict]]`

The helpers should be deterministic and easy to unit test without a storage provider.

### Target Planning

Update `plan_storage_attempt` so it can receive movie tags separately from magnet tags.

It should:

- Use magnet tags for `build_video_filename`, preserving existing suffix behavior.
- Use movie tags for VR detection.
- Record the final planned paths on `subtask.target_paths` as it does today.

### File Pipeline

Update `run_found_files_pipeline` so it applies quality duplicate filtering after `classify_scanned_files`.

The rename step should receive only the retained videos. Dropped quality variants should not be renamed, moved, copied, verified, or included as successful result files.

## Logging

Preparation logging should keep the existing `target_paths` payload. When VR is detected, include structured context such as:

- `vr_detected: true`
- `vr_source: "movie_tags"`

Quality duplicate filtering should log only when at least one file is dropped. The log message should include:

- retained files
- dropped files
- dedupe group key
- reason `duplicate_quality_smaller_size`

Normal tasks without quality duplicates should not gain noisy extra logs.

## Error Handling

VR detection must be best-effort and non-fatal. Bad tag values should behave like non-VR tags.

Quality duplicate filtering must also be non-fatal:

- Missing file name keeps the item in its own group.
- Missing size is treated as `0`.
- Ties keep the deterministic first winner after stable sorting by size descending, then name and path.

Existing errors from directory creation, rename, move, copy, verification, and cleanup remain handled by the current pipeline.

## Testing

Backend tests should cover:

- Movie tags containing `VR` insert `/VR/<code_folder>` into the target path.
- Magnet tags containing `VR` do not trigger the VR directory rule.
- Non-VR movie tags preserve current target paths.
- Multiple target locations all receive `VR/<code_folder>` for VR movies.
- A target location that already ends with `VR` does not produce duplicate `VR/VR`.
- `XXX_1_8K.mp4` and `XXX_1_HD.mp4` are grouped and only the largest file is retained.
- `XXX-CD1.mp4` and `XXX-CD2.mp4` are not grouped together.
- `XXX_part1_4K.mp4` and `XXX_part2_4K.mp4` are not grouped together.
- The pipeline renames and moves only retained quality variants.
- Dropped quality variants appear in logs with `duplicate_quality_smaller_size`.

## Out Of Scope

- Frontend UI changes.
- Database schema changes.
- CloudDrive2 provider API changes.
- Reorganizing files that were already stored before this change.
- Changing magnet ordering or selected magnet logic.
- Using magnet tags for VR detection.
