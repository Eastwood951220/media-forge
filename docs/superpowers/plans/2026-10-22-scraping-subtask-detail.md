# Scraping Subtask Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show real scraping subtask steps and logs in a detail drawer on the task page.

**Architecture:** Add a current-step column and per-item JSONL log helper, expose owner-scoped detail/log endpoints, and instrument the scraper worker at meaningful stages. The existing task page opens an Ant Design drawer and loads logs on demand; SSE appends current-item records and refreshes the item state.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, React 19, TypeScript, Ant Design, TanStack Query, SSE.

**Spec:** `docs/superpowers/specs/2026-10-22-scraping-subtask-detail-design.md`

## Global Constraints

- Work in this checkout; AGENTS.md forbids Git worktrees.
- Preserve existing scraping endpoints and unrelated work.
- Old items have no historical logs; display existing fields and an empty log state.
- Commit each functional change after inspecting staged file names.
- Use an explicit Details button so opening the drawer is keyboard accessible.

## Review Focus

- Another user's item ID: both detail and logs return 404; Task 1 API tests.
- Missing or malformed log file: return an empty or valid subset without a 500; Task 1 log tests.
- Early skip, expected failure, unexpected exception, cancellation, and interruption: each ends with a reason log; Task 2 tests.
- Realtime event for a different item: never appears in the open drawer; Task 3 test.
- Closing and opening another item: old logs must not appear while the new item loads; Task 3 test.

---

### Task 1: Persist and serve scraping item steps and logs

**Files:**
- Modify: `backend/app/models/scraping_task.py`, `backend/app/modules/scraping/tasks/serializers.py`, `backend/app/modules/scraping/tasks/events.py`, `backend/app/modules/scraping/router.py`
- Create: `backend/app/modules/scraping/tasks/logs.py`, `backend/alembic/versions/20261022_0001_add_scraping_item_step.py`
- Test: `backend/tests/test_scraping_task_logs.py`, `backend/tests/test_scraping_tasks_api.py`

**Interfaces:** `write_scraping_item_log(item_id: str, level: str, message: str, *, step: str | None = None, context: dict | None = None) -> dict`; `read_scraping_item_logs(item_id: str) -> list[dict]`; `publish_scraping_item_log_appended(owner_id: str, item_id: str, entry: dict) -> None`. `GET /api/scraping/tasks/items/{item_id}` and `/logs` require ownership and return item / log data.

- [ ] Write tests for log persistence, invalid JSONL lines, owner-scoped detail/log routes, and serialized `step`.
- [ ] Run focused tests and see expected missing-interface failures.
- [ ] Add the model/migration, log helper, event and API handlers; migrate old items with an empty `step`, and initialize new items at `prepare`.
- [ ] Run focused tests and confirm pass.
- [ ] Stage named files, inspect staged list, commit `feat(scraping): persist and expose item progress`.

### Task 2: Record real worker stages and terminal outcomes

**Files:**
- Modify: `backend/app/modules/scraping/tasks/item_runner.py`, `backend/app/modules/scraping/tasks/worker.py`, `backend/app/modules/scraping/tasks/service.py`
- Test: `backend/tests/test_scraping_task_worker.py`, `backend/tests/test_scraping_task_service.py`

**Interfaces:** Task 1's log writer and event publisher. Stage keys: `prepare`, `locate_folder`, `fetch_metadata`, `write_artwork`, `write_nfo`, `refresh_status`.

- [ ] Add tests for stage order on success, early skips and failures, unexpected exception, cancellation, and interruption.
- [ ] Run focused tests and confirm stage/log assertions fail.
- [ ] Emit step transition/item update and append a log after each real stage; log terminal reasons once and preserve existing status behavior.
- [ ] Run worker/service and scraping backend tests.
- [ ] Stage named files, inspect staged list, commit `feat(scraping): record subtask stages and outcomes`.

### Task 3: Add detail drawer, logs, and realtime updates

**Files:**
- Modify: `frontend/src/api/scraping/scrapingTasks/types.ts`, `frontend/src/api/scraping/scrapingTasks/index.ts`, `frontend/src/pages/scraping/tasks/TaskDetailPage.tsx`, `frontend/src/pages/scraping/tasks/__tests__/task-pages.test.tsx`, `frontend/README.md`
- Create: `frontend/src/pages/scraping/tasks/components/ScrapingItemDetailDrawer.tsx`, `frontend/src/pages/scraping/tasks/utils/itemSteps.ts`

**Interfaces:** Task 1 item/log APIs. `ScrapingTaskItem.step?: string`; `ScrapingTaskLog` contains timestamp, level, message, optional step/context.

- [ ] Add UI tests for Details action, fields, step and log rendering, live event filtering, empty and switched-item states.
- [ ] Run focused Vitest and observe missing drawer/API behavior.
- [ ] Add typed API and accessible button/drawer with on-demand fetch, stage timeline, full logs, and item-scoped SSE updates.
- [ ] Run focused Vitest, `pnpm build`, and relevant scraping backend tests.
- [ ] Stage named files, inspect staged list, commit `feat(scraping): show item progress drawer`.
