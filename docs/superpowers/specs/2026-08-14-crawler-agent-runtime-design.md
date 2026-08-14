# Crawler Agent Runtime Design

## Context

When a crawler task is submitted from the task list with incremental or full crawl mode, submission succeeds but execution fails if `JAVDB_FETCH_MODE=agent` and the task contains JavDB URLs. The worker enters `execute_threaded_crawl()`, detects Agent mode, and calls `execute_agent_crawl()`. That function currently raises a placeholder runtime error:

`JavDB Agent runtime is configured but Agent work execution is not available in this task`

The project already has partial Chrome Agent infrastructure:

- Agent token/session/status APIs.
- Agent WebSocket connection and heartbeat/cookie-sync handling.
- `CrawlerAgentWorkItem` model.
- Work item claiming and stale lease reset.
- `agent.task_request` and `agent.page_snapshot` WebSocket messages.
- Backend parser bridge that converts Agent DOM fragments into existing JavDB parser inputs.

The missing piece is the crawler runtime that creates work items, waits for Agent snapshots, parses them on the backend, and continues the existing list/detail persistence pipeline.

## Goal

Implement a complete synchronous Chrome Agent execution path for JavDB crawler runs. Incremental and full runs should work in Agent mode instead of failing with the placeholder runtime error.

## Non-Goals

- Do not implement extension-side business parsing.
- Do not introduce a second crawler scheduler or asynchronous run state machine.
- Do not add WebSocket as a crawler realtime replacement; existing run/task EventSource behavior remains unchanged.
- Do not automatically fall back to static mode when Agent mode is selected.
- Do not redesign the crawler config page beyond preserving existing Agent status/config behavior.

## Confirmed Decisions

- Use `JAVDB_FETCH_MODE=agent` to route JavDB URLs into Agent execution.
- Use backend parsing. The Chrome Agent opens pages and sends DOM fragments; backend reuses existing JavDB parsers.
- If Agent is unavailable or does not execute work, the run fails with a clear error. It does not wait indefinitely and does not silently fall back to static.
- Keep the existing synchronous `execute_run -> execute_threaded_crawl -> finalize_run` lifecycle.

## Recommended Approach

Use a synchronous waiting Agent runtime.

`execute_agent_crawl()` creates `CrawlerAgentWorkItem` rows, waits for the connected Chrome Agent to claim and complete them, parses returned snapshots, and then calls the same persistence/event helpers already used by the threaded crawler.

This keeps the change bounded and avoids adding a separate run state machine. The trade-off is that a crawler worker slot waits while the Agent works. That is acceptable for this implementation because it preserves the current execution model and makes failure/stop handling deterministic.

## Runtime Flow

### Entry

`execute_threaded_crawl()` continues to read crawler runtime config. If `JAVDB_FETCH_MODE == "agent"` and the task contains JavDB URLs, it calls `execute_agent_crawl()`.

The Agent path receives the same arguments as threaded mode:

- `db`
- `run`
- `task`
- `runtime`
- `detail_only`
- `selected_task_url_ids`

It returns the same result shape used by `finalize_run()`:

- `total_tasks`
- `completed_tasks`
- `failed_tasks`
- `skipped_tasks`
- `saved`
- `failed`
- `skipped`
- optional `stopped`

### Preflight

Before creating work items, the runtime checks whether the current task owner has an online Agent.

If not, it writes a readable run log and raises an Agent-specific error such as:

`Chrome Agent 未在线，无法执行 JavDB Agent 爬取`

This fails the run quickly and removes the current placeholder failure.

### List Phase

For non-`detail_only` runs:

1. Resolve the task URLs, applying `selected_task_url_ids` if present.
2. For each JavDB URL, create a `CrawlerAgentWorkItem`:
   - `owner_id`: task owner
   - `run_id`: current run
   - `task_id`: current task
   - `url_entry_id`: source task URL
   - `page_kind`: `list`
   - `url`: URL/final URL to open
   - `status`: `pending`
3. Wait for the Agent to claim and complete the item.
4. Parse `result_json` through `parse_agent_list_snapshot()`.
5. Apply existing incremental behavior:
   - use existing movie-code checks where needed
   - skip persisted rows for incremental `already_exists` items
   - append source task IDs for existing movies
6. Persist visible detail tasks through `upsert_detail_task()`.
7. Publish `crawler.run.detail.updated` with `refresh_tasks=True`.
8. Append run logs for visibility.

The list phase does not parse business fields in the extension. The extension only supplies the DOM fragments required by the backend parser bridge.

### Detail Phase

For each pending detail task:

1. Claim the next pending detail row.
2. Create a `CrawlerAgentWorkItem`:
   - `owner_id`: task owner
   - `run_id`: current run
   - `task_id`: current task
   - `detail_task_id`: current detail row
   - `page_kind`: `detail`
   - `url`: detail source URL
   - `status`: `pending`
3. Wait for the Agent result.
4. Parse `result_json` through `parse_agent_detail_snapshot()`.
5. Pass the parsed detail through `MoviePipeline`.
6. Persist the movie through `upsert_movie_with_magnets()`.
7. Update detail status:
   - `saved` for successful pipeline/save
   - `skipped` for already-existing item
   - `crawl_failed` or `save_failed` for failures
8. Publish `crawler.run.detail.updated` for the changed detail row.

This mirrors the existing threaded detail phase, replacing only page fetching with Agent snapshot execution.

## Backend Components

### `backend/app/modules/crawler/agent/work_items.py`

Add small work item lifecycle helpers:

- `create_work_item(db, *, owner_id, run_id, task_id, page_kind, url, detail_task_id=None, url_entry_id=None) -> CrawlerAgentWorkItem`
- `wait_for_work_item_result(db, item, *, runtime, run_id, timeout_seconds, poll_interval_seconds=1.0) -> CrawlerAgentWorkItem`
- `mark_work_item_failed(db, item, reason) -> CrawlerAgentWorkItem`

Waiting must:

- refresh from the database each poll
- call `expire_stale_work_items()` before deciding an item is stuck
- check `runtime.is_stop_requested(run_id)`
- return completed items
- raise a timeout error for pending/assigned/running items after the timeout
- raise an execution error for failed items

### `backend/app/modules/crawler/agent/runtime.py`

Replace the placeholder `execute_agent_crawl()` with a real implementation.

Keep it split into small internal functions:

- `_ensure_online_agent()`
- `_run_agent_list_phase()`
- `_run_agent_detail_phase()`
- `_process_agent_detail_result()`
- `_build_agent_result()`

The module should reuse existing runtime helpers instead of duplicating crawler persistence rules.

### `backend/app/modules/crawler/agent/errors.py`

Define explicit exceptions:

- `AgentUnavailableError`
- `AgentWorkTimeoutError`
- `AgentWorkFailedError`

Parser errors can continue using `AgentSnapshotParseError`.

### `backend/app/modules/crawler/agent/router.py`

Keep the existing WebSocket protocol. Tighten completion behavior:

- `agent.page_snapshot` should complete only work items that are still completable.
- Late snapshots for stopped/failed/completed work items should receive a `server.ack` with `ignored=True` and must not advance crawler state.
- Snapshot validation or parser-bridge failures should mark the work item failed and return a `server.error` payload containing the Agent task ID and reason.

The router should not finalize crawler runs; run progression remains owned by `execute_agent_crawl()`.

## Data Contracts

### Agent Task Assignment

Existing `task.assigned` payload is sufficient:

- `agent_task_id`
- `run_id`
- `detail_task_id`
- `url_entry_id`
- `page_kind`
- `url`
- `attempt`

### Agent Snapshot

Agent snapshot payload remains:

- `agent_task_id`
- optional `cookies`
- `snapshot`

Snapshot shape:

- `page_kind`: `list` or `detail`
- `url`
- `fragments`
- `source_page`

Required fragments:

- list: `items`
- detail: `title`, `movie_panel`

## Error Handling

### Agent unavailable

Fail immediately before work item creation:

`Chrome Agent 未在线，无法执行 JavDB Agent 爬取`

### Work item timeout

If the Agent does not claim or complete work within the configured timeout, fail with:

`Chrome Agent 执行超时`

Agent work timeout should reuse the existing `SECURITY_WAIT_SECONDS` runtime config. This avoids adding config UI or a new persistence field in this scope.

### Snapshot parse failure

List parse failure fails the run.

Detail parse failure marks the current detail row `crawl_failed`, writes the error to `detail.error` and run logs, publishes the detail update, and then continues with the next pending detail row. If every detail fails, the final run result reports failed tasks through the existing finalize path.

### User stop

If `runtime.is_stop_requested(run_id)` becomes true during waiting:

- stop waiting
- return a result with `stopped=True`
- avoid marking the item as a normal failure

### Late snapshot

If a snapshot arrives after the related work item is no longer completable, it must not update run/detail/movie state.

## Realtime And Store Behavior

This design preserves the recent crawler realtime boundaries:

- Runtime status is still published through existing run/task EventSource events.
- Run-detail subtask/log updates remain page-local.
- Agent runtime writes run logs and publishes detail updates through existing helpers.
- No Agent work item state is stored in the frontend Zustand runtime store.

## Testing Strategy

### Backend Tests

Add focused tests before implementation:

1. Agent mode no longer raises the placeholder RuntimeError.
2. Agent unavailable fails fast with the new readable error.
3. A completed list work item snapshot creates detail tasks through backend parsing.
4. A completed detail work item snapshot saves a movie and marks the detail row `saved`.
5. Work item timeout fails with a readable timeout error.
6. Stop request during wait returns stopped behavior.
7. Late `agent.page_snapshot` for a non-completable work item does not advance crawler state.
8. Existing Agent WebSocket token/session/cookie-sync behavior remains unchanged.

### Frontend Tests

Only existing UI behavior needs coverage unless the implementation changes copy:

1. Failed Agent runs appear as failed through existing runtime store/EventSource flow.
2. Run detail logs display the Agent failure reason.
3. Config page Agent status remains visible.

## Rollout

1. Implement backend Agent runtime behind the existing `JAVDB_FETCH_MODE=agent` config.
2. Keep static mode unchanged.
3. Verify with backend focused Agent/runtime tests.
4. Verify crawler task/run realtime tests to ensure status propagation still works.
5. Verify frontend focused crawler tests and build.

## Risks

- Worker slots can be occupied while waiting for Agent execution.
- Agent DOM fragments may drift from JavDB markup and parser requirements.
- Timeout values that are too short may fail legitimate manual/security-check flows.
- Late snapshots must be guarded carefully to avoid stale state mutation.
