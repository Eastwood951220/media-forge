# FANZA scraping and distinct artwork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FANZA as an ordered metadata source and ensure scraped image slots contain distinct scenes when available.

**Architecture:** A FANZA adapter resolves an exact movie code to digital GraphQL or DVD detail data and maps it into `SourceMetadata`. The item runner fetches source images even for populated movie rows; the artwork writer downloads, compares, and saves distinct images. The existing source priority UI and nfo writer expose the resulting choice and files.

**Tech Stack:** Python 3.12, FastAPI, httpx, pytest, Pillow for image comparison; React 19, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-22-fanza-scraping-artwork-design.md`

## Global Constraints

- Work in this checkout on an ordinary Git branch; never create a worktree.
- Preserve unrelated files, stage explicit paths, inspect staged file names before every commit.
- Keep existing JavDB/JavBus defaults for existing and new configurations.
- Do not overwrite populated movie database fields or require the Go SDK at runtime.
- A title with fewer available scenes may have fewer than three image files.

## Review Focus

- Search result code looks similar but is not equal: reject it and try the next source (Task 1).
- FANZA response is blocked, malformed, or empty: fail over without a partial metadata result (Task 1).
- Preview image is resized cover: skip it through decoded-image comparison (Task 2).
- Complete movie row lacks usable backdrop: still query sources for artwork (Task 3).
- Artwork download partially fails: preserve good existing files and emit only real nfo paths (Task 3).

---

### Task 1: FANZA source adapter

**Files:**
- Create: `backend/app/modules/scraping/fanza.py`
- Modify: `backend/app/modules/scraping/sources.py`
- Test: `backend/tests/test_scraping_fanza.py`

**Interfaces:**
- Produces: `FanzaAdapter.fetch_by_code(code: str) -> SourceMetadata | None`; register key `fanza`, label `FANZA`.
- Consumes: `SourceMetadata`, `normalize_code`, source priority contract.

- [ ] Add fixtures and tests for exact code resolution, digital field mapping, DVD fallback, lookalike rejection, and blocked or malformed responses.
- [ ] Run `python -m pytest backend/tests/test_scraping_fanza.py -q`; expect new tests to fail.
- [ ] Implement the adapter with bounded HTTP requests, exact normalized product-number validation, digital GraphQL mapping, and DVD HTML mapping. Use the local Go provider as the reference for URL and field behavior.
- [ ] Run `python -m pytest backend/tests/test_scraping_fanza.py backend/tests/test_scraping_sources.py -q`; expect pass.
- [ ] Commit only Task 1 files as `feat(scraping): add FANZA metadata source`.

### Task 2: Distinct image selection

**Files:**
- Modify: `backend/app/modules/scraping/images.py`, `backend/requirements.txt`
- Test: `backend/tests/test_scraping_images.py`

**Interfaces:**
- Produces: `write_artwork(folder, *, cover_url, backdrop_urls, landscape_urls, referer, transport) -> ArtworkResult` where the result reports existing written slots.
- Consumes: URL candidates from Task 1 and the existing image download constraints.

- [ ] Add tests with actual JPEG fixtures for resized duplicates, unique previews, partial failures, and reruns with existing files.
- [ ] Run `python -m pytest backend/tests/test_scraping_images.py -q`; expect new tests to fail.
- [ ] Implement decoded image similarity (Pillow), bounded downloads, atomic slot replacement, and proven-duplicate cleanup; add Pillow as a direct dependency.
- [ ] Run `python -m pytest backend/tests/test_scraping_images.py -q`; expect pass.
- [ ] Commit only Task 2 files as `fix(scraping): keep artwork scenes distinct`.

### Task 3: Item runner, nfo, and source control

**Files:**
- Modify: `backend/app/modules/scraping/tasks/item_runner.py`, `backend/app/modules/scraping/nfo.py`, `backend/app/modules/scraping/schemas.py`, `frontend/src/pages/scraping/config/components/SourcePriorityList.tsx`, `frontend/src/pages/scraping/config/ScrapingConfigPage.tsx`, `frontend/README.md`
- Test: `backend/tests/test_scraping_task_worker.py`, `backend/tests/test_scraping_nfo.py`, `frontend/src/pages/scraping/config/__tests__/ScrapingConfigPage.test.tsx`

**Interfaces:**
- Consumes: Task 1 registered source and Task 2 artwork result.
- Produces: a scrape task that fetches artwork metadata independently of missing DB fields, and nfo art entries only for saved files.

- [ ] Add tests for populated-row artwork fetch, source fallback, nfo with missing backdrop, and FANZA priority UI.
- [ ] Run the focused pytest and Vitest files; expect new tests to fail.
- [ ] Update task orchestration, nfo art flags, ordered source UI, and README.
- [ ] Run focused pytest, Vitest and `pnpm build`; expect pass.
- [ ] Commit only Task 3 files as `feat(scraping): integrate FANZA and artwork results`.

### Task 4: Integration verification

**Files:**
- Test: affected backend and frontend test suites

**Interfaces:**
- Consumes: Tasks 1–3; produces verification evidence.

- [ ] Run all `backend/tests/test_scraping_*.py` and focused frontend config tests.
- [ ] Run `pnpm build` and `git diff --check`; record any baseline-limited checks separately.
- [ ] Review changed files against the spec and test one real FANZA title if reachable from this host.
