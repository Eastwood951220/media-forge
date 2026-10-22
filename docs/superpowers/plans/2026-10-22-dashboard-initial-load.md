# Dashboard Initial Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the first dashboard overview wait and avoid rescanning all movies for rankings on every request.

**Architecture:** Keep the existing overview endpoint and statistics. Suppress unused ORM relationship loading in dashboard read paths. Cache only the global movie rankings in Redis for 300 seconds; dynamic counters and status remain live.

**Tech Stack:** Python, FastAPI, SQLAlchemy, PostgreSQL, Redis, pytest.

**Spec:** `docs/superpowers/specs/2026-10-22-dashboard-initial-load-design.md`

## Global Constraints

- Work in the current checkout; do not create a worktree.
- Preserve existing overview fields, ranking rules, and partial-error behavior; add only the ranking calculation timestamp field.
- Cache only rankings for 300 seconds; Redis failures must fall back to database computation.
- Stage only intended files and inspect the staged file list before commits.

## Review Focus

- Latest runs and recent storage tasks with many detail/subtask rows should not cause dashboard reads to load them.
- A cache hit must leave movie totals and storage status live.
- A cache miss must preserve all three ranking groups and excluded tags.
- A cache hit must display the original ranking calculation time, not the new overview request time.
- A malformed or unavailable Redis value must not blank the content section.
- An unavailable Redis queue must not prevent the overview endpoint from returning its database-backed sections.
- Manual refresh must still fetch fresh dynamic metrics while rankings may be five minutes old.

---

### Task 1: Trim unused relationship loads

**Files:**
- Modify: `backend/app/modules/crawler/tasks/runtime_status.py`
- Modify: `backend/app/modules/dashboard/service.py`
- Test: `backend/tests/test_dashboard_overview.py`

**Interfaces:** `build_task_runtime_status_response(db, owner_id)` and `build_dashboard_overview(...)` retain signatures and response models.

- [ ] Add a regression test recording SQL during an overview build with task URLs, run details and storage subtasks, asserting those tables are not queried by the overview.
- [ ] Run the new test and confirm it fails because eager relationship queries occur.
- [ ] Add query-local loading options to omit `CrawlTask.urls` and `CrawlRun.detail_tasks` in the runtime status and dashboard recent-run queries.
- [ ] Run the focused dashboard test and related crawler status tests; confirm they pass.
- [ ] Commit only Task 1 files after inspecting `git diff --cached --name-only`.

### Task 2: Cache movie rankings for five minutes

**Files:**
- Modify: `backend/app/modules/dashboard/router.py`
- Modify: `backend/app/modules/dashboard/schemas.py`
- Modify: `backend/app/modules/dashboard/service.py`
- Test: `backend/tests/test_dashboard_overview.py`

**Interfaces:** `build_dashboard_overview(..., ranking_cache: redis.Redis | None = None)`; the router supplies the existing Redis client. Existing direct callers remain valid.

- [ ] Add tests for cache miss/hit with changed movie counts, 300-second expiry, ranking calculation timestamp, Redis read/write failure or invalid cached JSON, and endpoint degradation when Redis queue reads fail.
- [ ] Run those tests and confirm they fail for missing caching behavior.
- [ ] Cache rankings with their calculation time under a versioned global key; on cache failure, compute rankings from the database and keep dynamic metrics live.
- [ ] Run the focused tests and broader backend suite; confirm results and compare cache miss/hit timings.
- [ ] Commit only Task 2 backend files after inspecting `git diff --cached --name-only`.

### Task 3: Show ranking calculation time

**Files:**
- Modify: `frontend/src/api/dashboard/types.ts`
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/pages/dashboard/components/DashboardContentRankings.tsx`
- Test: `frontend/tests/dashboard.ui.test.tsx`

**Interfaces:** Consume Task 2's `content.rankings_updated_at` ISO datetime or null; pass it to the rankings component without changing the existing `rankings` structure.

- [ ] Add a frontend test for the labeled time in the rankings panel; run to confirm failure.
- [ ] Render the timestamp with the existing local date formatting pattern and run the focused frontend test and build.
- [ ] Commit only Task 3 frontend files plus approved spec and plan after inspecting `git diff --cached --name-only`.
