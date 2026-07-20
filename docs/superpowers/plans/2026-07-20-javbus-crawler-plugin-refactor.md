# JavBus Crawler Plugin Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JavBus list/detail crawling with Ajax magnet retrieval while preserving JavDB behavior and supporting mixed-source crawler tasks.

**Architecture:** Define a common site-plugin contract for list collection, detail execution, and optional name extraction. Register JavDB and JavBus implementations by normalized source, then route each URL and detail task through that registry. Keep scheduling, persistence, retries, incremental checks, and magnet ranking in the existing runtime and persistence layers.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Scrapling, BeautifulSoup-compatible Scrapling selectors, pytest, React 19, TypeScript 6, Ant Design 6, Vitest.

## Global Constraints

- `javdb.com` and its subdomains resolve to source `javdb`; `javbus.com` and `www.javbus.com` resolve to source `javbus`.
- Unknown hosts are rejected during task URL creation with HTTP 400.
- JavDB keeps its existing final URL parameters, filters, sorting, incremental behavior, and `MAX_LIST_PAGES` limit.
- JavBus final URLs do not receive JavDB-only parameters and JavBus pagination follows `a#next` until exhaustion; `MAX_LIST_PAGES` is never read by JavBus collection.
- One crawler task may contain both JavDB and JavBus URL entries.
- JavBus Ajax parsing persists every magnet; best-magnet selection remains `auto_select_best_magnet` in `backend/app/modules/content/movies/magnet_persistence.py`.
- Missing JavDB-only fields are allowed for JavBus items when the normalized movie item remains valid.
- Do not add dependencies; use existing fetcher, parser, pipeline, and persistence APIs.
- Each task ends with focused tests passing and its own commit.

## Code Quality Boundaries

- `scraper/spiders/javbus/javbus_parser.py` is a pure parsing module: it accepts a response/document and returns normalized values; it must not import `ScraplingFetcher`, SQLAlchemy, runtime callbacks, or backend modules.
- `scraper/spiders/javbus/javbus_spider.py` owns only JavBus request sequencing, callback invocation, and mapping parser output into the shared crawler item shape; it must not write to the database or implement magnet ranking.
- `scraper/spiders/javdb/javdb_spider.py` and `scraper/spiders/javbus/javbus_spider.py` depend on `SiteSpiderProtocol`; the threaded runtime depends on the protocol and registry, never on site-specific parser classes or CSS selectors.
- `scraper/spiders/registry.py` is the composition root for source-to-plugin construction. It must not contain HTML parsing, pagination, persistence, or runtime state transitions.
- `scraper/tasks/task_utils.py` owns URL/source normalization only. It must not import spider implementations.
- `backend/app/modules/crawler/runtime/threaded.py` owns scheduling and state transitions only. It must not branch on JavBus paths, parse HTML, build Ajax URLs, or rank magnets.
- `backend/app/modules/content/movies/magnet_persistence.py` remains site-neutral. JavBus code supplies all magnets through `magnets`; it must not call `auto_select_best_magnet` directly.
- Shared callback signatures and normalized item keys must be defined once in the protocol or shared schema; JavBus must not copy private JavDB helper implementations.
- Tests for runtime dispatch use protocol-conforming fakes, while parser tests use inline response fixtures. This keeps each layer independently replaceable.

## File Map

Create these files:

- `scraper/spiders/site_plugin.py`: shared site-plugin protocol and callback type aliases.
- `scraper/spiders/registry.py`: source-to-plugin registry and plugin lookup helpers.
- `scraper/spiders/javbus/__init__.py`: JavBus package marker.
- `scraper/spiders/javbus/javbus_parser.py`: pure JavBus list, detail, script metadata, and Ajax magnet parsers.
- `scraper/spiders/javbus/javbus_spider.py`: JavBus site-plugin implementation using the existing fetcher and callbacks.
- `scraper/tests/test_task_utils.py`: source and final URL utility coverage.
- `scraper/tests/test_javbus_parser.py`: parser fixtures expressed as inline HTML and parser assertions.
- `scraper/tests/test_javbus_spider.py`: fetcher and pagination behavior.

Modify these files:

- `scraper/tasks/task_utils.py`: strict host-based source detection and source-aware final URL construction.
- `scraper/tasks/task_schema.py`: carry source in detail task metadata if required by the plugin contract.
- `scraper/spiders/javdb/javdb_spider.py`: implement the common plugin contract without changing JavDB behavior.
- `backend/app/repositories/crawl_task.py`: reject unknown sources and persist normalized source/final URL values.
- `backend/app/modules/crawler/runtime/task_adapter.py`: preserve source and normalized URL data in scraper task entries.
- `backend/app/modules/crawler/runtime/details.py`: include source in detail task info passed to detail execution.
- `backend/app/modules/crawler/runtime/detail_queue.py`: persist/reload source metadata if the current detail payload has no source field.
- `backend/app/modules/crawler/runtime/threaded.py`: resolve plugins per URL and per detail task; remove the single-JavDB assumption.
- `backend/app/modules/crawler/runtime/engine.py`: route legacy engine execution through the registry while preserving its public behavior.
- `backend/app/modules/crawler/tasks/name_extractor.py`: use source-aware plugin name extraction.
- `scraper/config/sites.py`: add JavBus base URL/headers without changing JavDB defaults.
- `frontend/src/pages/crawler/tasks/taskUrlUtils.ts`: detect source, classify JavBus detail/list URLs, and make final URL previews source-aware.
- `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx`: hide JavDB-only controls for JavBus and show the source in URL classification.
- `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`: use the source-aware preview in the compact URL table.
- `frontend/tests/task-url-utils.test.ts`: source, JavBus URL, and preview tests.
- `backend/tests/test_crawl_tasks_api.py`: unknown-source rejection and mixed-source creation tests.
- `backend/tests/test_crawler_threaded_runtime.py`: per-source list/detail dispatch and failure isolation tests.
- `backend/tests/test_crawler_runtime_adapters.py`: registry compatibility for the legacy engine.
- `backend/tests/test_crawler_source_task_names.py`: source propagation and name extraction coverage where applicable.

## Task 1: Make URL Source Detection Strict and Source-Aware

**Files:**
- Modify: `scraper/tasks/task_utils.py`
- Modify: `scraper/tasks/task_schema.py` only if the detail metadata type needs a source field
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/modules/crawler/runtime/task_adapter.py`
- Create: `scraper/tests/test_task_utils.py`
- Test: `backend/tests/test_crawl_tasks_api.py`

**Interfaces:**
- Produces `determine_source(url: str) -> Literal["javdb", "javbus", "unknown"]`.
- Produces `build_final_url(..., source: str | None = None) -> str`; JavBus returns the normalized original URL without JavDB query parameters.
- Keeps `CrawlTaskUrlEntry.source` and `final_url` populated for new and legacy task payloads.

- [ ] **Step 1: Write failing source and URL tests**

Add tests with these exact expectations:

```python
def test_determine_source_uses_hostname_not_substring() -> None:
    assert determine_source("https://javdb.com/search?q=abc") == "javdb"
    assert determine_source("https://www.javdb.com/actors/a") == "javdb"
    assert determine_source("https://javbus.com/ABCD-123") == "javbus"
    assert determine_source("https://www.javbus.com/page/1") == "javbus"
    assert determine_source("https://example.com/javdb.com") == "unknown"


def test_build_final_url_does_not_add_javdb_params_to_javbus() -> None:
    result = build_final_url(
        "https://www.javbus.com/page/1?foo=bar",
        "detail",
        has_magnet=True,
        has_chinese_sub=True,
        sort_type=5,
        source="javbus",
    )
    assert result == "https://www.javbus.com/page/1?foo=bar"


def test_build_final_url_preserves_existing_javdb_behavior() -> None:
    result = build_final_url("https://javdb.com/search?q=abc", "search", source="javdb")
    assert "page=1" in result
    assert "sb=0" in result
```

Run: `source .venv/bin/activate && pytest scraper/tests/test_task_utils.py -q`  
Expected: FAIL because JavBus is currently classified as unknown and receives JavDB parameters.

- [ ] **Step 2: Implement host parsing and source-aware final URLs**

Use `urllib.parse.urlparse`, lowercase `hostname`, and require `http` or `https`. Match `hostname == "javdb.com" or hostname.endswith(".javdb.com")`; match `hostname == "javbus.com" or hostname == "www.javbus.com"`. Return the original URL after `ensure_string` for JavBus so its existing query string is retained unchanged. Keep the current JavDB parameter builder as the JavDB branch.

In `CrawlTaskRepository.build_url_values`, raise `ValueError("不支持的 URL 来源")` when `determine_source` returns `unknown`; map that error to the existing task API's HTTP 400 validation response. Preserve `entry.final_url` only after validating the source. Ensure `to_scraper_task` continues passing `source` and `final_url` into every `CrawlTaskUrlEntry`.

- [ ] **Step 3: Run the focused tests**

Run: `source .venv/bin/activate && pytest scraper/tests/test_task_utils.py backend/tests/test_crawl_tasks_api.py -q`  
Expected: PASS, including existing JavDB task creation tests.

- [ ] **Step 4: Commit**

```bash
git add scraper/tasks/task_utils.py scraper/tasks/task_schema.py backend/app/repositories/crawl_task.py backend/app/modules/crawler/runtime/task_adapter.py scraper/tests/test_task_utils.py backend/tests/test_crawl_tasks_api.py
git commit -m "feat: detect javbus task sources"
```

## Task 2: Add Frontend JavBus Recognition and Source-Specific Controls

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/taskUrlUtils.ts`
- Modify: `frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/tests/task-url-utils.test.ts`

**Interfaces:**
- Produces `detectUrlSource(url: string): 'javdb' | 'javbus' | null`.
- Extends `detectUrlType` to return a valid URL type for JavBus list/detail URLs without making JavBus-specific filter controls appear.
- Produces `buildFinalUrlPreview(baseUrl, urlType, hasMagnet, hasSub, sortType, source?)` with JavBus preview equal to the normalized original URL.

- [ ] **Step 1: Write failing frontend tests**

Add assertions:

```ts
expect(detectUrlSource('https://javdb.com/actors/abc')).toBe('javdb')
expect(detectUrlSource('https://javbus.com/page/1')).toBe('javbus')
expect(detectUrlSource('https://www.javbus.com/ABCD-123')).toBe('javbus')
expect(detectUrlSource('https://example.com/javbus.com')).toBeNull()
expect(buildFinalUrlPreview('https://javbus.com/page/1?foo=bar', 'detail', true, true, 5, 'javbus')).toBe('https://javbus.com/page/1?foo=bar')
```

Run: `cd frontend && npm test -- --run tests/task-url-utils.test.ts`  
Expected: FAIL because source detection and the source argument do not exist.

- [ ] **Step 2: Implement source-aware helpers and UI branching**

Add a `UrlSource` type and hostname-based `detectUrlSource`. Keep `detectUrlType` for JavDB path types; return a `detail` type for JavBus URLs that do not match a JavDB collection path, and recognize `/page/` list URLs as `detail` only for preview purposes. Pass the detected source into `buildFinalUrlPreview`.

In `UrlEntryCard.tsx` and the compact table in `TaskFormPage.tsx`, derive source from the URL. Render `has_magnet`, `has_chinese_sub`, and sort controls only when source is `javdb` or source is not yet detected. For JavBus, keep the URL type/name extraction flow available, but do not show JavDB filter/sort controls or append their parameters to the preview. Update the URL input hint to mention both supported hosts.

- [ ] **Step 3: Run frontend tests and build**

Run: `cd frontend && npm test -- --run tests/task-url-utils.test.ts && npm run build`  
Expected: PASS and a successful production build.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/crawler/tasks/taskUrlUtils.ts frontend/src/pages/crawler/tasks/components/UrlEntryCard.tsx frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/tests/task-url-utils.test.ts
git commit -m "feat: support javbus URLs in crawler form"
```

## Task 3: Implement Pure JavBus Parsers

**Files:**
- Create: `scraper/spiders/javbus/__init__.py`
- Create: `scraper/spiders/javbus/javbus_parser.py`
- Create: `scraper/tests/test_javbus_parser.py`

**Interfaces:**
- Produces `parse_list_page(page) -> tuple[list[dict[str, Any]], str | None]`.
- Produces `parse_detail_page(page, source_url: str) -> dict[str, Any]`.
- Produces `parse_magnet_ajax(page) -> list[dict[str, Any]]`.
- Produces `extract_ajax_params(page) -> dict[str, str]` containing `gid`, `uc`, and `img` when present.
- Parser output contains only plain Python values; it never returns fetcher objects, ORM models, callbacks, or site-plugin instances.

- [ ] **Step 1: Write failing parser tests with inline HTML fixtures**

Cover one list page with two `div.item a.movie-box` entries and an `a#next`; assert absolute detail URLs, title, and code. Cover one detail page with the Chinese basic-info labels and script values. Cover Ajax HTML with two magnet rows and assert both magnet URLs are returned, including size, date, tags, and `has_chinese_sub`.

The magnet assertion must be explicit:

```python
assert [item["magnet"] for item in magnets] == [
    "magnet:?xt=urn:btih:FIRST",
    "magnet:?xt=urn:btih:SECOND",
]
assert magnets[1]["has_chinese_sub"] is True
```

Run: `source .venv/bin/activate && pytest scraper/tests/test_javbus_parser.py -q`  
Expected: FAIL because the JavBus parser module does not exist.

- [ ] **Step 2: Implement list parsing**

Select `div.item a.movie-box`, read `href`, nested `img[title]`, and nested `date` text, and resolve links against `source_url` with `urljoin`. Return the next link from `a#next[href]` as an absolute URL; return `None` when absent.

- [ ] **Step 3: Implement detail and Ajax metadata parsing**

Map the labels `識別碼`, `發行日期`, `長度`, `導演`, `發行商`, `系列`, `類別`, and `演員` to `code`, `release_date`, `duration`, `director`, `maker`, `series`, `tags`, and `actors`. Read title and cover from `.screencap img[title]` / `src`. Scan inline scripts for `gid`, `uc`, and `img` values using the exact reference spider conventions, and leave missing values absent rather than raising during basic field parsing.

Parse each Ajax table row's magnet anchor, size/file text, date, and `.btn` tags. Set `has_chinese_sub` when a tag contains `中字` or `字幕`. Do not rank or discard rows in this module.

- [ ] **Step 4: Run parser tests**

Run: `source .venv/bin/activate && pytest scraper/tests/test_javbus_parser.py scraper/tests/test_javdb_parser_detail_title.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/spiders/javbus/__init__.py scraper/spiders/javbus/javbus_parser.py scraper/tests/test_javbus_parser.py
git commit -m "feat: parse javbus details and magnets"
```

## Task 4: Add JavBus Site Plugin and Common Registry

**Files:**
- Create: `scraper/spiders/site_plugin.py`
- Create: `scraper/spiders/registry.py`
- Create: `scraper/spiders/javbus/javbus_spider.py`
- Modify: `scraper/spiders/javdb/javdb_spider.py`
- Modify: `scraper/config/sites.py`
- Create: `scraper/tests/test_javbus_spider.py`
- Modify: `scraper/tests/test_javdb_spider_dedupe_callbacks.py` only where the common protocol changes constructor or return typing

**Interfaces:**
- `SiteSpiderProtocol.collect_detail_tasks_for_url(...) -> list[dict[str, Any]]`.
- `SiteSpiderProtocol.run_single_detail_task(detail_info: dict[str, Any], *, task_name: str, on_detail_completed, on_detail_failed, stop_check, log_callback, on_detail_check_callback, on_item_already_exists) -> dict[str, Any]`.
- `SiteSpiderProtocol.extract_url_name(url: str, url_type: str) -> str | None`.
- `get_site_spider(source: str, *, fetcher: ScraplingFetcher) -> SiteSpiderProtocol`.
- The protocol is the only interface imported by `backend/app/modules/crawler/runtime/threaded.py`; runtime code cannot import `JavbusSpider`, `JavbusParser`, or site selectors.

- [ ] **Step 1: Write failing spider and registry tests**

Use a fake fetcher that returns inline list/detail/Ajax responses. Assert that `JavbusSpider.collect_detail_tasks_for_url` follows the first page's `a#next`, requests the second page, returns detail tasks from both pages, and never reads `MAX_LIST_PAGES`. Assert a detail task causes one detail request and one Ajax request whose URL contains `gid`, `uc`, and `img`; assert the returned item contains every parsed magnet.

Also assert:

```python
assert get_site_spider("javdb", fetcher=fake_fetcher).__class__.__name__ == "JavdbSpider"
assert get_site_spider("javbus", fetcher=fake_fetcher).__class__.__name__ == "JavbusSpider"
```

Run: `source .venv/bin/activate && pytest scraper/tests/test_javbus_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py -q`  
Expected: FAIL because the protocol, registry, and JavBus spider do not exist.

- [ ] **Step 2: Define the protocol and registry**

Use `typing.Protocol` with keyword-only callback parameters matching the current `JavdbSpider` methods. Keep the protocol in the scraper package so both scraper implementations and backend runtime can depend on it without a backend-to-site implementation dependency. Register `javdb` and `javbus` in one function that constructs a new plugin with the supplied fetcher. Raise `ValueError("不支持的爬虫来源: {source}")` for unknown sources so runtime errors are explicit. The registry may import concrete plugins, but concrete plugins must not import the registry.

- [ ] **Step 3: Implement JavbusSpider list collection**

Construct the first URL from `url_entry.final_url or url_entry.url`. If the URL is a JavBus detail URL, return one detail task without list pagination. Otherwise fetch the current page, pass the response to `javbus_parser.parse_list_page`, apply the existing `crawl_mode`, `incremental_threshold`, `db_check_callback`, `on_item_already_exists`, and `stop_check` callbacks, then follow the parser's next URL until it is absent or a stop condition occurs. Never read `MAX_LIST_PAGES`. Keep URL classification in a small private method on the plugin; do not duplicate CSS selectors or pagination logic in the runtime.

- [ ] **Step 4: Implement JavbusSpider detail execution**

Fetch the detail URL, pass the response to `javbus_parser.parse_detail_page` and `extract_ajax_params`, construct the Ajax URL in one private JavBus helper, request it, pass the response to `parse_magnet_ajax`, and return a normalized item with `source`, `source_url`, `source_name`, `code`, field mappings, `cover_url`, and `magnets`. Call existing callbacks for completion, failure, existing-code checks, and skipped items using the same status vocabulary as JavDB. If Ajax parameters are missing, call `on_detail_failed` with a message containing `gid`, `uc`, and `img`. The plugin must not call the database or `auto_select_best_magnet`.

- [ ] **Step 5: Adapt JavdbSpider to the protocol without behavior changes**

Keep its current pagination loop and `MAX_LIST_PAGES` read. Add `extract_url_name` to the shared contract by delegating to the existing name parsing behavior. Change only shared typing/exports needed for registry dispatch. Existing JavDB tests must continue to exercise the same callbacks and result shapes.

- [ ] **Step 6: Add site configuration and run plugin tests**

Add `JAVBUS_SITE` with `name`, `base_url`, `cookie_file`, and the same browser headers shape as JavDB. Run: `source .venv/bin/activate && pytest scraper/tests/test_javbus_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py -q`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scraper/spiders/site_plugin.py scraper/spiders/registry.py scraper/spiders/javbus scraper/spiders/javdb/javdb_spider.py scraper/config/sites.py scraper/tests/test_javbus_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py
git commit -m "feat: add javbus crawler site plugin"
```

## Task 5: Route Threaded and Legacy Runtime Execution by Source

**Files:**
- Modify: `backend/app/modules/crawler/runtime/threaded.py`
- Modify: `backend/app/modules/crawler/runtime/details.py`
- Modify: `backend/app/modules/crawler/runtime/detail_queue.py`
- Modify: `backend/app/modules/crawler/runtime/engine.py`
- Modify: `backend/tests/test_crawler_threaded_runtime.py`
- Modify: `backend/tests/test_crawler_threaded_url_completion_refresh.py`
- Modify: `backend/tests/test_crawler_runtime_adapters.py`

**Interfaces:**
- `build_spider(source: str = "javdb") -> SiteSpiderProtocol` becomes source-aware or is replaced by `build_site_spider(source)`.
- `detail_row_to_task_info(detail) -> dict[str, Any]` includes `"_task_source"`.
- Threaded list collection resolves `get_site_spider(url_entry.source, fetcher=...)` independently for each URL.
- Runtime callbacks remain backend-owned and are passed into the protocol; site plugins cannot import `Session`, `CrawlRun`, `CrawlTask`, or persistence functions.

- [ ] **Step 1: Write failing mixed-source runtime tests**

Create fake JavDB and JavBus plugins and patch the registry. Feed `_run_list_phase` two URL rows with different sources. Assert each fake receives only its matching URL and both sets of detail tasks are persisted. Add a JavBus plugin fake that raises after one URL and assert the JavDB URL still completes. Add a detail-phase assertion that `_task_source == "javbus"` selects the JavBus fake.

Run: `source .venv/bin/activate && cd backend && pytest tests/test_crawler_threaded_runtime.py tests/test_crawler_threaded_url_completion_refresh.py -q`  
Expected: FAIL because `threaded.py` currently builds one JavDB spider and detail rows omit source.

- [ ] **Step 2: Preserve source in detail task rows**

Extend the detail task payload written by `upsert_detail_task` with `_task_source: url_entry.source`. Include that value in `detail_row_to_task_info`; when reading legacy rows with no source, derive JavDB only when `detail.source_url` has a JavDB host and otherwise fail the detail task as unsupported. Keep database columns unchanged if the payload JSON already stores arbitrary task metadata; add a migration only if inspection proves the current model cannot persist this key.

- [ ] **Step 3: Make list phase resolve one plugin per URL**

Replace the single `spider = build_spider()` in `_run_list_phase` with a source-aware factory inside `_collect_url`, passing the same callbacks and worker session factory. The runtime should pass only `ThreadedUrlEntry`, callback functions, and scalar configuration into the plugin. Catch a plugin collection exception at the per-future boundary, append the URL-specific error log, and continue awaiting other futures. Do not catch persistence errors as URL collection errors.

- [ ] **Step 4: Make detail phase resolve by `_task_source`**

In `_process_single_detail`, read `detail_info["_task_source"]`, build the matching fetcher/plugin, and call the common `run_single_detail_task`. Unknown source must produce the existing `crawl_failed` result with an actionable error. Keep `random_sleep`, pipeline validation, movie upsert, progress, and status transitions unchanged. The detail phase must not inspect `javbus.com`, construct the Ajax URL, or parse site HTML itself.

- [ ] **Step 5: Route the legacy engine through the same registry**

Update `backend/app/modules/crawler/runtime/engine.py` so its `_build_spider` accepts a source and uses the registry. Preserve the default `javdb` behavior for callers that do not provide a source. Keep the engine's public execution contract independent of concrete spider classes. Do not change `magnet_refresh.py`; it is an explicit JavDB-only refresh workflow outside this crawler task feature.

- [ ] **Step 6: Run runtime regression tests**

Run: `source .venv/bin/activate && cd backend && pytest tests/test_crawler_threaded_runtime.py tests/test_crawler_threaded_url_completion_refresh.py tests/test_crawler_runtime_adapters.py tests/test_crawler_detail_queue.py -q`  
Expected: PASS, including existing JavDB callback and completion behavior.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/threaded.py backend/app/modules/crawler/runtime/details.py backend/app/modules/crawler/runtime/detail_queue.py backend/app/modules/crawler/runtime/engine.py backend/tests/test_crawler_threaded_runtime.py backend/tests/test_crawler_threaded_url_completion_refresh.py backend/tests/test_crawler_runtime_adapters.py
git commit -m "feat: route crawler runtime by source"
```

## Task 6: Make Task Name Extraction Source-Aware

**Files:**
- Modify: `backend/app/modules/crawler/tasks/name_extractor.py`
- Modify: `backend/app/modules/crawler/tasks/router.py` only if request validation currently rejects the JavBus `detail` URL type
- Modify: `backend/tests/test_crawler_source_task_names.py`

**Interfaces:**
- Existing name extraction API remains backward compatible for JavDB.
- JavBus URL extraction uses `SiteSpiderProtocol.extract_url_name` and returns `{ "name": str | None }` in the existing response shape.

- [ ] **Step 1: Write failing JavBus name extraction test**

Patch the site registry with a fake JavBus plugin exposing `extract_url_name(url, url_type)`. Call the existing service/API path with `https://javbus.com/ABCD-123` and assert the fake is selected and its name is returned. Keep the current JavDB search query test unchanged.

Run: `source .venv/bin/activate && cd backend && pytest tests/test_crawler_source_task_names.py -q`  
Expected: FAIL because name extraction currently assumes JavDB.

- [ ] **Step 2: Implement source-aware extraction**

Determine source using `determine_source(url)`, resolve the site plugin, and delegate to `extract_url_name(url, url_type)`. The name-extractor service must not fetch JavBus HTML or duplicate parser logic; that responsibility stays inside `JavbusSpider`. Preserve existing JavDB search and cookie behavior behind the JavDB plugin.

- [ ] **Step 3: Run tests and commit**

Run: `source .venv/bin/activate && cd backend && pytest tests/test_crawler_source_task_names.py tests/test_crawl_tasks_api.py -q`  
Expected: PASS.

```bash
git add backend/app/modules/crawler/tasks/name_extractor.py backend/tests/test_crawler_source_task_names.py
git commit -m "feat: extract javbus task names"
```

## Task 7: Verify Persistence, UI Behavior, and Full Regression Coverage

**Files:**
- Modify: `backend/tests/test_movie_persistence.py` or create a focused test beside the existing movie persistence tests if current fixtures do not cover multiple magnets.
- Modify: `scraper/tests/test_movie_result.py` if pipeline acceptance needs a JavBus-shaped item.
- Modify: `frontend/tests/task-url-utils.test.ts` if UI preview cases are still missing after Task 2.
- Modify: `docs/superpowers/specs/2026-07-20-javbus-crawler-plugin-design.md` only if implementation reveals a concrete contract correction.

**Interfaces:**
- `upsert_movie_with_magnets` receives a JavBus-shaped item with multiple magnets.
- `auto_select_best_magnet` selects exactly one persisted magnet while all distinct magnets remain queryable.

- [ ] **Step 1: Add a persistence regression test**

Persist two distinct magnet dictionaries for one movie, with the lower-ranked magnet first and the higher-ranked magnet second. Assert two `MovieMagnet` rows exist and exactly one row has `selected is True`, with the higher-ranked row selected. This test proves the crawler's all-magnet contract reaches the existing selector.

Run: `source .venv/bin/activate && cd backend && pytest tests/test_movie_persistence.py -q`  
Expected: FAIL only if the current fixture lacks this explicit all-magnet assertion; otherwise retain the existing passing test as coverage.

- [ ] **Step 2: Add a JavBus-shaped pipeline acceptance test**

Pass an item containing `source_name`, `source_url`, `code`, `tags`, and `magnets` but no rating fields through the existing pipeline/persistence path. Assert it is accepted and `has_chinese_sub` is represented through the current tags/magnet normalization.

Run: `source .venv/bin/activate && pytest scraper/tests/test_movie_result.py -q`  
Expected: PASS.

- [ ] **Step 3: Run all focused backend and scraper suites**

Run:

```bash
source .venv/bin/activate
pytest scraper/tests/test_task_utils.py scraper/tests/test_javbus_parser.py scraper/tests/test_javbus_spider.py scraper/tests/test_javdb_parser_detail_title.py scraper/tests/test_javdb_spider_dedupe_callbacks.py scraper/tests/test_movie_result.py
cd backend
pytest tests/test_crawl_tasks_api.py tests/test_crawler_source_task_names.py tests/test_crawler_threaded_runtime.py tests/test_crawler_threaded_url_completion_refresh.py tests/test_crawler_runtime_adapters.py tests/test_crawler_detail_queue.py tests/test_movie_persistence.py
```

Expected: all selected tests pass.

- [ ] **Step 4: Run frontend verification**

Run: `cd frontend && npm test -- --run tests/task-url-utils.test.ts && npm run build`  
Expected: all task URL tests pass and the production build succeeds.

- [ ] **Step 5: Review the complete diff and commit verification changes**

Run: `git diff --check` and `git status --short`. Confirm no JavDB-only parameter is added to JavBus URLs, no JavBus code reads `MAX_LIST_PAGES`, mixed-source runtime tests exercise both phases, and all magnets remain in the returned item and persisted rows.

```bash
git add backend/tests/test_movie_persistence.py scraper/tests/test_movie_result.py frontend/tests/task-url-utils.test.ts
git commit -m "test: verify javbus crawler integration"
```

## Self-Review Checklist

- Spec goal and confirmed decisions are covered by Tasks 1 through 7.
- URL detection, HTTP 400 rejection, frontend controls, and final URL normalization are covered by Tasks 1 and 2.
- JavBus list pagination, detail fields, Ajax parameters, and all-magnet parsing are covered by Tasks 3 and 4.
- Mixed-source list/detail dispatch and per-URL/per-detail failure isolation are covered by Task 5.
- Existing JavDB behavior and legacy engine defaults are explicitly tested in Tasks 4 and 5.
- Best-magnet auto-selection is preserved and explicitly verified in Task 7.
- No task depends on a temporary marker or unspecified file path; each implementation step names an interface, command, or expected result.
