# Temporary Run Detail Title And Code Design

## Context

Temporary crawler runs seed `crawl_run_detail_tasks` from user-provided detail
URLs. The seeded rows currently use placeholder values such as `临时详情页`
and `临时任务`, so the run detail task table and movie detail drawer can show
temporary labels even after the detail page has been crawled.

The JAVDB detail page contains the canonical title area under
`.video-detail h2.title.is-4`, for example:

```html
<h2 class="title is-4">
  <strong>TIMD-036 </strong>
  <strong class="current-title">極上メス男子ゆうきくん無限アクメ肉棒大乱交！！ </strong>
</h2>
```

For temporary runs, the application should display `TIMD-036` as the movie code
and `極上メス男子ゆうきくん無限アクメ肉棒大乱交！！` as the title once the detail
page is parsed.

## Goals

- Parse the real movie code and title from the JAVDB detail page title block.
- Persist parsed code and title back to the run detail row for new temporary
  runs.
- Keep old completed temporary runs readable by deriving display fields from
  `item_data` when database row fields still contain placeholders.
- Keep run detail table search and realtime updates consistent with the API
  snapshot.

## Non-Goals

- No database migration or bulk backfill for historical temporary runs.
- No frontend layout redesign.
- No new crawler modes or task creation behavior.
- No change to regular list-based crawler runs except improved detail parsing
  when the same page structure is encountered.

## Approach

Use a backend-first data flow:

1. Enhance the JAVDB detail parser to recognize the structured title block.
2. Update the runtime detail row after successful detail parsing and pipeline
   cleanup.
3. Serialize consistent display fields from API and realtime payloads.
4. Leave the frontend table on `display_code` and `display_source_name`, with
   existing `code` and `source_name` fallbacks.

This keeps display behavior centralized and avoids pushing parsing or data
repair logic into React components.

## Parser Design

`scraper/spiders/javdb/javdb_parser.py` will add a small helper for detail title
metadata:

- Prefer `.video-detail h2.title.is-4 strong::text`.
- Treat the first non-empty `strong` as the code.
- Prefer `.video-detail h2.title.is-4 strong.current-title::text` as the title.
- If `current-title` is missing, use the second non-empty `strong` as the title.
- Strip whitespace through existing `clean_text`.
- Fall back to existing title selectors when the structured block is missing.

`parse_detail_page` will include `code` in the returned detail dict when found,
and set `source_name` to the parsed title instead of the combined or empty
placeholder text.

## Runtime Persistence Design

`backend/app/modules/crawler/runtime/threaded.py` will update
`CrawlRunDetailTask` after `pipeline.process_item` returns cleaned data:

- `detail.code` becomes `cleaned["code"]` when non-empty; otherwise keep the
  existing value.
- `detail.source_name` becomes `cleaned["source_name"]` when non-empty and not
  a temporary placeholder; otherwise keep the existing value.
- `detail.item_data` remains the full cleaned item for historical fallback and
  detail drawer data.

The update should not depend on the run being temporary. Regular runs already
have list-stage values, and replacing them with detail-page canonical values is
consistent with the crawler's source of truth.

## API And Realtime Design

The run detail task API already exposes `display_code` and
`display_source_name`. It will remain the canonical frontend contract:

- `display_code`: row `code`, then `item_data.code`, then `null`.
- `display_source_name`: row `source_name`, unless it is a temporary
  placeholder; then `item_data.source_name` or `item_data.name`; then the row
  value as a final fallback.

Realtime detail updates should use the same serialization path as the REST API,
so a running detail page does not momentarily replace real display text with
placeholder fields.

Keyword filtering should continue checking row fields and `item_data` fields so
old completed temporary runs can be found by parsed code or title.

## Error Handling

- If the title block is missing or malformed, parsing falls back to existing
  selectors and the run detail row keeps its current values.
- If code is absent but title exists, the title still updates.
- If title is absent but code exists, the code still updates.
- Failed detail crawls keep their existing placeholder fields until a retry
  succeeds.

## Testing

Add focused tests:

- Parser test for `.video-detail h2.title.is-4` with code and
  `.current-title`.
- Parser fallback test for existing title structures.
- Threaded runtime test proving a temporary seeded detail row is updated from
  parsed `code` and `source_name` after successful processing.
- API serialization or realtime payload test proving old placeholder rows with
  `item_data` expose real `display_code` and `display_source_name`.

Run the focused backend tests first:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_threaded_runtime.py backend/tests/test_crawler_runs_api.py backend/tests/test_javdb_spider_multi_url.py scraper/tests -q
```

If frontend code remains unchanged, no frontend build is required for this
feature. If the frontend contract changes during implementation, run the
focused crawler run page tests and `npm run build` from `frontend/`.
