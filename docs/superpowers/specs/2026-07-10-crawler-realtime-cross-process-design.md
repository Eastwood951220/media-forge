# Crawler Realtime Cross-Process Design

## Context

Crawler runtime updates currently reach the frontend through EventSource. The
frontend subscribes in `frontend/src/pages/crawler/runs/hooks/useRunDetailRealtime.ts`
and connects through `frontend/src/realtime/eventSourceClient.ts`.

The backend EventSource endpoint is `backend/app/modules/realtime/router.py`.
It subscribes to `backend/app/modules/realtime/bus.py`, which is an in-process
queue-based event bus. Crawler runtime events are published from
`backend/app/modules/crawler/runtime/events.py`.

Graphify output points to the crawler runtime as a current coupling hotspot:
`backend/app/modules/crawler/runtime/threaded.py`,
`backend/app/modules/crawler/runtime/service.py`,
`backend/app/modules/crawler/runtime/worker.py`, and
`backend/app/modules/crawler/runtime/redis_state.py` are all high-degree or
high-outdegree runtime nodes. That supports keeping this change focused on the
runtime event boundary instead of broad crawler rewrites.

The current in-process bus is correct only when the crawler worker and API SSE
endpoint live in the same Python process. Once crawler execution moves to a
separate process, publishing to the in-process bus in the worker process will
not reach the API process that owns browser EventSource connections.

## Goals

- Keep browser-side EventSource for crawler detail live updates.
- Make backend realtime delivery work across API and crawler worker processes.
- Keep database snapshots as the authority for run state, task rows, summaries,
  and logs.
- Preserve current frontend behavior where possible: incremental updates first,
  snapshot resync when needed.
- Limit scope to crawler realtime transport and crawler detail refresh
  semantics.

## Non-Goals

- No replacement of EventSource with WebSocket.
- No UI redesign.
- No crawler scheduling or scraping behavior changes.
- No database schema changes.
- No attempt to make every detail update exactly-once at the UI layer.

## Recommendation

Use EventSource for the browser connection, but replace the backend in-process
event transport with Redis-backed cross-process publishing.

The API process remains responsible for authenticated SSE connections. Worker
processes publish realtime events into Redis. The API process consumes those
Redis events and forwards them to subscribed browser connections. Redis is
already part of the project runtime and is already used by crawler runtime
state, so this keeps the dependency model aligned with the existing stack.

## Architecture

### Components

- `RealtimeEventBus` interface
  - Keeps the existing `subscribe(owner_id)`, `unsubscribe(owner_id, queue)`,
    and `publish(event)` style where practical.
  - Hides whether delivery is local-only or Redis-backed.

- Redis realtime publisher
  - Serializes `RealtimeEvent` as JSON.
  - Publishes events to an owner-scoped channel such as
    `realtime:owner:{owner_id}`.
  - Can be called safely from API or worker processes.

- API realtime subscriber bridge
  - Runs in the API process.
  - For each connected owner, subscribes to the matching Redis channel.
  - Pushes received events into the existing per-connection queues.
  - Emits `system.resync_required` when a queue overflows or malformed payloads
    are received.

- Frontend EventSource client
  - Keeps the current `EventSource('/api/events/stream?...')` model.
  - Keeps `system.resync_required` handling.
  - Does not need to know whether backend events came from the API process or a
    crawler worker process.

### Data Flow

1. A crawler worker updates database rows for a run or detail task.
2. The worker commits the database transaction.
3. The worker publishes a `RealtimeEvent` through the Redis-backed bus.
4. The API process receives the event from Redis.
5. The API process forwards the event to all active SSE queues for the owner.
6. The frontend applies a small incremental update or fetches a fresh snapshot.

Database commit must happen before publishing events that describe persisted
state. If the frontend resyncs immediately after receiving the event, the REST
snapshot must already include the change.

## Refresh Semantics

### Run Header

`crawler.run.updated` continues to update the top `run` object. When a run
enters `completed`, `failed`, or `stopped`, the frontend should also fetch:

- `/api/crawler/runs/{run_id}`
- `/api/crawler/runs/{run_id}/tasks`
- `/api/crawler/runs/{run_id}/logs`

This makes terminal state resilient to missed intermediate events.

### Detail Task Table

`crawler.run.detail.updated` may carry small batches of changed detail tasks.
The frontend can merge those into the current table when they match current
filters and pagination. If the event sets `refresh_tasks: true`, if a changed
task enters or leaves the current filter, or if the frontend detects ordering
uncertainty, it should call `fetchTasks()`.

The `/api/crawler/runs/{run_id}/tasks` endpoint remains authoritative because
it returns both page rows and `summary`.

### Top Summary Counts

Top summary counts should not rely on frontend-only incremental math. Summary
counts should be refreshed from `/api/crawler/runs/{run_id}/tasks` whenever a
detail task status change can affect aggregate counts. The existing detail
realtime hook already has a `fetchTasks()` path and should continue to use it
as the summary refresh mechanism.

### Logs

`crawler.run.log.appended` can append to the visible log timeline. On reconnect,
queue overflow, malformed event, or run terminal state, the frontend should call
`fetchLogs()` so log state recovers from missed append events.

## Error Handling

- Redis publish failure should not fail the crawler transaction after the
  database commit. It should log a warning with event name, owner ID, and
  resource ID.
- Redis subscriber failure in the API process should emit local
  `system.resync_required` to affected SSE clients when possible, then retry
  subscription.
- Per-connection queue overflow should keep the existing behavior: clear the
  queue and enqueue `system.resync_required` with reason `queue_overflow`.
- Malformed Redis event payloads should be discarded and logged; connected
  clients for that owner should receive `system.resync_required` with reason
  `malformed_event`.

## Testing

Backend tests:

- Publishing through the Redis-backed bus from one bus instance is received by
  a subscriber attached to another bus instance.
- Owner scoping prevents events for owner A from reaching owner B.
- Queue overflow produces `system.resync_required`.
- Crawler event helpers publish serialized payloads with the same event names
  and payload shapes currently consumed by the frontend.

Frontend tests:

- `useRunDetailRealtime` still merges matching detail updates.
- `refresh_tasks: true` calls `fetchTasks()`.
- Terminal `crawler.run.updated` calls `fetchLogs()` and `fetchTasks()`.
- `system.resync_required` calls the full snapshot resync callback.

## Migration Notes

The current in-process bus can remain as the local queue fan-out inside the API
process. The cross-process part should be introduced behind the existing
realtime event publishing API so crawler modules continue calling
`publish_run_updated`, `publish_run_detail_updated`, and
`append_run_log_for_run`.

The implementation should avoid touching scraping behavior. Any changes in
`backend/app/modules/crawler/runtime/threaded.py` should be limited to ensuring
events are published after commits and that bulk detail changes use
`refresh_tasks` when individual incremental events would be too noisy.

## Acceptance Criteria

- A crawler worker running in a separate process can publish a crawler run event
  and an active browser EventSource connection receives it.
- Detail page top run state updates through EventSource while the run is active.
- Detail table and summary counts recover through REST snapshot fetches after
  `refresh_tasks`, terminal run updates, queue overflow, and reconnect errors.
- Existing frontend EventSource API remains unchanged.
- Existing event names remain unchanged:
  - `crawler.run.updated`
  - `crawler.run.detail.updated`
  - `crawler.run.log.appended`
  - `system.resync_required`
