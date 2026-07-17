# Storage Video Part Order Design

## Problem

Storage subtasks rename selected video files in the order received from the download discovery pipeline. CloudDrive2 can return names in lexicographic order, so names like `*_10_12000.mp4` can appear before `*_1_12000.mp4`. The current filename builder then assigns `CD1` to the wrong source file.

The existing disc inference handles explicit `part2`, `cd2`, `disc2`, and `A/B/C` markers, but it does not handle batches where most filename characters are identical and only a bare numeric segment differs.

## Goals

- Rename multi-file videos according to the real part order when filenames differ only by a part token.
- Prefer the differing token among the selected video filenames over unrelated repeated tokens such as bitrate or size suffixes.
- Preserve current behavior for single-file videos and explicit `part/cd/disc` or `A/B/C` markers.
- Keep the change isolated to storage worker filename ordering and filename policy helpers.

## Non-Goals

- Do not change magnet selection, download polling, move, verify, or cleanup behavior.
- Do not introduce UI changes or new configuration.
- Do not attempt media-duration probing or content-based ordering.

## Recommended Approach

Add a small ordering helper for selected videos before rename:

1. Tokenize each selected video filename stem into text and number tokens.
2. Compare the selected batch and identify positions where tokens differ.
3. Prefer the differing token position that produces a unique ordering across the batch. Numeric differences sort numerically; letter parts such as `A/B/C` sort alphabetically with explicit mapping.
4. If batch-difference detection is not reliable, fall back to existing explicit disc inference (`part`, `cd`, `disc`, `A/B/C`).
5. If no reliable part signal exists, fall back to natural filename/path sorting rather than raw provider order.

For the reported batch, common tokens are effectively `4k2.com@vrkm01668_`, `_12000`, and `.mp4`; the differing numeric tokens are `1..15`, so the rename order becomes `_1`, `_2`, ..., `_15`.

## Components

- `storage.tasks.policies`
  - Add reusable helpers for natural tokenization and selected-video ordering.
  - Extend disc inference to support an optional detected batch part number.
  - Keep `build_video_filename` as the public filename builder.

- `storage.worker.rename_ops`
  - Sort `selected_videos` through the new helper before assigning indexes.
  - Use the sorted list for both rename execution and returned metadata.

## Data Flow

1. Download discovery returns accepted files.
2. Scan and classification select main videos.
3. Quality dedupe keeps one file per quality group while preserving selected items.
4. Rename step orders selected videos by batch-detected part token.
5. Filename builder assigns `CDn` based on explicit part markers or the sorted index.
6. Move and verify consume the renamed file list unchanged.

## Error Handling

Ordering must be deterministic and non-fatal. Ambiguous batches should not fail the subtask. If no confident differing part token exists, the helper falls back to natural sort so rename behavior remains predictable.

Existing rename error handling for duplicate target names and provider failures remains unchanged.

## Tests

Add focused backend tests for:

- `4k2.com@vrkm01668_10_12000.mp4` sorting after `_9` and before `_11`.
- Difference-token sorting where the shared suffix contains another number that must be ignored.
- Existing `part2`, `cd2`, `disc2`, and `A/B/C` inference still works.
- Single-file rename still omits the `CD` suffix.
- Ambiguous filenames fall back to deterministic natural sorting.

Run focused storage policy and worker tests after implementation.
