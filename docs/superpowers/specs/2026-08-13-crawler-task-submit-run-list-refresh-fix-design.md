# Crawler Task Submit And Run List Refresh Fix Design

## Problem

Two crawler frontend regressions need to be fixed:

- In crawler task edit mode, switching to URL list mode and clicking `更新` can save an empty URL list. The database table `crawl_task_urls` is then cleared for that task.
- The crawler run list repeatedly requests the list API instead of settling after the normal initial load and intentional refresh events.

The current working tree also contains unrelated theme-transition edits. This fix must not touch or revert those files.

## Evidence

### Task Edit URL Loss

`TaskFormPage` loads an existing task with `getCrawlTask(taskId)` and maps `task.urls` into the Ant Design form. The table-mode URL list renders values by calling `form.getFieldValue` inside table column render functions. Those table cells are display-only and do not register URL fields through `Form.Item`.

`handleSubmit` currently builds the URL payload from `values.urls` passed by `onFinish`. In table mode, that value can be incomplete or empty compared with the form's current internal URL state. If `updateCrawlTask(taskId, payload)` receives `urls: []`, the backend update path replaces the task URL relationship with an empty list, clearing `crawl_task_urls`.

Backend `replace_urls` reuses rows by URL string, not by frontend `id`, so the primary frontend requirement is to submit a complete non-empty URL array. Preserving URL metadata still helps keep table/edit workflows stable and avoids losing context for URL-specific run actions.

### Run List Request Loop

`RunListPage` creates `listParams` as a new object on every render:

```ts
const listParams = { page: current, size: pageSize }
```

`refreshRuns` depends on `listParams`, so `refreshRuns` also changes on every render. `useRouteActivationRefresh(refreshRuns)` receives that changing callback and can invalidate run queries again after render. The realtime subscription effect also depends on the changing `listParams`, so it can repeatedly unsubscribe and resubscribe. The likely loop is:

```text
render -> new listParams -> new refreshRuns -> activation refresh invalidates queries -> query state changes -> render
```

## Decision

Use the frontend-focused fix:

- Make crawler task edit submission derive URL entries from the live form state, not only from `onFinish(values)`.
- Normalize and validate URL entries before submit.
- Refuse to call `updateCrawlTask` or `createCrawlTask` when the normalized URL list is empty.
- Preserve loaded URL metadata when initializing edit mode.
- Stabilize `RunListPage` query params and refresh callbacks with `useMemo` and `useCallback`.
- Keep realtime list updates in-place with `setQueryData`; do not invalidate the run list on every realtime update.

Do not add backend changes in this pass. The backend can be hardened later, but this regression is caused by a frontend payload construction path and should be fixed at the source first.

## User-Facing Behavior

- Editing an existing crawler task in list mode and clicking `更新` preserves every visible URL unless the user explicitly deletes it.
- If the URL list is empty at submit time, the page shows an error and does not send the update request.
- Card mode and list mode both submit the same normalized URL entries.
- Auto-fetching missing URL names during submit continues to work.
- Existing duplicate URL validation continues to run before submit.
- The run records page loads the list once for the current page and size, plus the count request.
- The run records page refreshes only on route activation, explicit actions such as stop/restart/delete, page changes, or count/list invalidation from real mutations.
- Realtime `crawler.run.updated` events update matching rows in the current page without causing a continuous list refetch loop.

## Architecture

### TaskFormPage URL Payload

Add a small helper near the task form submit logic:

```ts
function normalizeUrlEntriesForSubmit(entries: TaskUrlEntry[] | undefined): TaskUrlEntry[] {
  return (entries ?? [])
    .filter((entry) => entry?.url?.trim())
    .map((entry) => ({
      id: entry.id,
      position: entry.position,
      url: entry.url.trim(),
      url_type: entry.url_type,
      has_magnet: entry.has_magnet ?? false,
      has_chinese_sub: entry.has_chinese_sub ?? false,
      sort_type: entry.sort_type ?? 0,
      source: entry.source,
      final_url: entry.final_url,
      url_name: entry.url_name?.trim() ?? '',
    }))
}
```

`handleSubmit` will read:

```ts
const currentUrlEntries = form.getFieldValue('urls') as TaskUrlEntry[] | undefined
const urlEntries = normalizeUrlEntriesForSubmit(currentUrlEntries)
```

The submitted values still provide task-level fields such as `name`, `storage_location`, and `is_skip`. URL entries come from the current form instance because that is the source both card mode and table mode mutate.

Before duplicate validation and enrichment, `handleSubmit` must check:

```ts
if (urlEntries.length === 0) {
  message.error('请至少保留一个 URL')
  return
}
```

Edit-mode initialization will preserve metadata from loaded entries:

```ts
{
  id: entry.id,
  position: entry.position,
  url: entry.url,
  url_type: entry.url_type,
  has_magnet: entry.has_magnet ?? true,
  has_chinese_sub: entry.has_chinese_sub ?? false,
  sort_type: entry.sort_type ?? 0,
  source: entry.source,
  final_url: entry.final_url,
  url_name: entry.url_name ?? '',
}
```

The enrichment step may continue returning only the fields accepted by the backend. The normalized submit list is the guardrail against empty-array updates; metadata preservation is for frontend continuity.

### RunListPage Query Stability

`RunListPage` will memoize params:

```ts
const listParams = useMemo(() => ({ page: current, size: pageSize }), [current, pageSize])
const countParams = useMemo(() => ({}), [])
```

`refreshRuns` will depend on stable params:

```ts
const refreshRuns = useCallback(() => {
  void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerRuns.list(listParams) })
  void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerRuns.count(countParams) })
}, [countParams, listParams, queryClient])
```

The realtime effect will depend on the stable `listParams` and `queryClient`. It will continue using `setQueryData` for current-page row updates. It will not call `invalidateQueries` for every `crawler.run.updated` event.

## Error Handling

- Empty normalized URL list: show `请至少保留一个 URL`, leave the user on the edit page, and do not call the update API.
- Duplicate URL: keep the existing duplicate message and return before submit.
- Unsupported URL source/type: keep the existing validation and return before submit.
- Name extraction failure: keep current behavior; leave `url_name` empty and continue if URL type/source is valid.
- Run list realtime update for a row not on the current page: leave current page data unchanged.

## Testing

Add or update frontend tests:

- In `task-url-drawer.test.tsx`, add an edit-mode list-table submit test that switches to list mode, clicks `更新`, and asserts `updateCrawlTask` receives the two existing URLs, not `urls: []`.
- In the same test file, assert loaded edit URLs preserve `id` when submitted.
- Add a submit guard test that sets form URL state to an empty list through the UI path or a focused component setup, clicks `更新`, and asserts `updateCrawlTask` is not called and `请至少保留一个 URL` is shown.
- In `run-list-query.test.tsx`, assert initial render calls `getCrawlerRuns` once with `{ page: 1, size: 20 }` and does not repeatedly call it after waiting for query settle.
- In `run-list-query.test.tsx`, assert a realtime `crawler.run.updated` event updates visible row state without calling `getCrawlerRuns` again.

Run:

```bash
cd frontend && npm test -- src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx src/pages/crawler/runs/__tests__/run-list-query.test.tsx
cd frontend && npm run build
```

Manual verification:

- Open an existing crawler task with multiple URLs.
- Switch to list mode.
- Click `更新`.
- Reopen the task and verify the URL rows are still present.
- Confirm `crawl_task_urls` remains populated for the task.
- Open `/crawler/runs` and confirm the list request does not repeat continuously in the browser network panel.

## Out Of Scope

- Backend schema or repository changes.
- Crawler runtime behavior.
- Storage task pages.
- Theme toggle files.
- General refactoring of Ant Design form structure.
- Changing realtime event protocol.
