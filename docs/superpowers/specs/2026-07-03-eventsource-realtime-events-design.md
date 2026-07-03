# EventSource Realtime Events Design

## Goal

Replace timer-based status refreshes with a reusable server-sent events channel. The first implementation phase should remove the polling loops from crawler run detail updates. The same event model must be reusable for future cloud storage progress, movie processing, task deletion progress, and queue status updates.

## Current Context

The project currently has periodic status refreshes in `frontend/src/pages/crawler/runs/RunDetailPage.tsx`:

- `getCrawlerRun(id)` is called every 3 seconds while the run is `queued` or `running`.
- `getCrawlerRunTasks(id, ...)` is also called every 3 seconds while the run is active.
- The page already performs an initial REST snapshot load for run metadata and detail tasks.

The backend currently has no WebSocket or SSE endpoint. Runtime state already uses Redis for queue/current-run state, but run logs are JSONL files written through `backend/app/modules/crawler/runs/logs.py`.

## Decision

Use EventSource/SSE instead of WebSocket for realtime status updates.

Reasons:

- Current realtime needs are server-to-client updates only.
- Client commands such as stop, restart, delete, or future cloud task controls can continue using REST APIs.
- Browser `EventSource` includes automatic reconnect behavior.
- SSE is simpler to test and operate than WebSocket for progress, status, and log streams.
- The event schema can be kept transport-neutral, so WebSocket can still replace the transport in a future phase if bidirectional traffic becomes necessary.

## Scope

### Included

- Add a generic SSE endpoint: `GET /api/events/stream?token=<jwt>`.
- Authenticate the stream with the existing JWT token passed as a query parameter.
- Add a reusable backend realtime module for event schemas, user-scoped connection queues, SSE formatting, and event publishing.
- Define event names and payload conventions for crawler, queue, movie, cloud storage, and system events.
- First functional integration: crawler run detail realtime updates.
- Frontend adds one reusable EventSource client and local event subscription API.
- Run detail page keeps its initial REST snapshot and replaces periodic active-run refresh with SSE updates.
- On SSE reconnect, active pages resync through REST to avoid missed events.

### Excluded

- Replacing all possible list-page refreshes in the first phase.
- Multi-process Redis pub/sub fanout in the first phase.
- Sharing a single SSE connection across browser tabs.
- Moving REST commands such as stop/restart/delete into the event stream.
- Building cloud storage functionality itself.

## Backend Design

Create a new module under `backend/app/modules/realtime`.

### `schemas.py`

Define the canonical event shape:

```python
class RealtimeEvent(BaseModel):
    id: str
    event: str
    scope: str
    resource_id: str | None = None
    owner_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
```

Field meaning:

- `id`: monotonic enough event id for logs and reconnect diagnostics.
- `event`: concrete event name, such as `crawler.run.updated`.
- `scope`: broad domain, such as `crawler.run` or `cloud.storage`.
- `resource_id`: run id, cloud task id, movie id, or `None` for user-level events.
- `owner_id`: user id used for routing events to the right authenticated clients.
- `payload`: event-specific data.
- `created_at`: server event creation time.

### `bus.py`

Provide a process-local user-scoped event bus:

- `subscribe(owner_id: str) -> AsyncIterator[RealtimeEvent]`
- `publish(event: RealtimeEvent) -> None`
- `unsubscribe(owner_id: str, queue_id: str) -> None`

The first phase uses in-memory `asyncio.Queue` instances. Each connected user can have multiple queues because multiple tabs are allowed. Queue capacity should be bounded. If a queue is full, publish `system.resync_required` to that user and drop older queued messages for that connection.

This intentionally does not add Redis pub/sub in the first phase. If crawler workers move to a separate process in a future phase, the event bus can keep its public API and switch the internal publisher to Redis pub/sub.

### `router.py`

Add:

```text
GET /api/events/stream?token=<jwt>
```

Behavior:

- Decode token using the existing JWT logic.
- Resolve the user from the database.
- Return `401` when the token is missing, invalid, expired, or points to no user.
- Return `StreamingResponse` with `media_type="text/event-stream"`.
- Send keepalive comments every 20 seconds:

```text
: keepalive

```

- Serialize each event as:

```text
id: <event.id>
event: <event.event>
data: <json payload>

```

The JSON `data` must include the full `RealtimeEvent` except internal server-only objects.

Register this router in `backend/app/main.py`.

## Event Names

First phase crawler events:

- `crawler.run.updated`: run status, timestamps, result, error, and log snapshot when useful.
- `crawler.run.detail.updated`: one detail task changed or a batch of detail tasks changed.
- `crawler.run.log.appended`: one run log entry was appended.
- `crawler.queue.updated`: queue size/current run changed.

Reserved future movie events:

- `movie.saved`
- `movie.updated`
- `movie.magnet.updated`
- `movie.storage_status.updated`

Reserved future cloud storage events:

- `cloud.storage.task.updated`
- `cloud.storage.transfer.progress`
- `cloud.storage.file.matched`
- `cloud.storage.delete.updated`
- `cloud.storage.log.appended`

System events:

- `system.connected`
- `system.keepalive`
- `system.resync_required`

## Crawler Integration

Publish realtime events from existing crawler runtime points:

- When a run is created or restarted: `crawler.run.updated`.
- When a run changes to `running`: `crawler.run.updated`.
- When a detail task is created or its status changes: `crawler.run.detail.updated`.
- When `_append_run_log` appends a JSONL log entry: `crawler.run.log.appended`.
- When queue state changes: `crawler.queue.updated`.
- When a run completes, fails, or stops: `crawler.run.updated`.

Event payloads should be compact but sufficient for the frontend to update state without a full refetch in the normal path.

Example `crawler.run.updated` payload:

```json
{
  "id": "run-id",
  "task_id": "task-id",
  "task_name": "JavDB VR 女优列表",
  "status": "running",
  "crawl_mode": "incremental",
  "queued_at": "2026-07-03T08:00:00",
  "started_at": "2026-07-03T08:00:01",
  "finished_at": null,
  "result": null,
  "error": null
}
```

Example `crawler.run.detail.updated` payload:

```json
{
  "run_id": "run-id",
  "tasks": [
    {
      "id": "detail-id",
      "code": "ABC-001",
      "source_url": "https://javdb.com/v/abc001",
      "source_name": "ABC-001",
      "status": "saved",
      "error": null,
      "crawled_at": "2026-07-03T08:02:00",
      "saved_at": "2026-07-03T08:02:03"
    }
  ]
}
```

Example `crawler.run.log.appended` payload:

```json
{
  "run_id": "run-id",
  "log": {
    "timestamp": "2026-07-03T08:02:03",
    "level": "INFO",
    "component": "crawler.run",
    "event": "run_log",
    "message": "入库成功: ABC-001",
    "context": {
      "code": "ABC-001"
    }
  }
}
```

## Frontend Design

Create `frontend/src/realtime`.

### `types.ts`

Define:

```ts
export type RealtimeEvent<TPayload = Record<string, unknown>> = {
  id: string
  event: string
  scope: string
  resource_id: string | null
  owner_id: string
  payload: TPayload
  created_at: string
}
```

Define specific payload types for crawler events used in the first phase.

### `eventSourceClient.ts`

Responsibilities:

- Read the current JWT token from the existing auth utility.
- Build the stream URL: `/api/events/stream?token=<encoded token>`.
- Hold one EventSource instance per browser tab.
- Expose `connect()`, `disconnect()`, `subscribe(eventName, handler)`, and `getConnectionState()`.
- Use native EventSource reconnection.
- On reconnect after an error, emit a local `resync` notification so active pages can refetch snapshots.
- Do nothing when no token exists.

### Run Detail Page

`RunDetailPage` keeps the current initial snapshot:

- `getCrawlerRun(id)`
- `getCrawlerRunTasks(id, { limit: 200, status, keyword })`

Then it subscribes to:

- `crawler.run.updated`
- `crawler.run.detail.updated`
- `crawler.run.log.appended`
- `system.resync_required`

Filtering rules:

- Ignore events whose `resource_id` does not match the current run id.
- For detail events, ignore updates whose `payload.run_id` does not match the current run id.
- Apply current `statusFilter` and `keyword` before inserting/updating detail rows.
- On resync, refetch the run and current filtered detail list through REST.

Remove both existing `setInterval` loops from `RunDetailPage`.

## Cloud Storage Fit

SSE is suitable for cloud storage status updates because those flows are also server-to-client progress streams:

- upload or transfer queued/running/completed/failed
- directory scan progress
- matched/unmatched file results
- delete progress for the future cloud-delete task mode
- batch progress counts
- log append events

Commands such as pause, retry, delete, or change settings should remain REST endpoints. Their resulting status changes should be published through SSE.

Cloud storage should use the same event envelope and these reserved event types:

- `cloud.storage.task.updated`
- `cloud.storage.transfer.progress`
- `cloud.storage.file.matched`
- `cloud.storage.delete.updated`
- `cloud.storage.log.appended`

## Error Handling

- Missing or invalid token: stream endpoint rejects the connection.
- Network disconnect: EventSource reconnects automatically.
- Reconnect after disconnect: frontend refetches active REST snapshots.
- Event queue overflow: backend sends `system.resync_required` and clears old queued events for that connection.
- Unknown event type: frontend ignores it.
- Malformed event payload: frontend logs the parse failure and triggers a snapshot resync for the active page.

## Security

The stream uses query token authentication because browser `EventSource` cannot set custom headers.

Constraints:

- Token must be URL encoded.
- Do not log full stream URLs.
- Do not include token values in error messages.
- Stream events only to connections authenticated as the matching `owner_id`.
- Business event payloads must not include secrets, cookies, raw authorization headers, or cloud storage credentials.

## Testing

Backend tests:

- SSE endpoint rejects missing token.
- SSE endpoint rejects invalid token.
- SSE endpoint accepts a valid token and emits `system.connected`.
- Publishing an event with `owner_id=A` is received only by user A.
- Crawler run state changes publish `crawler.run.updated`.
- Appending a run log publishes `crawler.run.log.appended`.
- Queue overflow emits `system.resync_required`.

Frontend tests:

- EventSource client builds URL with encoded token.
- EventSource client does not connect without a token.
- Event listeners receive parsed realtime events.
- Reconnect/resync signal triggers active page snapshot refetch.
- `RunDetailPage` updates run status from `crawler.run.updated`.
- `RunDetailPage` upserts detail rows from `crawler.run.detail.updated`.
- `RunDetailPage` appends log entries from `crawler.run.log.appended`.
- `RunDetailPage` no longer calls `window.setInterval`.

## Rollout

1. Add the generic realtime module and SSE endpoint.
2. Add frontend realtime client.
3. Publish crawler run events from runtime service.
4. Replace run detail polling with SSE subscriptions.
5. Keep REST snapshots as the fallback and resync path.
6. Leave task list, movie list, and cloud storage integrations for future event consumers using the same event schema.

## Success Criteria

- Active run detail pages update status, detail task rows, and logs without timer polling.
- Stopping or completing a run updates the page without waiting for a 3-second interval.
- Disconnect/reconnect does not leave the run detail page stale because it refetches the REST snapshot.
- The event schema can describe both crawler and future cloud storage progress events.
- Existing REST endpoints remain usable and continue to provide initial snapshots.
