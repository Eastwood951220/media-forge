# JavDB Browser Fetch Mode Design

Date: 2026-08-10

## Context

The current JavDB access guard correctly reports blocked backend access. After
exporting fresh cookies from Chrome, the backend cookie test can still return:

`JavDB 返回 403，后端爬虫会话被拒绝，请在浏览器完成验证后重新导出 Cookie`

This means the saved cookies are not enough for static HTTP fetching. JavDB can
allow the user's real Chrome session while rejecting backend requests because of
browser fingerprinting, TLS/client impersonation differences, JavaScript
execution, request headers, or session binding.

The next change should therefore add a real browser-backed fetch mode that works
both in local development and inside the project's Docker image.

## Goals

- Add a JavDB browser fetch mode for cases where static HTTP returns 403 with
  otherwise fresh cookies.
- Keep static HTTP as the default mode because it is faster and simpler when it
  works.
- Reuse the existing JavDB parsers by returning parser-compatible page content
  from browser-loaded pages.
- Use only cookies explicitly saved through Media Forge.
- Support Docker single-container runtime for amd64 and arm64 builds.
- Keep the existing access guard behavior: blocked pages fail clearly instead
  of producing empty names, empty lists, or empty detail results.

## Non-Goals

- Do not solve captchas or bypass human verification.
- Do not read cookies directly from Chrome profiles.
- Do not require connecting to the user's live Chrome browser or CDP endpoint.
- Do not replace existing JavDB parsers.
- Do not make JavBus use browser mode.
- Do not add new product features beyond fetch mode selection and diagnostics.

## Recommended Approach

Implement `JAVDB_FETCH_MODE=static | browser`.

Default: `static`.

When mode is `browser`, JavDB requests use a headless Chromium browser in the
backend process. The browser context is initialized from the saved
`data/cookies/javdb_cookies.json` browser-export cookie array. After navigation
and page load, the HTML is converted into a Scrapling parser `Adaptor` or an
equivalent parser-compatible object, with status metadata attached so the
existing access detector still works.

The first implementation should prefer Scrapling `DynamicFetcher` if it can
reliably accept the saved cookie array and return parser-compatible content. If
that is not sufficient, use Playwright directly behind the same local
`ScraplingFetcher` interface. The public crawler/spider code should not depend
on the browser implementation details.

## Architecture

### Runtime Configuration

Extend crawler config with:

- `JAVDB_FETCH_MODE`: `static` or `browser`

Validation rules:

- Missing or invalid value falls back to `static`.
- The config endpoint exposes and persists the value alongside the existing
  crawler settings.
- UI displays this as a controlled option, not free-form text.

### Site Fetch Mode Selection

Only JavDB should use `JAVDB_FETCH_MODE`.

JavBus remains static because it has separate behavior and existing fallbacks.

Current spider builders should change from:

```python
fetcher = ScraplingFetcher(headers=site_config["headers"], cookies=cookies, timeout=...)
```

to a centralized helper, for example:

```python
fetcher = build_site_fetcher(source, runtime_config)
```

That helper owns:

- selecting JavDB static/browser mode
- loading the right cookie representation
- applying site headers and timeout
- keeping JavBus unchanged

Call sites to route through the helper:

- crawler runtime engine
- threaded crawler runtime
- task name extraction
- magnet refresh

### Cookie Loading

The existing `CookieManager.load()` returns a flat `name -> value` dict. Static
HTTP should keep using that shape.

Browser mode needs the full browser-export cookie array. Add a focused method:

- `CookieManager.load_browser_cookies() -> list[dict]`

This method should:

- return `[]` when the file is missing or invalid
- preserve the cookie metadata needed by browser contexts
- ignore invalid rows without failing the entire load
- avoid logging cookie values

Cookie conversion for browser mode:

- `expirationDate` maps to Playwright/Scrapling `expires`
- `httpOnly` keeps camel-case `httpOnly`
- `sameSite` maps case-insensitively:
  - `lax` -> `Lax`
  - `strict` -> `Strict`
  - `no_restriction` or `none` -> `None`
- `domain`, `path`, `secure`, `name`, and `value` are preserved
- host-only cookies keep their domain from the export

### Browser Fetcher

Add a focused browser-backed implementation behind the existing fetcher boundary.

Preferred shape:

```python
ScraplingFetcher(
    headers=...,
    cookies=flat_cookies,
    browser_cookies=browser_cookie_rows,
    timeout=...,
    dynamic=True,
)
```

In dynamic mode:

- pass converted cookies into the browser context
- pass extra headers
- run headless by default
- wait for DOM content and a short network idle/window where practical
- attach best-effort `status_code` to the returned parser object
- return content compatible with existing `.css()` parser calls

If Scrapling `DynamicFetcher` cannot reliably provide status or parser
compatibility, implement a local Playwright path inside `ScraplingFetcher`:

1. launch Chromium headless
2. create context with locale and extra headers
3. add cookies
4. navigate to URL
5. read HTTP response status
6. read page content
7. close the browser/context
8. wrap HTML using `scrapling.parser.Adaptor`
9. attach `status_code`

The browser lifecycle should be simple for the first implementation: launch per
request. This is slower but avoids shared browser lifetime bugs in crawler
threads. Reuse/pooling can be considered later if performance becomes a problem.

### Static Fetcher Enhancement

Static mode can add low-risk browser impersonation:

- pass `impersonate="chrome"` or the closest supported Chrome impersonation
  value to `Fetcher.get`

This is not expected to solve all 403 cases, but it is a safe improvement for
static mode.

### Cookie Health Check

The existing `/api/crawler/config/cookies/test` endpoint should test with the
current fetch mode.

Response should add:

- `fetch_mode`: `static` or `browser`

Message behavior:

- static 403: suggest switching to browser mode
- browser 403/security page: suggest completing verification in real Chrome and
  exporting cookies again
- browser runtime unavailable: explain that Chromium/Playwright is not installed
  or failed to launch

### Frontend

Update `/crawler/config`:

- add a `JAVDB_FETCH_MODE` segmented control or select
- options:
  - `static`: "静态请求"
  - `browser`: "浏览器模式"
- keep mode near the cookie test controls because the test result depends on it
- show `fetch_mode` in the cookie test result

Do not show raw cookie values outside the existing JSON editor.

### Docker Support

The Docker runtime image must include browser mode dependencies.

Implementation options:

1. Use Playwright's install commands inside the Python runtime image:
   - install Python dependencies
   - run `python -m playwright install --with-deps chromium`

2. Or explicitly install Debian Chromium packages and configure Playwright to use
   the system executable.

Use option 1 unless image build reliability forces option 2. It is clearer and
keeps browser dependency management aligned with the installed Playwright
package.

Docker requirements:

- browser mode works in the single runtime container
- `/app/data` remains the only required persistent volume
- saved cookies still live in `/app/data/cookies/javdb_cookies.json`
- amd64 and arm64 build targets remain supported

Image size increase is acceptable for this feature.

### Concurrency And Performance

Browser mode is slower and heavier than static mode.

Initial constraints:

- keep browser mode compatible with existing crawler concurrency settings
- document that users should reduce `LIST_MAX_WORKERS` and `DETAIL_MAX_WORKERS`
  if the host lacks memory
- no browser pooling in the first implementation
- access guard retry limits remain unchanged

### Error Handling

Use clear Chinese messages:

- static 403:
  `JavDB static 模式返回 403，请切换浏览器模式后重试`
- browser missing:
  `浏览器模式不可用，Chromium/Playwright 未正确安装或启动失败`
- browser verification:
  `JavDB 浏览器模式仍触发安全验证，请在浏览器完成验证后重新导出 Cookie`
- browser timeout:
  `JavDB 浏览器模式加载超时，请稍后重试或降低并发`

Do not include cookie values in logs or error messages.

## Testing

Backend tests should cover:

- `CookieManager.load_browser_cookies()` preserves browser-export cookie fields.
- cookie conversion maps `sameSite` and `expirationDate` correctly.
- static fetcher passes impersonation options.
- browser fetcher passes browser cookies into dynamic/browser loading.
- site fetcher builder uses browser mode only for JavDB.
- config reader validates `JAVDB_FETCH_MODE`.
- cookie test endpoint returns `fetch_mode`.
- browser runtime failure returns a structured blocked/unavailable response.

Frontend tests should cover:

- fetch mode field renders in crawler config.
- changing fetch mode saves `JAVDB_FETCH_MODE`.
- cookie test displays returned `fetch_mode`.
- existing cookie save/test behavior still works.

Docker verification should cover:

- `make docker-build-amd64` completes.
- `make docker-build-arm64` completes when the builder supports arm64.
- container starts and health check passes.
- browser mode smoke test can launch Chromium in the container.

## Rollout

1. Add config and cookie-loading primitives.
2. Add browser-capable fetcher behind the existing fetcher boundary.
3. Centralize site fetcher construction and wire JavDB browser mode into all
   JavDB entry points.
4. Extend cookie health check response and UI.
5. Update Dockerfile to install browser runtime dependencies.
6. Run backend, frontend, and Docker verification.

## Acceptance Criteria

- Users can choose `static` or `browser` mode for JavDB.
- Static mode remains the default.
- Cookie test reports which fetch mode was used.
- Browser mode uses saved cookie JSON and does not read Chrome profile cookies.
- Browser mode works inside the Docker runtime image.
- Existing JavDB parsers continue to be reused.
- A 403/security page in either mode is reported clearly and does not create
  false success.
- No code solves captchas or bypasses verification.
