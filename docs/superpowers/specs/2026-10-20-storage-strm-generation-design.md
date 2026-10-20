# Storage-Queue-Idle STRM Generation Design

## Context

Media Forge moves downloaded media through storage tasks. After the storage
queue has fully drained, an external STRM service must be told to generate
STRM files for a configured directory. The external call is a single HTTP
request:

```text
POST {base_url}/api/sync/path/start?api_key=...
Content-Type: application/json

{"id": 4}
```

The trigger must happen only after every storage main task has finished and no
storage task is waiting. The behavior needs to be configurable from the UI and
also runnable on demand for validation.

The trigger is global: the storage queue is shared by all users and tasks, and
there is exactly one configured external directory. Any drain of that queue
schedules the same directory sync.

## Goals

- Add an independent backend module named `scraping` and a frontend module
  named `scraping`.
- Persist the external service base URL, API key, directory ID, and a trigger
  delay.
- After the storage worker drains, wait for the configured delay, then trigger
  STRM generation exactly once if the storage worker is still idle.
- Restart the delay whenever a new storage task appears during the delay
  window.
- Provide a `刮削 / 刮削配置` page with the configuration form, a save action,
  and a manual `立即生成` action.
- Keep failure handling minimal: automatic failures are logged, never retried.

## Non-Goals

- No trigger history or result panel.
- No automatic retry of failed external calls.
- No new database tables or migrations.
- No per-user or per-directory configuration; one global directory ID.
- No change to storage worker queue semantics or storage task statuses.
- No change to authentication, authorization, or user permissions.

## Module Boundary

Backend files:

```text
backend/app/modules/scraping/
  __init__.py
  schemas.py
  config.py
  strm.py
  trigger.py
  router.py
```

Frontend files:

```text
frontend/src/api/scraping/scrapingConfig/
  index.ts
  types.ts
frontend/src/pages/scraping/config/
  ScrapingConfigPage.tsx
  ScrapingConfigPage.module.less
```

API prefix: `/api/scraping`.

Frontend route: `/scraping/config`.

Sidebar: a new `刮削` group (`ScissorOutlined`) placed after `存储`, containing
`刮削配置` (`SettingOutlined`).

## Configuration

### Fields

| Field | Default | Validation |
| --- | --- | --- |
| `base_url` | `http://192.168.0.36:12333` | When non-empty, must start with `http://` or `https://`; surrounding whitespace and trailing `/` are removed on save |
| `api_key` | `""` | Masked on read; empty or masked submissions keep the stored value |
| `directory_id` | `null` | Integer, `>= 1`; `null` clears it |
| `trigger_delay_seconds` | `30` | Integer, `10 <= value <= 3600` |

`trigger_delay_seconds` is the quiet period after the queue drains. The user
can change it; the minimum prevents an accidental immediate call.

### Persistence

Configuration is stored in `data/configs/scraping.conf` in dotenv form,
matching `storage.conf` and `backup.conf`:

```text
base_url=https://2756e03c9b1c-1.eastwood951220.5ddd.com
api_key=secret-key
directory_id=4
trigger_delay_seconds=30
```

- `ScrapingConfigService(config_file: Path | None = None)` resolves the default
  path from `RuntimeConfigPaths.from_env().config_dir / "scraping.conf"`, so
  `APP_CONFIG_DIR` is honored in tests and deployments.
- Reads go through `dotenv_values(..., interpolate=False)`; writes use a
  temporary file and `replace()` so readers never observe a partial file.
  Disabling interpolation keeps `$` sequences in API keys literal.
- Only `directory_id` and `trigger_delay_seconds` are coerced to integers.
  `base_url` and `api_key` always remain strings, so an all-digit API key is
  never converted to a number.
- Values are single-line. Strings containing whitespace or `#` are quoted with
  `json.dumps`; this keeps URLs and keys parseable.
- The API key is stored in plaintext, consistent with `storage.conf`. The file
  must not be logged.
- Each automatic and manual trigger re-reads the file, so saving a new
  configuration does not require a backend restart.
- Invalid persisted values are tolerated: an unparseable `directory_id` becomes
  `null`, and an out-of-range `trigger_delay_seconds` falls back to `30`.
  This prevents a hand-edited file from breaking the settings page.

### Public Config Shape

`GET /api/scraping/config` returns:

```json
{
  "base_url": "https://example.com",
  "api_key": "************1234",
  "api_key_configured": true,
  "directory_id": 4,
  "trigger_delay_seconds": 30
}
```

Masking uses the same rules as storage config: keys shorter than 8 characters
become `****`; longer keys become 12 asterisks plus the last 4 characters.

`PUT /api/scraping/config` accepts any subset of:

```json
{
  "base_url": "https://example.com/",
  "api_key": "new-key",
  "directory_id": 4,
  "trigger_delay_seconds": 30
}
```

Update semantics:

- Use `model_dump(exclude_unset=True)` so omitted fields keep their stored
  values while explicit `null` can clear `directory_id`.
- If `api_key` is omitted, empty, or a masked value, the stored key is kept.
  No separate clear-key action is provided.
- `base_url` is trimmed and trailing slashes are removed; an empty string or
  explicit `null` clears it.
- Invalid `base_url` raises a validation error handled as HTTP 400. Numeric
  range violations are rejected by Pydantic field constraints (HTTP 422).

## Trigger Lifecycle

### Drain Detection

`storage/worker/runner.py` tracks whether the current worker run processed at
least one main task. After the existing double-check confirms that
`claim_next_main_task()` returns `None`:

1. Set `_worker_running = False` while holding `_worker_lock`, so a newly
   enqueued task can start a fresh worker immediately.
2. If the run processed at least one main task, call
   `schedule_strm_after_storage_drain(runtime, is_worker_idle=is_storage_worker_idle)`.
3. Return from the worker loop.

`is_storage_worker_idle()` is a small helper in `runner.py` that reads
`_worker_running` under `_worker_lock`; the trigger thread passes it into the
delayed check, so idle state is always read at wake-up time.

If the worker never claimed a task, it does not schedule a trigger. If the
worker loop crashes, it does not schedule a trigger.

The scheduling call is wrapped in `try/except` and only logs, so a scraping
problem can never keep the storage worker alive or break storage processing.

### Delayed Check

`scraping/trigger.py` owns the delay and the idle checks:

- A module-level generation counter is incremented for every scheduled check.
  A check captures its generation and aborts after sleeping if a newer
  generation exists. This makes a newer drain invalidate an older pending
  check.
- The check sleeps for the `trigger_delay_seconds` value captured when it was
  scheduled. A configuration change during the sleep applies to the next
  drain, not to the in-flight check.
- The thread is a daemon named `strm-trigger-<generation>`; it never blocks
  application shutdown.

At wake-up, the check runs these checks in order:

1. Its generation is still current.
2. `is_worker_idle()` is true, meaning `_worker_running` is false.
3. `runtime.pending_main_task_count()` is zero (Redis
   `storage:main_queue` has no queued task IDs).
4. A fresh database session finds no `StorageMainTask` in `queued`, `running`,
   or `stopping`.

Only if all four pass does it re-read the configuration, re-validate it, and
perform the external request. Any failed check logs at INFO/DEBUG and exits;
the next drain schedules a fresh check.

### New Tasks During the Delay

- If a new storage task starts before the check wakes, the worker is busy or
  the queue is non-empty when the check wakes, so it exits. When that new batch
  drains, a new full delay starts.
- If a short new batch finishes before the old check wakes, the new drain
  increments the generation. The old check wakes, sees a stale generation, and
  exits. The new check waits its own full delay.
- The Redis and database checks close the window between "task enqueued" and
  "worker starts", including the restart/retry path that pushes to Redis
  before committing the database status.

A microscopic window remains between the final idle check and the HTTP call.
If a task is enqueued in that window it may overlap with the external request.
Closing it entirely would require holding a global storage lock across a
network call, which is not acceptable.

### Idle Check Failure Policy

If Redis or the database cannot be queried, the check treats the worker as
not confirmed idle and skips the trigger. This is a safety-first default: a
missed trigger is recoverable with the manual button, while a premature
trigger is not.

### Process Model Assumption

The trigger state is in-process. The current deployment runs one backend
process with one storage worker. If the backend restarts during the delay, the
pending check is lost. After restart, only a new drain or the manual button
triggers the service. Multi-process deployment is out of scope; multiple
workers would each schedule checks, and the Redis/database checks would not
deduplicate a call that already passed them.

## External STRM Request

`scraping/strm.py` exposes:

```python
@dataclass
class StrmRunResult:
    success: bool
    status_code: int | None
    message: str


def run_strm_generation(
    config: Mapping[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
) -> StrmRunResult:
    ...
```

Behavior:

- Build `{base_url}/api/sync/path/start` after stripping trailing slashes.
- Send `POST` with `params={"api_key": api_key}` and `json={"id": directory_id}`.
- Use a 30-second timeout (`httpx.Timeout(30.0)`).
- Any 2xx response is success. `raise_for_status()` is used to classify non-2xx
  responses.
- The success message is `HTTP <status>` plus a short response-body excerpt
  when the body is non-empty. The failure message is `HTTP <status>: <excerpt>`
  or `<exception type>: <safe text>` for network errors.
- Body excerpts are collapsed to a single line and truncated to 300
  characters.
- Every message is passed through a redaction helper that replaces the
  configured `api_key` value with `***`. Full URLs are never logged, because
  the key is a query parameter and exception strings can contain the URL.
  Logging never forwards raw httpx exceptions through `exc_info`; only the
  redacted result or a safe reason is logged.
- No retries. A failed automatic call is logged once with status/safe reason.

A `validate_run_config(config)` helper returns a human-readable reason when
`base_url`, `api_key`, or `directory_id` is missing, and `None` when the
configuration is runnable. Both the trigger and the manual endpoint use it.

## Backend API

All endpoints require the standard authenticated user dependency.

### `GET /api/scraping/config`

Returns the public config shape above inside the standard success envelope.

### `PUT /api/scraping/config`

Accepts a partial update, persists it, and returns the updated public config.
Validation errors return 400 or 422 as described above.

### `POST /api/scraping/strm/run`

Synchronous manual trigger using the saved configuration. It runs immediately
and does not wait for, or require, an idle storage queue.

- Unconfigured or incomplete configuration: HTTP 400 with a clear detail
  message.
- External request completed (success or failure): HTTP 200 with
  `{"success": bool, "status_code": int|null, "message": str}`.

Returning 200 for a failed external call lets the page show one explicit
success/error toast instead of relying on the global HTTP error toast.

## Frontend

### Routing and Navigation

- Add a lazy route `/scraping/config` in `frontend/src/routes/index.tsx`.
- Add metadata in `frontend/src/routes/tags.ts`:
  - path: `/scraping/config`
  - title: `刮削配置`
- Add the sidebar group after `存储` and update `selectedKey`/`openKeys`.
- Update `frontend/README.md` with the new route and page module.

### Page Layout

`ScrapingConfigPage.tsx` renders two cards:

1. **服务配置**
   - `服务地址`: text input, default/placeholder
     `http://192.168.0.36:12333`.
   - `API Key`: password input. When a key is configured, show a `已配置` tag
     with the masked value. Leaving the input empty keeps the stored key.
   - `目录 ID`: number input, minimum 1, placeholder `4`.
2. **自动触发**
   - `触发等待时间（秒）`: number input, minimum 10, maximum 3600.
   - An explanatory alert: "存储队列空闲 N 秒后自动调用；等待期间有新任务会
     重新计时。" where N is the current form value (fallback 30).

Actions:

- Form validation requires `服务地址`, `目录 ID`, and `触发等待时间`; `API Key`
  is required only when no key is currently configured. Saves are therefore
  always runnable.
- `保存配置`: validates the form, sends `PUT`, shows a success toast, updates
  the form with the masked response, and clears the API-key input.
- `立即生成`: validates the form, saves it first (same `PUT`), then calls
  `POST /api/scraping/strm/run`. This guarantees that what the user sees is
  what runs. Shows one success or error toast from the run result. The button
  is disabled while saving or running.

The page loads the saved config on mount and displays a loading state while
the request is in flight.

### API Module

`frontend/src/api/scraping/scrapingConfig/index.ts` exports:

```ts
getScrapingConfig(): Promise<ScrapingConfig>
updateScrapingConfig(payload: ScrapingConfigUpdate): Promise<ScrapingConfig>
runScrapingStrm(): Promise<ScrapingRunResult>
```

Types in `types.ts`:

```ts
interface ScrapingConfig {
  base_url: string
  api_key: string
  api_key_configured: boolean
  directory_id: number | null
  trigger_delay_seconds: number
}

interface ScrapingConfigUpdate {
  base_url?: string
  api_key?: string
  directory_id?: number | null
  trigger_delay_seconds?: number
}

interface ScrapingRunResult {
  success: boolean
  status_code: number | null
  message: string
}
```

## Testing

### Backend

`backend/tests/test_scraping_config_api.py`:

- Defaults when no file exists.
- Write produces `scraping.conf` with the expected dotenv content.
- API key is masked on read and preserved when the client submits the masked
  value or an empty value.
- `directory_id` can be cleared with an explicit `null`.
- Invalid base URL returns 400.
- Out-of-range directory ID or delay returns 422.
- GET/PUT responses use the standard success envelope.

`backend/tests/test_scraping_strm_trigger.py`:

- `run_strm_generation` with `httpx.MockTransport` sends POST to
  `/api/sync/path/start`, puts `api_key` in the query string, and sends
  `{"id": 4}`.
- 2xx response produces success; non-2xx and network failures produce
  `success=False` without raising.
- API-key redaction removes the key from messages.
- Scheduled check does not call the service when the worker is busy, when
  Redis has a pending task, or when the database has a pending task.
- Scheduled check calls the service when idle.
- A stale generation does not call the service.
- The manual endpoint returns the result on success, 400 when unconfigured,
  and 200 with `success=false` on external failure.

`backend/tests/test_storage_worker_service.py`:

- Update the existing worker-loop recheck test to stub the scheduling function.
- Assert scheduling happens after a drain when a task was processed.
- Assert scheduling does not happen when the worker never processed a task.

`backend/tests/test_storage_runtime_redis.py`:

- Extend the fake Redis with `llen` and cover `pending_main_task_count()`.

### Frontend

- Add a focused `ScrapingConfigPage` test:
  - loads and renders the saved values;
  - saving after touching only `base_url` does not send `api_key`;
  - `立即生成` calls the update endpoint before the run endpoint.
- Run `pnpm build`.
- Run focused Vitest for the new page.

## Verification

Backend:

```bash
cd backend
python -m pytest tests/test_scraping_config_api.py tests/test_scraping_strm_trigger.py tests/test_storage_worker_service.py tests/test_storage_runtime_redis.py -v
python -m pytest tests/test_storage_tasks_api.py tests/test_storage_config_api.py -v
```

Frontend:

```bash
cd frontend
pnpm build
pnpm test -- src/pages/scraping
```

Manual smoke:

1. Save a valid config and click `立即生成`; the external service receives one
   request with the configured key and directory ID.
2. Run a storage batch; after the queue drains, the call happens after the
   configured delay.
3. Create another storage task during the delay; no early call happens, and
   the timer restarts after the new batch drains.
4. Leave the config incomplete; no automatic call happens and an info log is
   written.
5. Point the config at an unreachable host; only a warning log is written and
   storage tasks are unaffected.

## File Changes

New backend:

- `backend/app/modules/scraping/__init__.py`
- `backend/app/modules/scraping/schemas.py`
- `backend/app/modules/scraping/config.py`
- `backend/app/modules/scraping/strm.py`
- `backend/app/modules/scraping/trigger.py`
- `backend/app/modules/scraping/router.py`
- `backend/tests/test_scraping_config_api.py`
- `backend/tests/test_scraping_strm_trigger.py`

Modified backend:

- `backend/app/main.py` (register the router)
- `backend/app/modules/storage/worker/runner.py` (drain hook, idle helper)
- `backend/app/modules/storage/runtime/redis_state.py` (`pending_main_task_count`)
- `backend/tests/test_storage_worker_service.py`
- `backend/tests/test_storage_runtime_redis.py`

New frontend:

- `frontend/src/api/scraping/scrapingConfig/index.ts`
- `frontend/src/api/scraping/scrapingConfig/types.ts`
- `frontend/src/pages/scraping/config/ScrapingConfigPage.tsx`
- `frontend/src/pages/scraping/config/ScrapingConfigPage.module.less`
- `frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx`

Modified frontend:

- `frontend/src/routes/index.tsx`
- `frontend/src/routes/tags.ts`
- `frontend/src/layout/Sidebar/index.tsx`
- `frontend/README.md`

Documentation:

- `docs/superpowers/specs/2026-10-20-storage-strm-generation-design.md`

## Risks and Assumptions

- The external service treats repeated starts as idempotent; the design does
  not add deduplication beyond the generation and idle checks.
- The backend runs as a single process with a single storage worker.
- A restart during the delay loses the pending check.
- The API key is stored in plaintext in `scraping.conf`, consistent with
  existing configuration files.
- A manual run can take up to 30 seconds if the external service is slow; the
  page keeps the button in a loading state.
