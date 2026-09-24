# JavDB Page Actions Design

## Summary

Add contextual Media Forge controls directly to JavDB pages through the
existing Chrome extension:

- A movie detail page can create a temporary crawl run under an existing task.
- Any movie-list page except the JavDB home page can create a new task and
  immediately start a full crawl.
- The same list page can be added to an existing task and immediately start an
  incremental crawl scoped to that URL.

The page UI runs in the content script, but all authenticated requests run in
the extension background service worker. New Agent-authenticated backend
endpoints resolve the owner from the configured Agent token and reuse the
existing crawler task and run services.

## Goals

- Make the current JavDB page actionable without copying URLs into Media
  Forge manually.
- Keep task ownership and authorization enforced by the backend.
- Preserve the current list page's search, filter, and sort parameters while
  always starting traversal from page 1.
- Prevent duplicate task URLs and duplicate task names.
- Provide clear loading, success, partial-failure, and error feedback within
  the injected UI.
- Preserve the existing Agent WebSocket task-execution protocol.

## Non-goals

- Redesigning the extension popup or options page.
- Adding controls to the JavDB home page.
- Supporting non-JavDB sites.
- Changing crawler scheduling or storage-task behavior.
- Adding a new frontend framework to the Chrome extension.
- Changing the meaning of full, incremental, or temporary crawler runs.

## Page Classification

The content script classifies the current page in this order:

1. The normalized root path `/` is `home` and receives no page-action UI.
2. A path matching `/v/<identifier>` is `detail`.
3. A non-home, non-detail page containing the JavDB movie-list structure is
   `list`.
4. Everything else is `unsupported` and receives no page-action UI.

List classification uses both the URL and the actual movie-list DOM instead of
only a fixed route allowlist. This covers existing routes such as search,
actors, series, makers, directors, video codes, lists, and tags, while also
covering future JavDB list routes that retain the same movie-card structure.

The content script re-evaluates the page after history navigation and relevant
DOM replacement. A stable extension host element ID makes mounting
idempotent, so re-evaluation cannot add duplicate controls.

## Injected Interface

The content script mounts a fixed-position toolbar into a Shadow DOM root. The
Shadow DOM prevents JavDB styles from changing the extension UI and prevents
extension styles from affecting the host page. The implementation remains
plain TypeScript and DOM APIs, consistent with the existing extension.

Controls have visible text and icons, a minimum 44 by 44 pixel target, visible
keyboard focus, and accessible names. The toolbar occupies the right edge of
the viewport without covering the page's primary controls. It can adapt its
vertical position when the viewport is small.

### Detail page

The toolbar contains one action: `加入临时任务`.

Opening it shows a modal containing:

- The detected movie title and current detail URL as read-only context.
- A searchable selector containing enabled tasks only.
- A submit action that creates a temporary run with the current detail URL.

The crawl mode is the existing temporary-detail mode and is not editable.

### List page

The toolbar contains two actions.

#### Quick create and crawl

`快速创建并全量爬取` opens a modal containing:

- The normalized current list URL as read-only context.
- An editable task name prefilled from the current section heading, search
  keyword, or document title fallback.
- A read-only crawl-mode indicator showing `全量爬取`.

Submitting creates an enabled task with one URL, uses the final task name as
its storage location, and starts a full crawl. If the task name already exists,
the backend returns a conflict and no task is created. The system does not add
numeric suffixes automatically.

#### Add to an existing task

`加入已有任务并增量爬取` opens a modal containing:

- The normalized current list URL and detected list name.
- A searchable selector containing enabled tasks only.
- A read-only crawl-mode indicator showing `增量爬取`.

If the normalized URL is absent from the selected task, the backend appends it
and starts an incremental run scoped only to the new URL. If the normalized
URL is already present, the backend does not add another row and starts the
same URL-scoped incremental run using the existing URL entry.

### Shared modal behavior

- Task choices load only when a modal that needs them is opened.
- Submit controls are disabled while a request is in flight.
- Forms use visible labels and preserve user input after recoverable errors.
- Errors render beside the relevant field or in an announced modal error
  region.
- Escape closes the modal, focus stays inside while open, and focus returns to
  the invoking control when closed.
- Success shows the task name, run ID, `查看运行详情`, and `关闭`.
- Success does not navigate automatically. `查看运行详情` opens the Media
  Forge run-detail route in a new tab.

## Extension Architecture

### Content script

`chrome-extension/src/content.ts` remains responsible for existing page
snapshot collection and gains page classification, page metadata extraction,
UI mounting, modal state, and typed page-action requests.

The content script never reads the Agent token and never performs backend
requests. It sends typed messages to the background service worker and renders
the returned result.

The UI should be separated into focused modules rather than turning
`content.ts` into a monolith. Expected boundaries are:

- Page classification and metadata extraction.
- URL normalization utilities shared with tests.
- Background message contracts.
- Shadow DOM toolbar and modal rendering.

### Background service worker

`chrome-extension/src/background.ts` handles page-action messages. It reads the
configured backend URL and Agent token from extension storage, constructs the
Agent-authenticated HTTP request, maps network and backend errors into the
typed response contract, and returns the result to the content script.

No token, authorization header, or raw backend response is sent to the host
page. Diagnostic logging must redact tokens and authorization data.

The existing Agent connection, cookie synchronization, and WebSocket task
execution behavior remain unchanged.

## Backend API

Add an Agent-authenticated page-actions area under the existing crawler Agent
router namespace.

### Authentication

Requests use:

```text
Authorization: Bearer <Agent Token>
```

A shared dependency validates the token against an Agent record and returns
the Agent owner ID. All task lookup, mutation, and run creation is scoped to
that owner. These endpoints do not accept a user ID from the request.

The content script cannot supply or override the owner ID. A valid Agent token
cannot access another owner's tasks.

### Endpoints

#### `GET /api/crawler/agent/page-actions/tasks`

Returns enabled tasks for the authenticated Agent owner, ordered by task name.
Each item contains only the task ID and name needed by the selector.

#### `POST /api/crawler/agent/page-actions/temporary-runs`

Request fields:

- `task_id`
- `detail_url`

The service validates that the URL is a JavDB detail URL, verifies that the
owned task still exists and is enabled, and creates a temporary detail run.

#### `POST /api/crawler/agent/page-actions/quick-create-runs`

Request fields:

- `name`
- `page_name`
- `list_url`

The service validates and normalizes the URL, detects its known URL type or
uses the generic JavDB list type, rejects an existing task name, creates one
enabled task URL, and starts a full crawl.

`page_name` becomes the URL entry's display name. `name` is the final editable
task name and storage location.

#### `POST /api/crawler/agent/page-actions/add-url-runs`

Request fields:

- `task_id`
- `page_name`
- `list_url`

The service verifies that the owned task exists and is enabled, normalizes the
URL, finds or appends the matching URL entry, and starts an incremental run
scoped to that URL entry.

### Success response

Mutation endpoints return a stable result containing:

- `task_id`
- `task_name`
- `run_id`
- `crawl_mode`
- `url_entry_id` when the run is scoped to a persisted list URL
- `url_added` for add-to-task requests

This is sufficient for confirmation UI and the run-detail link.

### Error contract

The API returns stable machine-readable codes plus a user-readable message for:

- Missing or invalid Agent authorization.
- Unsupported host or page type.
- Missing, deleted, or disabled task.
- Duplicate task name.
- Invalid or empty task name.
- Invalid detail URL.
- Run creation or runtime availability failure.

The background script maps transport failures separately from backend business
errors so the modal can distinguish an unreachable backend from rejected
input.

## URL Normalization and Duplicate Detection

For list actions, the backend is the authority for normalization:

1. Require `http` or `https` and a `javdb.com` host or subdomain.
2. Reject the home page and detail pages.
3. Remove the URL fragment.
4. Preserve search, filter, and sort parameters.
5. Replace any existing `page` value with `1`, or add `page=1` when absent.
6. Sort query keys into a stable order for storage and equality checks.
7. Normalize the host casing and omit default ports.

The normalized URL is stored as the task URL and final URL so later crawler
page generation starts from the same selected view and replaces only the page
number.

Duplicate detection compares normalized URLs, not raw input strings. A URL
with reordered query parameters or a different page number therefore resolves
to the same task URL entry.

## Data and Transaction Behavior

No database migration is expected. The feature uses existing crawl task, task
URL, crawl run, and temporary detail task records.

The new service operations centralize composite workflows so the extension
does not chain several public APIs:

- Quick create validates all input and the name conflict before inserting the
  task and run.
- Add-to-task resolves or appends the URL entry before creating a scoped run.
- Temporary run delegates to the existing temporary-detail run behavior.

Database mutations should commit in a consistent unit with the run record.
Runtime enqueue happens after the run exists. If enqueue or worker startup
fails after persistence, the API must report the run ID and explicit partial
failure state instead of claiming that nothing was created; the persisted run
remains visible and diagnosable in Media Forge.

Concurrent add-to-task requests must re-check the normalized URL under the
transaction and resolve to one URL entry. If the existing schema does not
enforce the required uniqueness, the service must use an appropriate lock and
repeat the lookup before insert rather than introducing unrelated schema
changes.

## Security

- Agent tokens remain in `chrome.storage.sync` and the extension background
  context.
- The content script sends action data but never credentials.
- Every backend operation derives ownership from the verified Agent token.
- URLs are parsed and validated on the backend; the host page cannot request
  arbitrary backend fetch targets.
- Error responses and extension diagnostics never include credentials.
- Existing short-lived Agent sessions and WebSocket authentication remain
  unchanged.

## Testing

### Chrome extension

Add focused tests for:

- Home, detail, supported list, generic DOM-backed list, and unsupported page
  classification.
- Single mounting across repeated classification and history changes.
- Detail title and list-name extraction fallbacks.
- URL normalization preview and forced page 1 behavior.
- Detail, quick-create, and add-to-task modal validation.
- Enabled-task loading, selector search, loading state, recoverable errors,
  success state, and run-detail link construction.
- Typed background message dispatch.
- Missing settings, network failure, authorization failure, and backend error
  mapping.
- Assurance that content-script messages and rendered DOM contain no token.

Run:

```bash
cd chrome-extension
pnpm typecheck
pnpm test
pnpm build
node scripts/verify-agent-extension.mjs
```

### Backend

Add focused tests for:

- Valid, missing, and invalid Agent tokens.
- Owner isolation and enabled-task filtering.
- Detail URL validation and temporary run creation.
- Quick create plus full run creation.
- Duplicate task name rejection with no new task.
- Query preservation, fragment removal, stable parameter order, and forced
  `page=1`.
- Adding a new URL and starting only that URL incrementally.
- Reusing an existing normalized URL without duplication.
- Concurrent duplicate-add protection.
- Deleted or disabled task handling between selector load and submission.
- Generic DOM-backed list URL behavior.
- Runtime start failure and partial-state response behavior.

Run focused backend tests first, followed by the broader crawler task and Agent
tests when practical.

## Documentation

Update the Chrome extension documentation and `frontend/README.md` only where
their existing architecture and workflow descriptions need to mention the new
page actions and Agent-authenticated endpoints. No user-facing route is added
to the React frontend.

## Acceptance Criteria

- No page-action control appears on the JavDB home page or unsupported pages.
- A detail page can create a temporary run under a selected enabled task.
- Every non-home page containing the JavDB movie-list DOM exposes both list
  actions.
- Quick create shows an editable default name, rejects name conflicts, creates
  one enabled task, and starts a full crawl.
- Add-to-task appends a new normalized URL or reuses the existing URL, then
  starts an incremental run scoped only to that URL.
- All stored list URLs preserve current filter, search, and sort parameters and
  use `page=1`.
- Success UI shows the run ID and can open the Media Forge run detail without
  navigating automatically.
- Agent credentials remain inaccessible to the host page.
- Focused extension and backend verification passes without including the
  pre-existing unrelated modification to
  `scraper/spiders/javdb/javdb_spider.py` in the commit.
