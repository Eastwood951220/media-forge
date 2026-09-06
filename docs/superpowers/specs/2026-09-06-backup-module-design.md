# Backup Module Design

## Context

Media Forge needs a backup and restore feature for reusable application data.
The entry point should appear under Content Management, but the backend module
must be independent so the feature can grow beyond content-only data.

The movie library can contain tens or hundreds of thousands of records, so the
backup format must avoid loading one giant JSON document into memory. The first
version should preserve data that is useful after restore and avoid restoring
historical execution state.

## Goals

- Add an independent backend module named `backup`.
- Add a Content Management menu entry for backup and restore.
- Export and restore grouped reusable data:
  - movie data
  - crawler tasks and schedules
  - configuration
- Preserve `movies.code` uniqueness during restore.
- Support merge restore and overwrite restore, with merge as the default.
- Support automatic scheduled backups to a local backup directory.
- Handle large movie libraries through streamed export and batched restore.
- Keep sensitive configuration out of backups unless the user explicitly opts in.

## Non-Goals

- Do not implement full PostgreSQL physical backups.
- Do not restore historical execution records such as crawler runs, crawler run
  detail tasks, schedule run history, storage main tasks, or storage subtasks.
- Do not upload automatic backups to CloudDrive2 in the first version.
- Do not back up users, auth tokens, active runtime state, Redis state, logs, or
  generated frontend/static build output.

## Module Boundary

Backend files should live under:

```text
backend/app/modules/backup/
```

The API prefix should be:

```text
/api/backup
```

Frontend files should live under:

```text
frontend/src/api/backup/
frontend/src/pages/content/backup/
```

The frontend route should be:

```text
/content/backup
```

The sidebar should add a `数据备份` item under `内容管理`. The module is named
backup even though the navigation location is under content management.

## Backup Format

Backups use a `.mfbackup` archive. The archive is a ZIP file with a manifest and
grouped JSON Lines files:

```text
media-forge-backup-20260906-033000.mfbackup
  manifest.json
  data/
    movies.jsonl
    movie_magnets.jsonl
    movie_filters.jsonl
    crawl_tasks.jsonl
    crawl_task_urls.jsonl
    crawl_task_tags.jsonl
    crawl_task_tag_links.jsonl
    crawler_schedules.jsonl
    crawler_schedule_tasks.jsonl
  config/
    crawler_config.json
    movie_filter_config.json
    storage_config.json
    javdb_cookies.json
```

`javdb_cookies.json` is only included when sensitive configuration export is
enabled. `storage_config.json` should omit `api_token` unless sensitive export
is enabled.

`manifest.json` should include:

- format name and version
- Media Forge app version when available
- created timestamp
- selected groups
- `include_sensitive`
- per-file row counts
- source timezone
- checksum metadata for archive entries where practical

JSONL entries should be UTF-8 encoded, one object per line. Export should page
through database records and write lines incrementally. Restore should read each
file line by line and commit in batches, such as 500 or 1000 records per batch.

## Data Groups

### Movie Data

Includes:

- `movies`
- `movie_magnets`
- `movie_filters`

Movie records keep their original IDs when possible. Restore lookup priority is:

1. `id`
2. `code`
3. `source_url`

`code` must remain unique. If an incoming movie has a `code` already used by a
different movie, restore should skip that movie, record a conflict, and skip its
dependent magnets.

Magnets restore by resolved movie ID plus `dedupe_key`. `movie_filters` should
be regenerated after movie restore rather than trusted from the backup counts,
so filter counts match the restored library.

### Tasks And Schedules

Includes:

- `crawl_tasks`
- `crawl_task_urls`
- `crawl_task_tags`
- `crawl_task_tag_links`
- `crawler_schedules`
- `crawler_schedule_tasks`

Does not include:

- `crawl_runs`
- `crawl_run_detail_tasks`
- `crawler_schedule_runs`
- `crawler_schedule_run_crawl_runs`
- `storage_main_tasks`
- `storage_sub_tasks`

Tasks restore by `id` first, then by the current user plus task `name`. URLs
restore by resolved task ID plus URL. Tags restore by current user plus tag
name. Schedule-task links are rebuilt through the restored task ID map.

Schedules restore by `id` first, then by current user plus schedule `name`.
Schedule next-run values should be recalculated after restore rather than
blindly trusting stale values from the backup.

### Configuration

Includes selectable configuration files:

- crawler config
- JavDB cookies
- movie filter UI config
- storage config

Sensitive fields are opt-in:

- JavDB cookies
- CloudDrive2 API token

When a backup does not contain sensitive fields, restore must preserve existing
local sensitive values rather than clearing them.

## Restore Modes

### Merge Restore

Merge is the default mode. Existing rows are updated when matched by stable
identity, and missing rows are inserted. Rows not present in the backup remain
untouched. Conflicting rows are skipped and reported without aborting the whole
restore unless the archive structure is invalid or incompatible.

### Overwrite Restore

Overwrite clears only the selected groups before import:

- movie group clears movies, magnets, and filter rows
- tasks and schedules group clears crawler tasks, task URLs, task tags,
  schedules, and link tables
- config group overwrites selected config files, while preserving local
  sensitive values when the archive does not include them

Overwrite still does not delete historical run or storage task tables. Existing
foreign-key rules handle links from historical records to deleted reusable data.

## Automatic Backups

Automatic backup settings should be stored in:

```text
data/configs/backup.conf
```

Settings:

- `enabled`
- `backup_dir`, defaulting to `data/backups/`
- `schedule_type`, initially `daily` or `weekly`
- `time_of_day`
- `weekdays` for weekly schedules
- selected groups
- `include_sensitive`, default false
- `retention_count`, default 10

The backend should load the setting at startup and register a lightweight backup
scheduler. Saving config through the API should refresh the scheduler.

Automatic backups call the same export service used by manual backups. File
names should use a timestamp:

```text
media-forge-backup-YYYYMMDD-HHMMSS.mfbackup
```

After a successful automatic backup, the service should delete older backup
files beyond `retention_count` in the configured directory.

Only one backup operation should run at a time. Manual export, automatic export,
inspection, and restore should coordinate through a process-local lock. If an
automatic backup fires during restore, it should skip that run and record the
skip reason in logs and job state.

## API Design

Base prefix:

```text
/api/backup
```

Endpoints:

- `GET /config`: return automatic backup settings
- `PUT /config`: save automatic backup settings and refresh the scheduler
- `GET /files`: list `.mfbackup` files in the configured backup directory
- `POST /export`: start a manual export job
- `GET /files/{name}/download`: download an existing local backup file
- `POST /inspect`: upload a backup for preflight inspection
- `POST /restore`: upload and restore a backup
- `POST /files/{name}/restore`: restore from an existing local backup file
- `DELETE /files/{name}`: delete a local backup file
- `GET /jobs/{job_id}`: return backup job status

Long-running export and restore operations should use in-process jobs. The API
returns a `job_id` immediately, and the frontend polls job status. Job status is
allowed to be lost on backend restart; completed backup files remain on disk.

Job status fields:

- `id`
- `operation`: export, inspect, restore, auto_export, delete
- `status`: pending, running, succeeded, failed, skipped
- `phase`
- `processed`
- `total`
- result statistics
- error summary
- output file name when available

Path parameters for local files must reject path traversal. Only files in the
configured backup directory with the `.mfbackup` suffix may be downloaded,
restored, or deleted.

## Frontend Design

Add route:

```text
/content/backup
```

Add sidebar entry:

```text
内容管理 / 数据备份
```

The page has three operational areas:

1. Manual backup
   - group checkboxes
   - sensitive configuration switch, default off
   - start export button
   - job progress
   - download button after success
2. Restore backup
   - upload `.mfbackup` or choose an existing local file
   - inspect first
   - show manifest, groups, row counts, created time, and sensitive flag
   - choose merge or overwrite, merge default
   - choose groups to restore
   - confirm dangerous actions before overwrite restore
3. Automatic backup
   - enable switch
   - local backup directory input
   - daily or weekly schedule controls
   - retention count
   - group checkboxes
   - sensitive configuration switch, default off
   - recent backup file table with download, restore, and delete actions

The UI should use existing Ant Design conventions and match the current page
structure. Query invalidation after restore should refresh movie lists, crawler
task lists, schedule lists, and configuration queries for selected groups.

## Error Handling

Archive inspection should fail clearly for:

- non-ZIP files or invalid `.mfbackup` structure
- missing `manifest.json`
- unsupported format version
- missing selected data files
- invalid JSONL rows
- path traversal entries in the archive

Restore should continue on row-level conflicts where possible and summarize:

- created
- updated
- skipped
- conflicts
- errors

Fatal errors should rollback the current batch and mark the job failed. Earlier
committed batches may remain restored; the result should say the restore was
partial if that happens.

## Testing

Backend tests should cover:

- archive manifest and JSONL structure
- sensitive fields omitted by default
- sensitive fields included only when requested
- merge restore by ID, code, and source URL
- `code` uniqueness conflicts
- overwrite restore scoped to selected groups
- historical run tables excluded from backup and restore
- config restore preserving local secrets when missing from backup
- automatic backup file generation and retention cleanup
- path traversal rejection for local file operations and archive entries
- large-data export and import through pagination and batching

Frontend tests should cover:

- sidebar and route metadata for `/content/backup`
- manual export payloads
- sensitive export confirmation
- upload inspection before restore
- merge and overwrite restore payloads
- overwrite restore confirmation
- automatic backup config form payloads
- local backup table actions
- job polling success and failure states

## Open Decisions Resolved

- Use `.mfbackup` ZIP archives with manifest plus JSONL files.
- Keep backend backup code in an independent `backup` module.
- Place the frontend entry under Content Management.
- Use merge as the default restore mode and support overwrite as an option.
- Make export/restore groups selectable.
- Make sensitive configuration export opt-in and disabled by default.
- Save automatic backups locally, defaulting to `data/backups/`, with a
  configurable directory.
