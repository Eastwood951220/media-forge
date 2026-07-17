# Movie List and Magnet Refresh Design

## Problem

The crawler run detail task list does not show useful code and movie title values for temporary detail runs, even after the detail page has enough data. The movie list action column also exposes too many direct actions, making the table harder to scan.

Users also need a way to refresh magnet links for one or more existing movies. This refresh should create a normal crawler run record for progress tracking, but it must only update the movie magnet library and must not overwrite movie detail fields or mutate the movie's real `source_task_ids`.

## Goals

- Show code and movie name in temporary run subtasks whenever the backend has those values.
- Move row-level movie actions other than detail into a "More" dropdown.
- Add a single magnet refresh API that accepts one or more movie ids.
- Create a crawler run record for magnet refresh progress.
- Automatically create or reuse a current-user "Magnet Refresh" display crawl task for those runs.
- Refresh only magnets for target movies.
- Do not update movie detail fields such as title, actors, tags, rating, release date, or raw detail.
- Do not append the display task id to `movie.source_task_ids`.

## Non-Goals

- Do not change normal crawler full, incremental, or temporary detail behavior except where shared display serialization needs a safe fallback.
- Do not introduce a separate task system outside crawler runs.
- Do not change storage push behavior.
- Do not change magnet scoring rules beyond reusing the existing auto-select-best behavior after upsert.

## Recommended Approach

Implement this as two related changes under one feature:

1. **Display and action cleanup**
   - Enhance crawler run detail task serialization so temporary detail rows expose display code and display source name from `item_data` when persisted columns still contain placeholders.
   - Update the run task table to render those display values.
   - Change the movie table action column to show "Detail" directly and move push, CD2 sync, magnet refresh, and delete into a dropdown.

2. **Magnet refresh run**
   - Add `POST /api/content/movies/magnet-refresh` with `{ movie_ids: string[] }`.
   - The endpoint ensures a current-user display task named `磁力更新` exists.
   - It creates a `crawl_runs` row with `crawl_mode = "magnet_refresh"`.
   - It creates one `crawl_run_detail_tasks` row per target movie.
   - The crawler worker detects `magnet_refresh` runs and processes detail rows through a magnet-only path.

## Backend Design

### Magnet Refresh API

Add a request schema:

```json
{
  "movie_ids": ["uuid"]
}
```

Validation:

- `movie_ids` must contain at least one id.
- All movies must belong to the current user by normal movie visibility rules. Since movies are currently owner-linked through source tasks, the implementation should require at least one existing source task for the current user, or otherwise reject the movie.
- Movies without `source_url` should still create detail rows, but those rows should be marked skipped with a clear reason.

Response:

- Return the created crawler run payload so the frontend can open the run detail page.

### Display Crawl Task

Create or reuse a `CrawlTask` for the current user:

- `name = "磁力更新"`
- `storage_location = ""`
- It is only used for run grouping and display.
- It must not be appended to `movie.source_task_ids`.

### Run and Detail Rows

For each selected movie:

- `code = movie.code`
- `source_name = movie.source_name`
- `source_url = movie.source_url`
- `source_url_name = "磁力更新"`
- `task_url_type = "magnet_refresh"`
- `status = "pending_crawl"` when `source_url` exists
- `status = "skipped"` with error `missing_source_url` when `source_url` is empty

### Worker Mode

For `crawl_mode = "magnet_refresh"`:

- Skip list collection.
- Process only detail rows.
- Fetch each detail page using the existing detail spider path.
- Extract `magnets` from the detail result.
- Upsert magnets for the existing movie id/code using the existing `upsert_magnets` and `auto_select_best_magnet` logic.
- Mark the row `saved` when magnet upsert succeeds.
- Mark the row `crawl_failed` or `save_failed` when fetch or persistence fails.
- Do not call movie upsert for the main movie document.
- Do not call `append_source_task_id`.

## Frontend Design

### Temporary Task Display

Run detail task rows should render:

- Code: `record.code`, then `record.item_data?.code`, then `-`.
- Source name: if `record.source_name` is a placeholder such as `临时详情页`, prefer `record.item_data?.source_name` or `record.item_data?.name`.
- URL source remains `source_url_name || task_url_type || "-"`.

Search should continue using backend keyword search. Backend keyword matching must include `item_data.code`, `item_data.source_name`, and `item_data.name` for rows whose persisted `code` or `source_name` are empty or temporary placeholders.

### Movie Row Actions

Movie table row actions:

- Direct button: `详情`
- Dropdown button: `更多`
  - `推送`
  - `CD2同步`
  - `更新磁力`
  - `删除`

`删除` remains danger-styled in the menu. `CD2同步` keeps per-row loading state.

### Bulk Actions

When rows are selected:

- Keep `批量推送`
- Add `批量更新磁力`
- Keep `批量删除`

Magnet refresh success should show a message and offer navigation to the created run detail route.

## Error Handling

- If the refresh endpoint receives no ids, return a 400 response.
- If no selected movie is valid for the user, return a 400 response.
- If some movies lack `source_url`, create skipped detail rows rather than failing the whole run.
- If the worker cannot fetch a detail page, mark only that detail row failed.
- If magnet parsing returns no magnets, mark that row `skipped` with error `no_magnets_found` and log the source URL.

## Testing

Backend tests:

- Temporary run task serialization exposes display code/name from `item_data`.
- `POST /api/content/movies/magnet-refresh` accepts one id and multiple ids through the same payload shape.
- The endpoint creates or reuses a display task named `磁力更新`.
- The endpoint creates a `magnet_refresh` run and detail rows.
- Missing `source_url` rows are skipped.
- Magnet refresh worker upserts magnets without changing movie detail fields or `source_task_ids`.

Frontend tests:

- Movie row actions render `详情` and a `更多` dropdown.
- Dropdown contains push, CD2 sync, update magnets, and delete.
- Bulk toolbar shows `批量更新磁力` when rows are selected.
- Temporary task rows display fallback code/name from `item_data`.
