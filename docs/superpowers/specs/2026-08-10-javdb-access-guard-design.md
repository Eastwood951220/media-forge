# JavDB Access Guard Design

Date: 2026-08-10

## Context

Media Forge can open JavDB in the user's Chrome session after the user completes
site verification, but backend crawler requests can still receive HTTP 403 from
JavDB. The affected backend flows currently use `CookieManager` and
`ScraplingFetcher` with exported cookies and fixed headers:

- task URL name extraction
- JavDB list page collection
- JavDB detail page collection
- magnet refresh

The current security-page detector only checks response text for verification
keywords. When JavDB returns a 403 page that does not match those keywords, the
code may parse it as a normal page. This creates false success cases, such as
`extract-name` returning HTTP 200 with an empty name or list crawling stopping as
if the page had no data.

## Goals

- Detect JavDB access blocks consistently across name extraction, list crawling,
  detail crawling, and magnet refresh.
- Prevent false success when a blocked page returns no parseable data.
- Give the user actionable errors: refresh cookies, complete browser
  verification, reduce request rate, or switch fetch mode.
- Add a health check so the user can verify the backend crawler session before
  running a task.
- Preserve existing parsers and crawler behavior for normal successful pages.
- Avoid automatic captcha solving, credential extraction, or bypass behavior.

## Non-Goals

- Do not automatically solve or bypass human verification.
- Do not read cookies directly from Chrome profiles.
- Do not store browser profile data in the repository.
- Do not add unrelated crawler features or new JavDB data fields.
- Do not change JavBus behavior except where shared fetch helpers need neutral
  compatibility.

## Recommended Approach

Implement this in three layers:

1. Add a shared access-state detector for HTTP status and verification content.
2. Use that detector at every JavDB request boundary before parsing.
3. Add a JavDB cookie health-check endpoint and optional browser fetch mode.

The first implementation plan should prioritize layers 1 and 2 plus the health
check. Browser fetch mode can be implemented behind a config flag after the
static mode reports accurate failures.

## Architecture

### Access State Model

Create a small security/access helper in `scraper/core/security.py`:

- `get_response_status(page) -> int | None`
- `detect_access_state(page) -> AccessState`
- `is_security_check_page(page) -> bool`

`AccessState` should include:

- `ok`: true only when the page is safe to parse
- `status_code`: best-effort HTTP status code
- `reason`: one of `ok`, `http_403`, `http_429`, `security_keywords`, or
  `unknown_error`
- `message`: user-facing Chinese summary

`is_security_check_page(page)` remains for existing call sites but delegates to
`detect_access_state(page)` and returns false only for `ok`.

Status lookup should be defensive because Scrapling page objects may expose
status differently across fetcher implementations. The helper should check
common attributes such as `status`, `status_code`, `response.status`,
`response.status_code`, and `metadata`.

### Fetcher Compatibility

`ScraplingFetcher` should keep its existing public shape but avoid hiding status
information. If Scrapling already exposes status on the page object, no wrapper
is needed. If static and dynamic fetchers expose status differently, normalize it
with a lightweight local attribute after fetching when possible.

Static mode remains the default.

### JavDB Name Extraction

In `backend/app/modules/crawler/tasks/name_extractor.py`, JavDB extraction
should:

1. Fetch the URL.
2. Run `detect_access_state(page)`.
3. Raise `HTTPException(429, message)` for access-block states.
4. Parse the section name only when access is ok.
5. If the page is ok but no name is found for a URL type that should have a
   name, raise a clear upstream parse error instead of returning silent empty
   success.

Search URLs keep the current query-string behavior and do not fetch JavDB.

### JavDB List Collection

In `scraper/spiders/javdb/javdb_spider.py`, list page collection should run the
access detector immediately after `self.fetch(page_url)` and before
`parse_search_page`.

If blocked:

- increment the existing verification/access counter
- log the status and reason
- wait using `SECURITY_WAIT_SECONDS`
- retry only up to the configured maximum attempts
- after the maximum, fail the current URL collection with an explicit exception
  or failure result that the runtime records as failed

An empty `parse_search_page` result should be treated as "no data" only when the
access state is ok.

### JavDB Detail Collection

Detail collection should use the same detector before `parse_detail_page`.
Blocked detail pages should stay pending only during limited retry. After the
retry limit, the detail task should become failed with a message that includes
the access reason and suggests refreshing cookies or completing browser
verification.

### Magnet Refresh

Magnet refresh builds a JavDB spider and uses detail parsing. It should receive
the same detail failure behavior so blocked pages do not look like parse errors
or empty magnet results.

## Cookie Health Check

Add a backend endpoint under crawler config:

- `POST /api/crawler/config/cookies/test`

Request body:

- optional `url`, defaulting to `https://javdb.com/`

Response data:

- `ok`
- `status_code`
- `reason`
- `message`
- `url`
- `logged_in_detected`

The endpoint uses the current saved JavDB cookie file and site headers. It does
not accept raw cookies in the request body, so cookies continue to be managed by
the existing save endpoint.

`logged_in_detected` can be best-effort and based on visible page markers, such
as a profile/user link. It must not require a specific username.

## Frontend

Update `/crawler/config` to add a "测试 Cookie" action next to the cookie save
controls.

Behavior:

- The button calls the health-check endpoint.
- Success shows that the backend crawler session can access JavDB.
- Failure shows the returned reason and message.
- After saving cookies, the page may offer or automatically run the test.

The UI should not display full cookie values outside the existing JSON editor.

## Optional Browser Fetch Mode

Add a future-safe config flag:

- `JAVDB_FETCH_MODE=static | browser`

Default: `static`.

When `browser` is enabled, JavDB fetches should use Playwright/Chromium with a
browser context initialized from the saved cookie JSON. The crawler then passes
the loaded HTML into the existing JavDB parsers. This mode is a fallback for
cases where static HTTP requests are blocked but browser-like page loading with
the same exported cookies succeeds.

Browser mode rules:

- It does not solve captchas.
- It does not read the user's Chrome cookie store.
- It uses only cookies explicitly saved through Media Forge.
- If a verification page appears, it returns the same access-block state and
  fails fast after limited retry.

Browser mode can be implemented after static mode has accurate detection and
health-check reporting.

## Error Handling

Use consistent Chinese messages:

- `JavDB 返回 403，后端爬虫会话被拒绝，请在浏览器完成验证后重新导出 Cookie`
- `JavDB 返回 429，请降低并发或延长请求间隔后重试`
- `JavDB 触发安全验证，请刷新 Cookie 或完成浏览器验证`
- `JavDB 页面可访问，但未解析到名称，请检查 URL 类型或页面结构`

Crawler run logs should include enough context to identify the failing phase:

- list page URL and page number
- detail URL and detail index
- status code and access reason

## Testing

Backend tests should cover:

- `detect_access_state` returns blocked for 403.
- `detect_access_state` returns blocked for 429.
- keyword-based verification still works.
- `extract_task_name` raises a clear error for blocked JavDB pages.
- list collection does not treat a blocked empty page as "no data".
- normal JavDB name parsing still works.
- cookie health-check endpoint returns structured blocked and ok responses.

Frontend tests should cover:

- cookie test button calls the API.
- successful test result is rendered.
- blocked test result is rendered with the returned message.
- save-cookie behavior remains unchanged.

## Rollout

1. Implement shared access detection and tests.
2. Wire detection into name extraction, list collection, detail collection, and
   magnet refresh.
3. Add backend cookie health-check endpoint and tests.
4. Add frontend cookie test action and tests.
5. Optionally add browser fetch mode in a separate implementation pass if static
   mode still cannot access JavDB after valid cookies are saved.

## Acceptance Criteria

- A JavDB 403 response never produces a successful empty name.
- A JavDB 403 list page never ends a task as if the page simply had no data.
- A blocked list or detail page logs the access reason and fails after limited
  retry.
- The config page can test whether the backend crawler session can access
  JavDB with saved cookies.
- Normal existing JavDB parsing tests continue to pass.
- No code attempts to solve captchas or extract cookies from Chrome.
