# Scraping Directory Status and Scraping Tasks Design

## Context

Media Forge already has a `scraping` module that triggers an external STRM
service: after the storage queue drains (or on demand), it calls
`POST {base_url}/api/sync/path/start` for one configured directory
(`data/configs/scraping.conf`). That external service generates STRM files and
artwork inside a media library directory. Media Forge currently has no
visibility into the resulting folders and no way to produce metadata itself.

The media library is stored in CloudDrive2 under a cloud path such as
`/media/<storage_location>/<code>` (for example
`/media/北野未奈/ADN-784`). A scraped movie folder looks like this:

```text
/media/北野未奈/ADN-784/
  ADN-784.strm
  movie.nfo
  folder.jpg
  backdrop.jpg
  landscape.jpg
```

The `movie.nfo` file is metatube-style XML: it carries title, original title,
year, mpaa, release dates, tagline, genres, tags, studio, set, an `art` block
pointing at `folder.jpg` and `backdrop.jpg`, and a `metatubeid` such as
`JavBus:ADN-784`.

The product needs to: configure the scraping directory, scan it to decide
whether each movie folder is scraped, scrape metadata (nfo + images) with
javdb/javbus priority, show a scraping status in the movie list, and run
single/batch scraping with persistent tasks and progress.

## Goals

- Add scraping directory configuration: local scan root, cloud media root, and
  an ordered list of metadata sources (javdb, javbus; javlibrary later).
- Scan the local scraping directory recursively and decide, per movie folder,
  whether it is scraped: `*.strm` + `movie.nfo` + at least one image.
- Persist a scraping status on `movies` (already-scraped / not-scraped) that
  is only meaningful for stored movies.
- Scrape a stored movie into its existing media folder: generate `movie.nfo`
  and artwork, using DB metadata first and crawling missing fields from the
  configured sources in priority order. Never create folders.
- Add persistent scraping tasks with a list page and a detail page, progress,
  cancellation, and retry of failed/skipped items.
- Add a scraping status column and scrape / batch-scrape actions to the movie
  list.
- Make the crawler run records page, the storage task list, and the new
  scraping task list uncached lists: they must reload whenever the user enters
  them, and each renders a card header with a title and a refresh button
  (matching the storage task list).

## Non-Goals

- No button hiding/conditional visibility in the movie list in this iteration.
  Buttons stay visible; availability rules are a follow-up.
- No multiple scraping directories. One global `scrape_root` /
  `media_root` pair.
- No scraping of movies that are not stored, and no folder creation.
- No `javlibrary` adapter; only the registry is designed to accept it later.
- No scheduled/periodic scans; refreshes are manual or event-driven.
- No changes to storage task semantics, storage statuses, or the external STRM
  request contract.
- No filtering of the movie list by scraping status (only a column).
- No per-user media libraries; `movies` and their scraping status are global.

## Confirmed Decisions

| Decision point | Decision |
| --- | --- |
| Who executes scraping | External service creates STRM; Media Forge writes `movie.nfo` + images |
| Scraping directory | One global directory (reuses the existing `directory_id`) |
| Movie → folder mapping | Storage `target_folder` derivation first, folder-name code extraction as fallback |
| Status storage | New `movies` columns, list reads the DB |
| Batch execution | Persistent task tables + task list/detail pages + progress |
| Metadata source strategy | DB first, crawl only missing fields, first successful source wins |
| Scraped judgment | `*.strm` + `movie.nfo` + at least one image |
| Missing folder/STRM | Only write into existing folders; otherwise the item is skipped |
| Status refresh | Manual full scan + event-triggered recheck (no timer) |
| Button visibility | Unchanged in this iteration |

## Glossary

- **Scrape root** (`scrape_root`): absolute local path the backend scans, e.g.
  `/mnt/cd2/media`. It is a mount of the cloud media library.
- **Media root** (`media_root`): the cloud path that `scrape_root` maps to,
  e.g. `/media`.
- **Media folder**: the cloud folder of one movie,
  `{storage target_folder}` such as `/media/北野未奈/ADN-784`.
- **Scraped**: the media folder contains a `*.strm` file, `movie.nfo`, and at
  least one `.jpg`/`.jpeg`/`.png` image.
- **Scraping task**: one persisted batch of movies to scrape.

## Architecture

```text
Movies list ──► POST /api/scraping/tasks ──► scraping_tasks + items (queued)
                                                    │
                                    scraping worker (single thread)
                                                    │
              ┌─────────────────────────────────────┼──────────────────────┐
              ▼                                     ▼                      ▼
      resolve media folder               metadata (DB first,         write movie.nfo
      (target_folder / scan)             then javdb → javbus)        + images, recheck
                                                    │
                                                    ▼
                                      movies.scraping_status + realtime events

Config page ──► POST /api/scraping/scan ──► full directory scan ──► movies columns
STRM trigger success (auto/manual) ──────► background full scan ──► movies columns
```

Backend files:

```text
backend/app/models/scraping_task.py            # ScrapingTask, ScrapingTaskItem
backend/app/modules/scraping/
  config.py                                    # extended config service
  schemas.py                                   # extended config schemas
  scan.py                                      # directory walk + status judgment
  paths.py                                     # local/cloud path mapping + code normalization
  nfo.py                                       # movie.nfo renderer/writer
  images.py                                    # artwork downloader
  sources.py                                   # metadata source registry (javdb, javbus)
  tasks/
    service.py                                 # create/list/get/cancel/retry
    worker.py                                  # single-thread task runner
    item_runner.py                             # per-movie scrape pipeline
    events.py                                  # realtime publishing
    schemas.py                                 # task request/response schemas
  router.py                                    # extended routes
backend/alembic/versions/20261020_0001_add_scraping_status_and_tasks.py
```

Frontend files:

```text
frontend/src/api/scraping/scrapingConfig/      # extended types + scan call
frontend/src/api/scraping/scrapingTasks/       # task API module
frontend/src/pages/scraping/tasks/
  TaskListPage.tsx
  TaskDetailPage.tsx
  components/  hooks/  utils/  __tests__/
frontend/src/pages/scraping/config/ScrapingConfigPage.tsx   # extended form + scan
frontend/src/pages/content/movies/components/MovieTable.tsx # status column + scrape action
frontend/src/pages/content/movies/MovieListPage.tsx         # batch scrape button
frontend/src/pages/content/movies/hooks/useMovieScraping.ts # task creation + realtime
frontend/src/layout/routeCacheControl.ts                    # uncached list pages
frontend/src/pages/crawler/runs/RunListPage.tsx              # title + refresh header
```

## Data Model

### `movies` columns

Added by the migration, SQLite-compatible (no server defaults):

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `scraping_status` | `String(20)` | yes | `scraped`, `not_scraped`, or `NULL` when the movie is not stored / never checked |
| `scraping_folder` | `Text` | yes | Cloud media folder that was judged, e.g. `/media/北野未奈/ADN-784` |
| `scraping_checked_at` | `DateTime` | yes | Last successful judgment time |

- `scraping_status` is written only when the movie's normalized storage status
  is `stored`.
- The list serializer returns all three fields; the UI renders `-` when
  `scraping_status` is `NULL`.

### `scraping_tasks`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `status` | `String(30)` | `queued`, `running`, `success`, `partial_failed`, `failed`, `cancelled` |
| `total_count` | Integer | Items created |
| `success_count` | Integer | Items that wrote nfo + at least one image |
| `failed_count` | Integer | Items that hit an error |
| `skipped_count` | Integer | Items whose preconditions were not met (not stored, folder missing) |
| `cancel_requested` | Boolean | Cooperative cancellation flag |
| `config_snapshot` | JSON | `scrape_root`, `media_root`, `metadata_sources` at creation time |
| `created_by` | UUID FK `users.id` | Owner |
| `queued_at`, `started_at`, `finished_at` | DateTime, nullable | |
| `error_message` | Text, nullable | Last fatal error |

Indexes: `(status, created_at)`, `(created_by, status)`.

### `scraping_task_items`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `task_id` | UUID FK `scraping_tasks.id` ON DELETE CASCADE | |
| `movie_id` | UUID FK `movies.id` ON DELETE CASCADE | |
| `movie_code` | `String(100)` | Snapshot for display |
| `movie_title` | Text | Snapshot for display |
| `status` | `String(30)` | `pending`, `running`, `success`, `failed`, `skipped` |
| `source` | `String(30)`, default `""` | Source key actually used (`javdb`, `javbus`, or empty) |
| `folder` | Text, default `""` | Cloud media folder |
| `duration_ms` | Integer, default 0 | |
| `error_message` | Text, nullable | Skip reason or failure detail |

Indexes: `(task_id, status)`, `(created_at)`.

Models live in `backend/app/models/scraping_task.py` following
`storage_task.py` conventions (`Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin`,
`CompatibleJSON`).

## Configuration

`data/configs/scraping.conf` gains three fields; existing fields keep their
semantics:

| Field | Default | Validation |
| --- | --- | --- |
| `scrape_root` | `""` | Absolute path; when non-empty it must exist and be a directory (validated on save and at scan time) |
| `media_root` | `/media` | Absolute path starting with `/`; trailing `/` removed; must not be `/` |
| `metadata_sources` | `["javdb","javbus"]` | Non-empty JSON array; every key must be in the source registry; order = priority |
| `base_url`, `api_key`, `directory_id`, `trigger_delay_seconds` | unchanged | unchanged |

Persistence rules:

- `metadata_sources` is stored in the dotenv file as a JSON string
  (`metadata_sources=["javdb", "javbus"]`); the dotenv writer already quotes
  values containing spaces or `#`.
- Invalid persisted values must not break the page: an unparseable
  `metadata_sources` falls back to the default list; an invalid `media_root`
  falls back to `/media`; `scrape_root` is returned as stored and only
  validated when saving/scanning.
- `GET /api/scraping/config` returns `scrape_root`, `media_root`,
  `metadata_sources`, and the existing fields, plus `api_key_configured`.
- `PUT /api/scraping/config` uses partial-update semantics (omitted fields keep
  stored values). Validation errors return 400.

Path mapping (`paths.py`):

```python
def local_folder(scrape_root, media_root, cloud_folder) -> str | None
def cloud_folder(scrape_root, media_root, local_folder) -> str | None
```

- `cloud_folder` must equal `media_root` or start with `media_root + "/"`;
  otherwise the mapping is `None`.
- `local_folder` joins `scrape_root` with the cloud path after removing the
  `media_root` prefix.
- All joins use `PurePosixPath` semantics for cloud paths and `Path` for local
  paths; the local result is resolved and must stay under `scrape_root`.

## Metadata Source Registry

`sources.py` exposes:

```python
@dataclass
class SourceMetadata:
    site_key: str          # e.g. "JavBus"
    title: str | None
    original_title: str | None
    year: int | None
    premiered: str | None  # ISO date
    genres: list[str]
    tags: list[str]
    studio: str | None
    series: str | None
    actors: list[str]
    cover_url: str | None
    backdrop_url: str | None
    landscape_url: str | None


SOURCE_REGISTRY: dict[str, SourceAdapter]  # "javdb", "javbus"
SOURCE_LABELS: dict[str, str]              # display names for the config page
```

- Each adapter searches by normalized code and fetches detail using the
  existing `scraper.fetchers` + javdb/javbus parsers, reusing the existing
  cookie and throttle handling. Adapters must never raise to the caller; they
  return `None` on failure and log a warning.
- Adding `javlibrary` later means adding one adapter class and registering it;
  configuration validation and the config page pick it up from the registry.
- Priority semantics: the scraping pipeline collects the fields that are
  missing from the DB row (`cover`, `actors`, `release_date`, `maker`,
  `series`, `tags`). It walks sources in configured order and fills still
  missing fields from the first source that returns data; the recorded `source`
  is the first source that supplied any field. When no source is needed the
  item `source` is empty and `metatubeid` is omitted from the nfo.

## Scan and Status Judgment

`scan.py` exposes:

```python
@dataclass
class ScanSummary:
    folders_scanned: int
    folders_with_strm: int
    scraped_folders: int
    not_scraped_folders: int
    matched_movies: int
    updated_movies: int
    unmatched_folders: list[str]  # capped at 50 entries
    duration_ms: int
```

Algorithm (`scan_directory(db, config) -> ScanSummary`):

1. Walk `scrape_root` recursively. Skip hidden directories (names starting with
   `.`), do not follow directory symlinks, cap depth at 8 to avoid runaway
   trees, and ignore permission errors per folder (log once per path).
2. A folder is a candidate when it contains at least one file ending in
   `.strm` (case-insensitive).
3. Scraped judgment: candidate + `movie.nfo` present (case-insensitive) + at
   least one `.jpg`/`.jpeg`/`.png` file. Otherwise `not_scraped`.
4. Build a `normalized code → Movie` map for all stored movies (see
   `storage_status.py` for the normalized storage status). Normalization:
   uppercase, remove every character that is not `A-Z0-9`.
5. Match candidates to movies deterministically, then resolve conflicts:
   - Exact pass: derive the expected cloud folder from
     `storage_summary.locations[].target_folder` (most recent location first)
     and compute the local folder via `paths.local_folder`. When that folder
     exists and is the folder being visited, it is an exact match.
   - Fallback pass: extract a code from the folder name with the regex
     `[A-Za-z]{2,6}[-_ ]?\d{2,6}(?:[-_ ][A-Za-z]{1,4})?`, normalize it, and
     look it up in the map.
   - A folder matches at most one movie and a movie matches at most one
     folder. When a movie has several candidate folders (the `-C`/`-U`/`-UC`
     variants), the exact `target_folder` match wins; otherwise the
     lexicographically smallest path wins.
6. Update only stored movies whose storage locations map under `media_root`:
   set `scraping_status`, `scraping_folder` (cloud folder), and
   `scraping_checked_at`; count them in `updated_movies`.
7. Status cleanup for movies in scan scope that were not matched: stored
   movies whose locations map under `media_root` but have no folder in the
   tree become `not_scraped` with `scraping_folder` cleared and a fresh
   `scraping_checked_at`. Movies that are no longer stored have their scraping
   fields cleared. Movies whose storage locations do not map under
   `media_root` are outside the scan scope and keep their previous fields.
8. Unmatched candidate folders are reported (capped) but do not change movies.

Per-movie recheck (`refresh_movie_statuses(db, movie_ids)`):

- Used by the scraping worker after each item and by event-triggered refreshes.
- Resolve the folder from the movie's storage locations first; when that fails,
  fall back to a folder-name lookup in the scan index.
- Judgment and persistence follow steps 3–6; movies that are no longer stored
  have their scraping fields cleared.

Triggers:

- `POST /api/scraping/scan` runs `scan_directory` synchronously (pure
  filesystem walk, no network) and returns the summary.
- After the external STRM request succeeds (automatic or manual), the scraping
  module schedules a daemon-thread scan (same process, no delay) so newly
  generated folders are reflected without user action.
- Scraping task items always recheck their own movie after writing files.
- No periodic timer; a manual scan is the recovery path.

## nfo and Artwork Generation

`nfo.py` renders the metatube-style document with `xml.etree.ElementTree`
(escaping handled by the library), UTF-8 with an XML declaration, two-space
indent, and writes atomically (temp file + `replace`) into the media folder:

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <plot />
  <lockdata>false</lockdata>
  <dateadded>2026-10-20 12:00:00</dateadded>
  <title>ADN-784 あなた、許して…。</title>
  <originaltitle>あなた、許して…。</originaltitle>
  <year>2026</year>
  <mpaa>JP-18+</mpaa>
  <premiered>2026-07-03</premiered>
  <releasedate>2026-07-03</releasedate>
  <tagline>配信開始日 2026-07-03</tagline>
  <genre>ドラマ</genre>
  <studio>アタッカーズ</studio>
  <tag>アタッカーズ</tag>
  <metatubeid>JavBus:ADN-784</metatubeid>
  <art>
    <poster>/media/北野未奈/ADN-784/folder.jpg</poster>
    <fanart>/media/北野未奈/ADN-784/backdrop.jpg</fanart>
  </art>
  <set>
    <name>あなた、許して…。</name>
  </set>
  <fileinfo>
    <streamdetails />
  </fileinfo>
</movie>
```

Field mapping:

| nfo element | Source |
| --- | --- |
| `title` | `source_name`, prefixed with `code ` when it does not already start with the code |
| `originaltitle` | `source_name` with a leading `code ` removed |
| `year` | `release_date.year` |
| `mpaa` | always `JP-18+` |
| `premiered`, `releasedate` | `release_date` ISO |
| `tagline` | `配信開始日 {release_date}` when a release date exists, otherwise omitted |
| `genre` | one element per `tags` entry |
| `studio` | `maker` |
| `tag` | `maker`, then `series`, then each `tags` entry (deduped) |
| `set/name` | `series` when non-empty, otherwise omitted |
| `art/poster`, `art/fanart` | `{cloud folder}/folder.jpg`, `{cloud folder}/backdrop.jpg` |
| `metatubeid` | `{source.site_key}:{code}` when a source supplied data, otherwise omitted |
| `dateadded` | local time at write, `YYYY-MM-DD HH:MM:SS` |

`images.py` downloads artwork with `httpx` (30 s timeout, 20 MB cap) using the
source adapter's required headers (for example a `Referer` for javdb):

- `cover_url` → `folder.jpg` (required for a successful item).
- `backdrop_url` → `backdrop.jpg` and `landscape_url` → `landscape.jpg` when
  available; missing URLs are not an error.
- Image downloads are content-type tolerant; a response without an image
  content type is treated as a failure for that file.
- Existing files are overwritten atomically so re-running a scrape is
  idempotent.

An item succeeds when `movie.nfo` and at least one image were written. The
post-write recheck decides the movie status independently.

## Scraping Task Lifecycle

### Creation

`POST /api/scraping/tasks`:

```json
{ "movie_ids": ["<uuid>", "..."] }
```

- Dedupe ids, require at least one, cap at 500 per task.
- Unknown movies are rejected with 400.
- One `scraping_task_item` per movie with `status=pending`; the task starts as
  `queued` with `config_snapshot` from the current configuration.
- Non-stored movies are not rejected at creation; the worker marks them
  `skipped` with reason `未存储` so the task detail explains what happened.
- The worker is started if it is not already running (single global worker,
  same start-on-demand pattern as the storage worker).

### Item pipeline (`item_runner.py`)

1. Load the movie. If its normalized storage status is not `stored`, mark the
   item `skipped` (`未存储`).
2. Resolve the media folder: storage `target_folder` derivation first, then
   the scan index by code. If no existing local folder is found, mark the item
   `skipped` (`目标文件夹不存在`). Never create folders.
3. Collect metadata: DB values first; crawl missing fields through
   `metadata_sources` in order. If the DB row already has every required
   field, no network call is made.
4. Render and write `movie.nfo`, then download artwork.
5. Recheck the folder and update `movies.scraping_status` /
   `scraping_folder` / `scraping_checked_at`.
6. Mark the item `success` with `source`, `folder`, and `duration_ms`.
7. Any exception marks the item `failed` with a safe error message; the worker
   continues with the next item.

### Task status transitions

- `queued` → `running` when the worker claims it (`started_at` set).
- `running` → `success` when `success_count > 0` and
  `failed_count + skipped_count == 0`.
- `running` → `partial_failed` when `success_count > 0` and
  `failed_count + skipped_count > 0`.
- `running` → `failed` when `success_count == 0` and
  `failed_count + skipped_count > 0`.
- `running` → `cancelled` when `cancel_requested` was observed; remaining
  pending items become `skipped` with reason `任务已取消`.
- Task counters are updated incrementally and published via realtime events.

### Cancellation and retry

- `POST /api/scraping/tasks/{id}/cancel` sets `cancel_requested = true`. A
  queued task is cancelled immediately; a running task stops between items.
- `POST /api/scraping/tasks/{id}/retry` is allowed for `failed`,
  `partial_failed`, and `cancelled` tasks. It creates a new task from the
  source task's `failed` and `skipped` movies (preconditions may now hold) and
  returns the new task.

### Concurrency

- One global worker thread, one task at a time, oldest queued task first.
- Items are processed serially to respect source-site rate limits; the scrape
  pipeline reuses the existing fetcher throttle and cookie handling.
- A task is marked `running` before the first item and `finished_at` is set
  when it reaches a terminal status.
- Worker start is idempotent and guarded by a module lock; there is no
  automatic retry of failed items.

## API

All endpoints require the standard authenticated user dependency.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/scraping/config` | Extended public config (new fields included) |
| PUT | `/api/scraping/config` | Partial update with validation |
| POST | `/api/scraping/scan` | Synchronous directory scan; returns `ScanSummary` |
| POST | `/api/scraping/tasks` | Create a scraping task from `movie_ids` |
| GET | `/api/scraping/tasks` | Paginated task list (`page`, `page_size`, `status`) |
| GET | `/api/scraping/tasks/{id}` | Task summary + items |
| POST | `/api/scraping/tasks/{id}/cancel` | Request cancellation |
| POST | `/api/scraping/tasks/{id}/retry` | Retry failed/skipped items as a new task |
| POST | `/api/scraping/strm/run` | Existing manual STRM trigger (unchanged) |

- The list/detail response envelope and pagination shape follow the storage
  task endpoints.
- Tasks are per-user: the list is scoped to `created_by == current_user.id`,
  and a task owned by another user is reported as not found, matching the
  storage task behavior.
- Task list items include `id`, `status`, counts, `created_by`, `queued_at`,
  `started_at`, `finished_at`, `error_message`, and `created_at`.
- Detail adds `items` (bounded by the 500-item creation cap) with `movie_id`,
  `movie_code`, `movie_title`, `status`, `source`, `folder`, `duration_ms`,
  `error_message`.
- Movie list serialization adds `scraping_status`, `scraping_folder`, and
  `scraping_checked_at`.

## Realtime Events

New events published through the existing realtime bus:

| Event | Scope | Payload |
| --- | --- | --- |
| `scraping.task.updated` | `scraping_task` | task id, status, counts |
| `scraping.item.updated` | `scraping_task` | task id, item id, status |
| `movie.scraping.updated` | `movie` | movie id, scraping status, checked_at |

- Frontend event types are extended in `frontend/src/realtime/types.ts`.
- The task list refreshes on `scraping.task.updated`; the detail page refreshes
  on `scraping.task.updated` and `scraping.item.updated`; the movie list
  applies scraping updates without a full reload.

## Frontend

### Routing and navigation

- New routes: `/scraping/tasks` (list) and `/scraping/tasks/$id` (detail),
  registered in `frontend/src/routes/index.tsx` with `lazyRouteComponent`.
- `frontend/src/routes/tags.ts`: `刮削任务` and `刮削任务详情` tab titles and
  cache keys.
- Sidebar `刮削` group gains `刮削任务` (`HistoryOutlined`) after `刮削配置`;
  the active-path matcher expands to `/scraping/tasks`.

### Config page

- Adds `刮削目录` (local path) and `媒体库根路径` inputs.
- Adds a `元数据源优先级` card: one row per registry source with a drag handle
  (@dnd-kit), label, and enable switch; enabled sources keep their order and
  are what `metadata_sources` saves. At least one source must stay enabled.
- Adds a `扫描目录` button with a result summary (folders scanned, scraped,
  not scraped, matched movies, unmatched folder count) rendered after a scan.
- Client-side validation: both paths required before saving; a scan requires a
  saved `scrape_root`.

### Task pages

- List: columns for status tag, progress (`success/total`, failed, skipped),
  owner, queued/started/finished times; actions `详情`, `取消` (queued/running),
  `重试` (failed/partial_failed/cancelled); SSE refresh.
- Detail: summary header, status/progress, error message, cancel/retry actions,
  items table (code, title, status tag, source, folder, duration, error), and
  SSE refresh.
- Status/color mapping helpers live in `pages/scraping/tasks/utils/status.ts`,
  mirroring the storage task utilities.

### List page caching and headers

The crawler run records page (`/crawler/runs`), the storage task list
(`/storage/tasks`), and the scraping task list (`/scraping/tasks`) are uncached
lists:

- Add all three paths to `ROUTE_CACHE_EXCLUDE_PATHS` in
  `frontend/src/layout/routeCacheControl.ts`. Excluded routes render outside
  `KeepAlive`, so entering the route remounts the page and TanStack Query
  refetches the list (`staleTime` defaults to 0). Detail routes
  (`/crawler/runs/$id`, `/storage/tasks/$id`, `/scraping/tasks/$id`) are not
  excluded and keep the existing cache behavior.
- Each of the three list pages renders its table inside a card whose header has
  a title and a `刷新` button in the card `extra` slot, following
  `StorageMainTaskTable`:
  - `/crawler/runs`: title `运行记录`, refresh calls the page's `refreshRuns`.
  - `/storage/tasks`: title `任务列表` (already implemented).
  - `/scraping/tasks`: title `刮削任务`, refresh calls the list hook's
    `refresh`.
- The existing tags view still registers tabs for these routes; cache-control
  `refresh` for an excluded route is a no-op because the page has no kept-alive
  instance.
- `useRouteActivationRefresh` may remain in pages that already use it; with
  cache exclusion the page remounts anyway, so it becomes redundant but
  harmless.

### Movie list

- New `刮削状态` column after `存储状态`:
  - not stored → `-`
  - `scraped` → green `已刮削`
  - `not_scraped` → default `未刮削`
  - unknown/`NULL` for a stored movie → `-`
- Row action `刮削` and toolbar `批量刮削` (next to the existing batch buttons),
  both visible in this iteration.
- Both actions create a task via the task API and show a success message with
  the created task id; the task list/detail is reachable from the sidebar.
- `useMovieScraping.ts` owns creation, error handling, and realtime
  `movie.scraping.updated` handling; `useMovieListRealtime` gains the new
  event route.

### API modules and query keys

- `frontend/src/api/scraping/scrapingConfig`: extended types and
  `runScrapingScan()`.
- `frontend/src/api/scraping/scrapingTasks`: list/detail/create/cancel/retry
  wrappers plus query keys.
- `frontend/src/api/queryKeys.ts` / `queryInvalidation.ts` gain scraping task
  keys and movie scraping invalidation.

## Error Handling and Edge Cases

- `scrape_root` missing or not a directory: config save returns 400 for a
  non-empty invalid path; scan returns 400 with a clear message.
- Unmapped cloud folders (not under `media_root`) are treated as unmatched;
  they never write movie status.
- Folder names that yield no code and no `target_folder` match are reported as
  unmatched.
- Duplicate code folders: exact `target_folder` match wins, then the
  lexicographically first path.
- Case-insensitive comparisons for `*.strm`, `movie.nfo`, and image
  extensions.
- Source crawl failure with a complete DB row: scrape proceeds without a
  `metatubeid`.
- Source crawl failure with missing cover: the item fails with a safe message
  (no image can be written).
- Existing `movie.nfo`/images are overwritten atomically; re-scraping is safe.
- Worker crash or backend restart: stale `running` tasks are marked `failed`
  with a restart message (`任务中断，需重试`) during application startup, in a
  startup hook mirroring `cleanup_interrupted_storage_tasks`; their pending
  items are marked `skipped`.
- Scanning is synchronous; a very large tree can be slow. Depth and
  hidden-directory limits bound the walk; a background scan mode is future
  work.

## Verification

Backend:

```bash
python -m pytest backend/tests/test_scraping_config_service.py -v
python -m pytest backend/tests/test_scraping_scan.py -v
python -m pytest backend/tests/test_scraping_tasks_api.py -v
python -m pytest backend/tests/test_scraping_nfo.py -v
python -m pytest backend/tests/test_content_movies_api.py -v
```

New focused tests:

- `test_scraping_config_service.py`: `metadata_sources` JSON round-trip,
  fallbacks, invalid source rejection.
- `test_scraping_scan.py`: scraped rule, code extraction, target-folder
  derivation, unmatched folders, non-stored movies untouched (tmp_path
  fixtures).
- `test_scraping_paths.py`: local/cloud path mapping and code normalization.
- `test_scraping_nfo.py`: field mapping, escaping, art paths, omitted
  metatubeid.
- `test_scraping_tasks_api.py`: creation validation, status transitions,
  cancel, retry, list pagination, per-user scoping, startup cleanup, realtime
  event publication.
- `test_content_movies_api.py`: new serializer fields.

Frontend:

```bash
cd frontend && pnpm build
cd frontend && pnpm test -- src/pages/scraping/tasks src/pages/scraping/config src/pages/content/movies
```

Tests cover: status column rendering, scrape/batch buttons creating tasks,
config page source ordering and scan summary, task list/detail rendering and
actions, realtime refresh, and the uncached list behavior (route exclusion and
card header refresh buttons for crawler runs, storage tasks, and scraping
tasks).

## Risks and Assumptions

- The external STRM service names folders consistently with the storage
  `target_folder` convention (`{target_root}/{storage_location}/{code}`). The
  code-extraction fallback covers deviations.
- `scrape_root` is a local mount of the cloud media root; the backend process
  can read it with its own permissions.
- javdb/javbus crawling depends on existing cookies and proxies; items fail
  individually and can be retried, never blocking the queue.
- The metatube-style nfo is accepted by the media server in use; fields absent
  from the DB are omitted rather than guessed.
- Movies are global, so scanning updates all stored movies regardless of which
  user triggered it; tasks themselves are per-user.

## Future Work

- Conditional button visibility (hide push for stored, hide scrape for
  scraped) and bulk skipping of already-scraped rows.
- `javlibrary` and additional source adapters.
- Multiple scraping directories with per-directory `directory_id` and roots.
- Movie list filtering by scraping status.
- Scheduled scans and background scan progress.
- Scraping status history.
