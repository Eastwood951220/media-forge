# Crawler Schedules Design

## Context

Media Forge already supports persistent crawler tasks, one-off crawler runs,
URL-subset runs, temporary detail runs, batch task creation, and batch task
execution. Crawler execution is currently queued through `CrawlerRunService`
and processed by the existing runtime worker. Storage tasks are managed by a
separate storage module with queued main tasks and subtasks.

Users need a reusable schedule feature for crawler workflows:

- One schedule configuration can contain multiple crawler tasks.
- A schedule can run every day at a selected time.
- A schedule can run every week on selected weekdays at a selected time.
- Scheduled crawler runs are always incremental.
- A schedule can optionally create a storage task after the scheduled crawler
  runs finish.
- Automatic storage should include only movies saved by the current scheduled
  run, not all historical movies under the selected crawler tasks.

## Goals

- Add persistent, per-user crawler schedule configurations.
- Let one schedule select multiple crawler tasks.
- Support daily and weekly recurrence with one time of day.
- Use APScheduler for backend schedule execution.
- Restore enabled schedules when the backend starts.
- Keep APScheduler jobs synchronized with schedule create, update, enable,
  disable, delete, and manual trigger operations.
- Trigger one incremental crawler run per selected active task.
- Record each scheduled trigger as history with per-task accepted, skipped, and
  failed results.
- Prevent overlapping executions of the same schedule.
- Optionally create one merged storage task after all crawler runs from a
  scheduled trigger finish.
- Include only movies saved by those crawler runs in automatic storage.
- Add a crawler schedule management page in the frontend.

## Non-Goals

- Do not add arbitrary cron expression editing.
- Do not support multiple times per day in this iteration.
- Do not support monthly, interval, or one-time schedules.
- Do not change manual crawler run behavior.
- Do not change crawler queue execution semantics.
- Do not create one combined crawler run for multiple tasks. Each selected
  crawler task still creates its own run.
- Do not automatically store historical movies that were not saved by the
  current scheduled trigger.
- Do not require an external scheduler service.
- Do not solve multi-backend-instance scheduling beyond explicit database
  guards in this iteration.

## Data Model

### Crawler Schedule

Add `CrawlerSchedule` under `backend/app/models/`.

Suggested table: `crawler_schedules`.

- `id`: UUID primary key
- `owner_id`: owning user
- `name`: display name, max length 200
- `enabled`: boolean
- `schedule_type`: `daily` or `weekly`
- `time_of_day`: string in `HH:mm` format
- `weekdays`: JSON array of integers `0` through `6`, where `0` is Monday
- `auto_storage_enabled`: boolean
- `storage_mode`: `single` or `multiple`
- `selected_storage_location`: nullable string, max length 500
- `last_triggered_at`: nullable datetime
- `next_run_at`: nullable datetime
- timestamps

Validation rules:

- A schedule must contain at least one crawler task.
- `daily` schedules ignore `weekdays`.
- `weekly` schedules require at least one weekday.
- `time_of_day` must be a valid 24-hour time.
- `storage_mode` is required when `auto_storage_enabled` is true.
- `selected_storage_location` is only meaningful for `single`. When it is
  empty, the storage module resolves locations from each movie's source crawler
  task.

### Schedule Tasks

Add a normalized association table: `crawler_schedule_tasks`.

- `schedule_id`: foreign key to `crawler_schedules.id`, cascade delete
- `task_id`: foreign key to `crawl_tasks.id`, cascade delete
- unique constraint on `(schedule_id, task_id)`
- indexes on `schedule_id` and `task_id`

Schedules may keep references to tasks that are later disabled. The schedule
trigger skips disabled tasks instead of removing them from the configuration.

### Schedule Run History

Add `CrawlerScheduleRun` for each schedule trigger.

Suggested table: `crawler_schedule_runs`.

- `id`: UUID primary key
- `schedule_id`: foreign key to `crawler_schedules.id`, cascade delete
- `owner_id`: owning user
- `status`: `running`, `completed`, `skipped`, `partial_failed`, `failed`
- `triggered_at`: datetime
- `finished_at`: nullable datetime
- `trigger_type`: `scheduled` or `manual`
- `result`: JSON summary with accepted, skipped, and failed task entries
- `storage_status`: `disabled`, `pending`, `created`, `skipped`, `failed`
- `storage_task_id`: nullable UUID reference to `storage_main_tasks.id`
- `storage_error`: nullable text
- timestamps

Add `CrawlerScheduleRunCrawlRun` to link schedule-trigger history to crawler
runs.

Suggested table: `crawler_schedule_run_crawl_runs`.

- `schedule_run_id`: foreign key to `crawler_schedule_runs.id`, cascade delete
- `crawl_run_id`: foreign key to `crawl_runs.id`, cascade delete
- `task_id`: nullable crawler task id snapshot
- unique constraint on `(schedule_run_id, crawl_run_id)`

This explicit link avoids overloading `crawl_runs.result` as the source of
truth. It also makes automatic storage coordination and history rendering
straightforward.

### Crawl Run Source Metadata

Add lightweight source metadata to `crawl_runs`:

- `trigger_source`: nullable string, values such as `manual`, `batch`,
  `schedule`, `retry`
- `schedule_id`: nullable foreign key to `crawler_schedules.id`
- `schedule_run_id`: nullable foreign key to `crawler_schedule_runs.id`

Manual runs may leave these fields null initially. Scheduled runs set
`trigger_source = "schedule"` and populate both schedule ids.

### Detail Movie Link

Automatic storage needs reliable movie ids from saved detail rows. Current save
callbacks receive the movie id returned by `upsert_movie_with_magnets`, but the
detail row stores only item data and log context.

Add `movie_id` to `crawl_run_detail_tasks` as a nullable foreign key to
`movies.id`. Set it when a detail task reaches `saved`. For older saved detail
rows without `movie_id`, no backfill is required for this feature because
automatic storage only processes new scheduled runs.

## Backend Modules

Add `backend/app/modules/crawler/schedules/`.

### `router.py`

Expose schedule endpoints under `/api/crawler/schedules`:

- `GET /api/crawler/schedules`: paginated schedule list
- `GET /api/crawler/schedules/{schedule_id}`: schedule detail
- `POST /api/crawler/schedules`: create schedule
- `PUT /api/crawler/schedules/{schedule_id}`: update schedule
- `POST /api/crawler/schedules/{schedule_id}/enable`: enable schedule
- `POST /api/crawler/schedules/{schedule_id}/disable`: disable schedule
- `POST /api/crawler/schedules/{schedule_id}/trigger`: manually trigger once
- `GET /api/crawler/schedules/{schedule_id}/runs`: schedule run history
- `DELETE /api/crawler/schedules/{schedule_id}`: delete schedule

### `schemas.py`

Define Pydantic schemas for:

- schedule create and update payloads
- schedule list item and detail response
- selected task summaries
- schedule run history response
- manual trigger accepted response

### `service.py`

Own schedule persistence and validation:

- validate current-user ownership for every selected task
- collapse duplicate task ids
- require at least one selected task
- normalize weekly weekdays into sorted unique integers
- calculate and persist next run time
- call scheduler synchronization after create, update, enable, disable, and
  delete

### `scheduler.py`

Wrap APScheduler behind a small app-specific boundary:

- initialize one scheduler during backend lifespan startup
- load enabled schedules from the database after PostgreSQL is connected
- register one APScheduler job per enabled schedule
- update or remove jobs when schedule configuration changes
- shut down the scheduler during FastAPI lifespan shutdown

Use `CronTrigger`:

- daily: hour and minute only
- weekly: day-of-week list plus hour and minute

Use the server local timezone. In the current development environment that is
`Asia/Shanghai`. The frontend displays times in the browser's local format, but
the backend stores and evaluates the schedule in server local time for this
iteration.

### `executor.py`

Execute a schedule trigger:

1. Open a fresh DB session.
2. Reload the schedule and selected tasks.
3. If the schedule is missing, disabled, or deleted, return without creating
   runs.
4. If the same schedule has a previous schedule run with linked crawler runs
   still in `queued` or `running`, create a skipped history entry and do not
   start another trigger.
5. Create a `crawler_schedule_runs` row with `status = "running"`.
6. For each selected task:
   - skip if the task no longer exists
   - skip if the task belongs to another user
   - skip if the task is disabled
   - otherwise create one crawler run with `crawl_mode = "incremental"`
7. Link accepted crawler runs to the schedule run.
8. Store accepted, skipped, and failed entries in the history `result`.
9. Update `last_triggered_at` and `next_run_at` on the schedule.

Single-task run creation failures should not abort the whole schedule trigger.
They are recorded as failed entries.

## Automatic Storage Coordination

Add a small coordinator that is called after a crawler run reaches a terminal
state in the existing run finalization path.

Terminal crawler statuses for schedule coordination are:

- `completed`
- `failed`
- `stopped`

When a scheduled crawler run finishes:

1. Find its `schedule_run_id`.
2. Check whether all crawler runs linked to that schedule run are terminal.
3. If not all are terminal, do nothing.
4. If all are terminal and the schedule run has not already processed storage,
   continue.
5. If automatic storage is disabled, set `storage_status = "disabled"` and
   finalize the schedule run.
6. Collect distinct `movie_id` values from linked `crawl_run_detail_tasks`
   where `status = "saved"`.
7. If no saved movie ids exist, set `storage_status = "skipped"` and record a
   readable message in `result`.
8. Create one storage main task for the collected movie ids:
   - `source = "crawler_schedule"`
   - `storage_mode` from the schedule
   - `selected_storage_location` from the schedule, or null to use existing
     source-task resolution
9. Store `storage_task_id` and `storage_status = "created"` on the schedule
   run.
10. If storage creation fails, set `storage_status = "failed"` and
    `storage_error` without changing completed crawler runs.

Automatic storage creates one merged storage task per schedule trigger. It does
not create one storage task per crawler task.

Use the storage module's internal task creation service rather than routing
through the public batch-push request schema. The internal path already accepts
movie ids, source, storage mode, and optional selected storage location; if the
method remains private, add a small schedule-facing service method instead of
duplicating storage task creation logic.

## API Behavior

### Create And Update

Payload shape:

```json
{
  "name": "Nightly Crawler",
  "enabled": true,
  "task_ids": ["uuid"],
  "schedule_type": "daily",
  "time_of_day": "03:30",
  "weekdays": [],
  "auto_storage_enabled": true,
  "storage_mode": "single",
  "selected_storage_location": null
}
```

Weekly schedules use weekdays:

```json
{
  "schedule_type": "weekly",
  "time_of_day": "03:30",
  "weekdays": [0, 2, 4]
}
```

Update replaces the selected task set when `task_ids` is provided.

### List And Detail

List rows include:

- schedule id and name
- enabled state
- human-readable recurrence summary
- selected task count
- auto-storage state
- last triggered time
- next run time
- latest schedule run status

Detail includes selected task summaries and full configuration.

### Manual Trigger

Manual trigger uses the same executor path as scheduled triggers, with
`trigger_type = "manual"`. It still uses incremental crawler mode and still
honors overlap protection.

## Frontend Design

Add `/crawler/schedules` to the authenticated route tree and route tags. Place
it near existing crawler task and run pages in navigation.

### Schedule List Page

The first screen is a work-focused schedule table, not a landing page.

Top metrics:

- enabled schedules
- schedules due today
- latest successful trigger
- latest failed or partial trigger

Table columns:

- name
- enabled status
- recurrence
- task count
- automatic storage state
- last triggered at
- next run at
- latest result
- actions

Actions:

- create
- edit
- enable or disable
- trigger now
- view history
- delete

### Create And Edit Drawer

Use a drawer to keep users on the list page.

Fields:

- name
- enabled switch
- task multi-select
- daily or weekly segmented control
- time picker
- weekday checkbox group for weekly schedules
- automatic storage switch
- storage mode segmented control
- selected storage location input visible for `single`

Task selection should reuse existing task dictionary/list APIs where possible.
Saving may include tasks that are currently disabled; execution skips them and
history records the skip.

### History Drawer

Show schedule trigger history:

- triggered time
- trigger type
- status
- accepted task count
- skipped and failed task count
- linked crawler runs
- automatic storage status
- linked storage task when created
- storage error when failed

Crawler run links navigate to existing run detail pages. Storage task links
navigate to existing storage task detail pages.

## Error Handling

- Reject schedules with no task ids.
- Reject invalid daily or weekly recurrence payloads.
- Reject task ids that are not owned by the current user.
- Reject invalid storage mode values.
- Skip disabled tasks during execution and record the skip.
- Skip overlapping schedule executions and record the skipped trigger.
- Keep schedule database writes transactional. Synchronize APScheduler only
  after the database commit succeeds. If scheduler synchronization fails, log
  the error, return a readable failure when the request is still active, and let
  the next backend restart restore jobs from the database.
- Do not roll back completed crawler runs if automatic storage creation fails.
- Do not create empty storage tasks.

## Dependencies

Add APScheduler to backend dependencies.

The scheduler boundary should be narrow so future replacement is possible if
Media Forge later moves scheduling to an external worker or multi-instance
deployment.

## Startup And Shutdown

Extend FastAPI lifespan:

1. Load runtime config.
2. Connect or repair PostgreSQL.
3. Clean up interrupted crawler and storage work as today.
4. Start the crawler schedule scheduler.
5. Load enabled schedules and register APScheduler jobs.
6. On shutdown, stop APScheduler before closing Redis and PostgreSQL.

If PostgreSQL is not initialized, do not start the scheduler.

## Testing

Backend tests:

- schedule create/update validation
- selected task ownership validation
- duplicate task id collapse
- daily and weekly next-run calculation
- APScheduler job add/update/remove synchronization
- enabled schedules restored on startup
- manual trigger creates incremental crawler runs
- disabled selected tasks are skipped during execution
- overlapping schedule triggers are skipped
- schedule run history records accepted, skipped, and failed entries
- run finalization waits until all linked crawler runs are terminal
- automatic storage creates one merged storage task for saved movies
- automatic storage skips when no saved movies exist
- automatic storage failure records `storage_error`
- saved detail rows store `movie_id`

Frontend tests:

- schedule list renders recurrence, task count, enabled status, and latest
  result
- create/edit drawer validates daily and weekly rules
- weekly schedules require at least one weekday
- automatic storage fields appear and hide correctly
- create/update requests use the expected payload shape
- enable, disable, delete, and trigger actions call the expected APIs
- history drawer renders crawler run and storage task links

Verification commands:

```bash
cd backend && python -m pytest tests/ -v
cd frontend && pnpm build
cd frontend && pnpm test
```

Focused tests should be added for the new schedule modules. Broader backend and
frontend commands should run when practical because this feature touches
startup, routing, crawler finalization, and storage task creation.
