# Crawler URL Drawer Design

## Context

The crawler task create/edit page (`/crawler/tasks/new` and
`/crawler/tasks/$id/edit`) uses `TaskFormPage` for the main task form and a
`Form.List` named `urls` for per-URL crawler configuration.

The page currently supports two URL display modes:

- Card mode: each URL is edited inline through `UrlEntryCard`.
- Table mode: URLs are summarized in an Ant Design table.

In table mode, adding a URL currently appends an empty form-list item but does
not surface an editable UI for that new item. Editing a row switches back to
card mode and scrolls to the corresponding card, which breaks the user's
current list-mode workflow. The crawler task list cards also have footer
actions whose alignment changes as runtime state changes the number and type of
visible buttons.

## Goals

- Keep crawler task URL management focused inside `TaskFormPage`.
- In URL table mode, make add and edit open a right-side drawer instead of
switching back to card mode.
- Preserve card mode as a direct inline editing experience.
- Reuse one URL field implementation across card and drawer editing so URL type
recognition, filter switches, sorting, preview, and name extraction stay
consistent.
- When saving a URL entry from the drawer, automatically fetch `url_name` if the
  user has not already fetched it.
- When submitting the whole task, continue automatically filling missing URL
  names for both card-mode and table-mode entries.
- Keep table-mode delete available and predictable.
- Improve table column sizing for type and name scanning.
- Align buttons in crawler task list cards across different runtime states.

## Non-Goals

- Do not add a new crawler task detail route.
- Do not change backend task, run, or URL APIs.
- Do not change crawler run detail subtasks.
- Do not redesign storage task pages.
- Do not replace the current route and keep-alive behavior.

## UI/UX Guidance Applied

This design follows `ui-ux-pro-max` guidance for a dense internal operations
interface:

- Forms must use visible labels and field-level validation.
- Async submissions must disable controls or show loading feedback.
- Destructive actions must be explicit and protected from accidental invalid
  states.
- Wide tables must use horizontal scrolling instead of overflowing the page.
- Icon-only row actions must have accessible labels and tooltips.
- Dense dashboards should use compact spacing while preserving 44 px practical
  click targets where possible.

## Proposed Approach

Use the current task form as the owner of all URL list state, and introduce a
small drawer editor for table-mode URL add/edit.

### Components

`TaskFormPage`

- Owns the main Ant Design form.
- Owns URL table/card mode.
- Owns drawer state:
  - drawer open/closed
  - mode: create or edit
  - editing URL index for edit mode
  - initial URL entry values
- Appends a new URL entry after drawer create save.
- Replaces an existing URL entry after drawer edit save.
- Continues to submit `CrawlTaskCreateParams` through the existing create/update
  APIs.

`UrlEntryFields`

- New reusable field component extracted from `UrlEntryCard`.
- Receives a form-list index and callbacks for:
  - detected URL type changes
  - extracted URL name changes
- Renders the shared URL fields:
  - URL input
  - derived URL type display
  - hidden `url_type`
  - hidden `url_name`
  - JavDB-only magnet/subtitle switches
  - conditional sort selector
  - final URL preview
  - manual `获取名称` button
- Maintains the current auto-detection behavior when URL changes.

`UrlEntryCard`

- Keeps the current card shell and delete affordance.
- Delegates field rendering to `UrlEntryFields`.
- Remains available only in card mode.

`UrlEntryDrawer`

- New side drawer for table-mode create/edit.
- Uses an internal Ant Design form so canceling the drawer does not mutate the
  main task form.
- Renders one URL entry through `UrlEntryFields` using a local `urls[0]` shape.
- Footer actions:
  - primary `保存`
  - secondary `取消`
  - optional destructive delete action can remain in the table row only; drawer
    does not need a second delete path for this iteration.
- On save, validates the local form, auto-detects URL type, auto-fetches missing
  `url_name` when possible, then passes the completed entry back to
  `TaskFormPage`.

`TaskListCards`

- Keeps the current card grid and runtime action behavior.
- Splits the card footer into stable action groups:
  - left group: runtime actions (`爬取`, `URL 爬取`, `停止`, `重启`)
  - right group: item maintenance actions (`编辑`, `删除`)
- Uses fixed footer height, consistent button sizes, and no layout-dependent
  spacing that changes per status.

## Table Mode Behavior

The URL table remains a summary view, not an inline editor.

- `添加 URL` opens `UrlEntryDrawer` in create mode.
- Row `编辑` opens `UrlEntryDrawer` in edit mode with that row's values.
- Drawer save in create mode appends a completed URL entry to `Form.List`.
- Drawer save in edit mode replaces the selected URL entry.
- The page stays in table mode after saving.
- The table immediately reflects the updated URL, type, name, and final URL.
- Row `删除` remains visible in the operation column.
- If there is more than one URL, row delete removes that entry.
- If there is only one URL, row delete is disabled with a tooltip explaining
  that at least one URL is required.

Recommended table sizing:

- Row number: 56 px
- Type: 150 px
- Name: 220 px with ellipsis and tooltip
- Actions: 104 px, right aligned
- URL and final URL: flexible long-text columns with ellipsis and tooltip
- Horizontal scroll: about 1000-1100 px

## Auto Name Extraction

Manual `获取名称` remains available in both card and drawer editing.

Drawer save adds an earlier convenience step:

1. Validate the drawer form.
2. Detect source and URL type from the URL.
3. If `url_name` is empty and the URL is recognizable, call `extractTaskName`.
4. If extraction succeeds, write the returned name into the saved URL entry.
5. If the parent task name is empty, pass the extracted name back so
   `TaskFormPage` can fill the task name just as card mode does today.
6. If extraction fails or returns no name, show a warning and still save the URL
   entry.

Whole-task submit keeps the existing final enrichment path:

- Before create/update, iterate all URL entries.
- Fill any missing `url_type` using URL detection.
- Fill any missing `url_name` through `extractTaskName` when possible.
- Reject submission only when a URL cannot be recognized as a supported source
  or type, preserving the current validation intent.

This means users do not need to remember to click `获取名称` in card mode or
drawer mode.

## Error Handling

- Drawer form validation errors stay beside the relevant fields.
- Drawer name extraction failure shows a warning and leaves the drawer open only
  if validation failed; extraction failure alone does not block saving.
- Drawer save buttons show loading while validation and name extraction are in
  progress.
- Whole-task submit keeps existing success and error messages.
- Delete uses the existing immediate list removal pattern, guarded by the
  one-URL minimum rule.

## Responsive Behavior

- Card mode remains responsive through the existing grid.
- Table mode uses horizontal scroll for dense columns and avoids page-level
  overflow.
- Drawer uses a desktop-friendly width around 520-640 px.
- On narrow screens, drawer width should become full width.
- Footer buttons should remain reachable without overlapping form content.

## Testing

Add focused frontend tests under `frontend/src/pages/crawler/tasks`:

- Table-mode `添加 URL` opens the drawer instead of silently appending an
  invisible item.
- Saving a new drawer entry appends it and shows it in the table.
- Editing a table row through the drawer updates that row without switching to
  card mode.
- Table-mode delete is visible; it removes entries when count is greater than
  one and is disabled for the final remaining entry.
- Drawer save calls `extractTaskName` when `url_name` is empty and URL detection
  succeeds.
- Drawer save continues when name extraction fails and surfaces a warning.
- Whole-task submit still enriches missing URL names for card-mode entries.

Verification commands:

```bash
cd frontend && npm test -- src/pages/crawler/tasks
cd frontend && npm run build
```

## Acceptance Criteria

- In URL table mode, users can add, edit, and delete URL entries without leaving
  table mode.
- Newly added URL entries are visible in the table immediately after drawer save.
- Edited URL entries update the correct row.
- Missing URL names are automatically fetched on drawer save when possible.
- Missing URL names are also handled during whole-task save for card-mode
  entries.
- Type and name columns in table mode are wide enough for common values and use
  tooltip-backed ellipsis for longer content.
- Crawler task list card buttons align consistently across idle, running,
  queued, stopped, and disabled task states.
