# Jellyfin Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Jellyfin to existing scraping and movie flows, synchronize `root` watch status, refresh affected libraries, and clean NAS STRM folders in cloud deletion modes.

**Architecture:** Keep Jellyfin HTTP and configuration logic under `backend/app/modules/jellyfin/`. Persist movie watch snapshots for fast server-side filtering, with one persisted sync status and a single APScheduler job configured from scraping settings. Extend existing movie deletion and scraping triggers instead of introducing parallel product flows.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, httpx, APScheduler, React, TanStack Query, Ant Design, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-10-30-jellyfin-library-watch-and-scraped-folder-design.md`

## Global Constraints

- Work in this checkout; never create a Git worktree. Preserve the existing uncommitted scraping image and test changes.
- Jellyfin user is `root`; shared path mapping is `media_root` (`/media` by default) to the existing `scrape_root`.
- Cloud-only and database-and-cloud deletion both remove the entire matching NAS movie folder. Database-only leaves NAS untouched.
- Manual refresh covers all libraries containing STRM files under current `scrape_root`; auto refresh covers changed STRM paths.
- Watch sync is manual or daily/weekly scheduled; automatic library refresh is independently configurable. Homepage stats are excluded.
- Use exact paths for watch matching, never a code-only guess. Never expose the Jellyfin API key to frontend or logs.
- Stage intended files explicitly and inspect `git diff --cached --name-only` before every functional commit.

## Review Focus

- Jellyfin returns duplicate or overlapping media paths: ambiguous movies stay unknown rather than being marked absent; Task 2 test.
- External STRM service accepts a job before files appear: auto refresh waits for observed file changes; Task 3 test.
- One media library fails while another refreshes: return per-library outcomes and retain successes; Task 3 test.
- NAS path escapes the configured root through symlinks or parent traversal: reject before deletion; Task 4 test.
- Cloud deletion succeeds but NAS deletion fails: retain database record and expose partial result for retry; Task 4 test.

---

### Task 1: Jellyfin configuration and read-only API

**Files:**
- Create: `backend/app/modules/jellyfin/client.py`, `backend/app/modules/jellyfin/router.py`
- Modify: `backend/app/modules/scraping/schemas.py`, `backend/app/modules/scraping/config.py`, `backend/app/main.py`
- Test: `backend/tests/test_jellyfin_client.py`, `backend/tests/test_jellyfin_config_api.py`

**Interfaces:**
- `JellyfinClient(base_url: str, api_key: str, transport: httpx.BaseTransport | None = None)` with `get_virtual_folders() -> list[dict]`, `get_users() -> list[dict]`, `get_items(user_id: str, start: int, limit: int) -> dict`, `refresh_item(item_id: str) -> None`.
- `GET /api/jellyfin/libraries`, `POST /api/jellyfin/test`; configuration fields `jellyfin_base_url`, `jellyfin_api_key`, `jellyfin_auto_refresh_enabled`, `jellyfin_watch_sync_enabled`, `jellyfin_watch_sync_schedule_type`, `jellyfin_watch_sync_time_of_day`, `jellyfin_watch_sync_weekdays` on existing scraping config API.

- [ ] Add failing tests for key masking/retention, invalid URL, root user lookup, authenticated virtual folders and API failures.
- [ ] Run `python -m pytest backend/tests/test_jellyfin_client.py backend/tests/test_jellyfin_config_api.py -q` and confirm failure.
- [ ] Implement configuration serialization and narrow HTTP client/router; protect all routes with `CurrentUser`.
- [ ] Run the focused tests and confirm pass.
- [ ] Stage only Task 1 files, inspect staged names, commit `feat: configure Jellyfin connection`.

### Task 2: Persistent watch snapshots and synchronization

**Files:**
- Create: `backend/alembic/versions/20261030_0001_add_jellyfin_watch_state.py`, `backend/app/models/jellyfin_sync.py`, `backend/app/modules/jellyfin/sync.py`, `backend/app/modules/jellyfin/scheduler.py`
- Modify: `shared/database/models/content.py`, `backend/app/models/__init__.py`, `backend/app/modules/jellyfin/router.py`, `backend/app/main.py`, `backend/app/modules/content/movies/router.py`, `backend/app/modules/content/movies/filters.py`, `backend/app/modules/content/movies/sql_builder.py`, `backend/app/modules/content/movies/serializers.py`
- Test: `backend/tests/test_jellyfin_sync.py`, `backend/tests/test_jellyfin_schedule.py`, `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Movie fields `jellyfin_item_id: str | None`, `jellyfin_watch_status: str | None`, `jellyfin_playback_position_ticks: int | None`.
- `sync_jellyfin_watch_state(db: Session, client: JellyfinClient) -> JellyfinSyncResult`; `POST /api/jellyfin/watch/sync`, `GET /api/jellyfin/watch/status`; `jellyfin_watch_status` movie list query parameter.
- Status values `played`, `unplayed`, `in_progress`, `not_in_library`; null means unsynced or ambiguous. Global sync state stores last success, last attempt, running/failure and error summary.

- [ ] Add failing tests for four states, path matching, pagination, duplicates, failed sync preserving old snapshot, config invalidation, list filtering, schedule daily/weekly and restart restoration.
- [ ] Run focused backend tests and confirm failure.
- [ ] Implement migration, sync service, status API, filter/serializer, and APScheduler job with no overlapping runs.
- [ ] Run focused backend tests and confirm pass.
- [ ] Stage only Task 2 files, inspect staged names, commit `feat: sync Jellyfin watch status`.

### Task 3: Targeted library refresh

**Files:**
- Create: `backend/app/modules/jellyfin/refresh.py`
- Modify: `backend/app/modules/jellyfin/router.py`, `backend/app/modules/scraping/scan.py`, `backend/app/modules/scraping/trigger.py`, `backend/app/modules/scraping/router.py`
- Test: `backend/tests/test_jellyfin_refresh.py`, `backend/tests/test_scraping_strm_trigger.py`, `backend/tests/test_scraping_api.py`

**Interfaces:**
- `refresh_libraries_for_paths(config: Mapping[str, Any], paths: Iterable[Path]) -> list[LibraryRefreshResult]` uses virtual folder `Locations`/`ItemId` and deduplicates matched IDs.
- `POST /api/jellyfin/libraries/refresh` scans existing STRM paths in `scrape_root`; refresh result reports accepted and failed libraries separately.

- [ ] Add failing tests for shared root mapping, overlapping libraries, no match, multiple results, and asynchronous STRM generation completion.
- [ ] Run focused tests and confirm failure.
- [ ] Implement library selection, manual endpoint and observed-file-change auto trigger after STRM generation; do not claim refresh completed merely because Jellyfin accepted the request.
- [ ] Run focused tests and confirm pass.
- [ ] Stage only Task 3 files, inspect staged names, commit `feat: refresh affected Jellyfin libraries`.

### Task 4: NAS movie folder cleanup in existing deletion modes

**Files:**
- Create: `backend/app/modules/content/movies/nas_delete.py`
- Modify: `backend/app/modules/content/movies/delete_api.py`, `backend/app/modules/content/movies/delete_service.py`, `backend/app/modules/content/movies/schemas.py`
- Test: `backend/tests/test_movie_delete_service.py`, `backend/tests/test_content_movies_api.py`

**Interfaces:**
- `resolve_nas_movie_folder(movie: Movie, config: Mapping[str, Any]) -> Path | None` and `delete_nas_movie_folders(movies: list[Movie], config: Mapping[str, Any]) -> NasDeleteResult`.
- Delete response adds `nas_deleted_folders`, `nas_missing_folders`, `nas_failed_folders`; cloud-only keeps database record, database-and-cloud deletes it after successful external cleanup.

- [ ] Add failing tests for the exact `/media/愛那あい/CJOD-496-C` mapping, whole folder removal, each delete mode, symlink/escape rejection, missing directories, partial failure and retry.
- [ ] Run focused tests and confirm failure.
- [ ] Implement preflight, guarded NAS deletion, partial result, status updates and targeted post-delete refresh using Task 3.
- [ ] Run focused tests and confirm pass.
- [ ] Stage only Task 4 files, inspect staged names, commit `feat: remove NAS STRM folders with cloud movies`.

### Task 5: Scraping configuration Jellyfin UI

**Files:**
- Create: `frontend/src/api/jellyfin/index.ts`, `frontend/src/pages/scraping/config/components/JellyfinConfigSection.tsx`
- Modify: `frontend/src/api/scraping/scrapingConfig/types.ts`, `frontend/src/pages/scraping/config/ScrapingConfigPage.tsx`, `frontend/README.md`
- Test: `frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx`, `frontend/src/pages/scraping/config/__tests__/JellyfinConfigSection.test.tsx`

**Interfaces:**
- Jellyfin API wrapper exposes connection test, libraries, manual refresh, manual watch sync and sync status. `JellyfinConfigSection` consumes existing form configuration values and callbacks.

- [ ] Add failing UI tests for key masking, libraries and mapping, auto refresh switch, manual refresh, root sync, daily/weekly schedule and result feedback.
- [ ] Run focused Vitest and confirm failure.
- [ ] Implement the Jellyfin section within existing scraping configuration page, following current Ant Design form conventions.
- [ ] Run focused tests and `pnpm build` from `frontend/` and confirm pass.
- [ ] Stage only Task 5 files, inspect staged names, commit `feat: manage Jellyfin in scraping settings`.

### Task 6: Movie list watch status and deletion feedback

**Files:**
- Modify: `frontend/src/api/movie/types.ts`, `frontend/src/api/movie/index.ts`, `frontend/src/pages/content/movies/MovieListPage.tsx`, `frontend/src/pages/content/movies/components/MovieTable.tsx`, `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`, `frontend/src/pages/content/movies/constants/movieFilterFields.ts`, `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`, `frontend/src/pages/content/movies/hooks/useMovieListActions.tsx`, `frontend/src/pages/content/movies/utils/movieFilter.ts`, `frontend/README.md`
- Test: `frontend/src/pages/content/movies/__tests__/movie-table-actions.test.tsx`, `frontend/src/pages/content/movies/__tests__/movie-filters-config.test.tsx`, `frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx`

**Interfaces:**
- Movie and query types add the three agreed Jellyfin fields and `jellyfin_watch_status` filter; delete result adds NAS folder outcomes.

- [ ] Add failing UI tests for four statuses, unknown status, filter query, latest sync warning, selected-row bulk delete and NAS deletion confirmation/results.
- [ ] Run focused Vitest and confirm failure.
- [ ] Implement watch column/filter, manual sync action, stale state hint and deletion feedback; preserve existing page-limited bulk selection.
- [ ] Run focused tests and `pnpm build` and confirm pass.
- [ ] Stage only Task 6 files, inspect staged names, commit `feat: show Jellyfin watch state in movie list`.

### Final verification

- [ ] Run affected backend test files, `python -m pytest scraper/tests -q` if scraping integration changed shared behavior, affected frontend tests and `pnpm build`.
- [ ] Inspect `git status --short` and `git diff` to confirm only the original three unrelated dirty files remain.
- [ ] Review API key redaction, root/path safety, schedule restoration, and partial deletion result against the spec.
