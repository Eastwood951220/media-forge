# JavDB Persistent Browser Session Design

Date: 2026-08-10

## Context

Media Forge already has a JavDB access guard and a browser fetch mode, but the
current browser mode still fails with:

`JavDB 浏览器模式仍触发安全验证，请在浏览器完成验证后重新导出 Cookie`

The current implementation starts a fresh headless Chromium instance for each
browser-mode request, creates a new browser context, injects exported cookies,
loads the page, reads the HTML, and closes the browser. This is not enough for
JavDB/Cloudflare-style verification because the accepted session can depend on a
continuous browser profile, local storage, browser cache, challenge state,
client environment, IP reputation, and request rate.

The next change should replace the one-off browser request model with a
persistent Playwright browser profile and a first-class verification workflow in
Media Forge. The design must work well in local development and remain usable
when the application runs in Docker on fnOS/Feiniu NAS.

## Goals

- Upgrade JavDB `browser` mode from one-off headless requests to a persistent
  Playwright Chromium profile.
- Let the user establish JavDB verification state from Media Forge instead of
  repeatedly exporting cookies from an external browser.
- Keep the existing JavDB spider, parser, pipeline, and run result behavior
  unless they need access-state integration.
- Support local development first, where the backend can open a headed
  Chromium window for verification.
- Support Docker/fnOS by storing browser state under the existing persistent
  `data/` volume so it can be copied, mounted, backed up, or reused.
- Make browser-mode failures actionable by distinguishing missing profile,
  expired profile, blocked profile, browser launch failure, timeout, 403, 429,
  and generic security challenge states.
- Reduce JavDB browser-mode traffic risk by serializing same-process browser
  fetches.

## Non-Goals

- Do not solve captchas or bypass human verification automatically.
- Do not scrape cookies from the user's personal Chrome profile.
- Do not add a noVNC or remote-browser gateway in the first implementation.
- Do not replace Scrapling parsing or JavDB parser logic.
- Do not add unrelated crawler features beyond the JavDB access/session flow.
- Do not make JavBus use the JavDB persistent browser session.

## Recommended Approach

Keep `JAVDB_FETCH_MODE=static | browser`.

Default remains `static`.

When mode is `browser`, JavDB fetches use a dedicated persistent browser session
backed by:

```text
data/browser-profiles/javdb/
```

This directory is the Playwright Chromium `user_data_dir`. It becomes the
primary source of browser state. The existing cookie JSON remains supported as a
compatibility and diagnostic input, but browser mode should no longer rely on
cookie injection alone.

Add a JavDB session service with APIs for:

- opening a headed verification browser when the runtime supports it
- closing the verification browser
- checking whether the current profile can access JavDB
- exporting Playwright storage state for backup or Docker diagnostics
- clearing a stale profile when the user chooses to reset it

The first implementation should avoid a remote GUI stack. For Docker/fnOS, the
supported path is:

1. complete verification in a local environment that can show Chromium
2. persist `data/browser-profiles/javdb/`
3. mount or copy that directory into the fnOS Docker volume
4. run browser mode with headless Chromium using the same profile

If the profile is rejected in Docker because the IP or environment changed,
Media Forge should report that the profile is expired or blocked and ask the
user to verify from the target runtime or refresh the mounted profile.

## Architecture

### Browser Session Manager

Add a focused module, for example:

```text
scraper/fetchers/javdb_browser_session.py
```

Responsibilities:

- own Playwright startup and shutdown
- calculate profile and storage-state paths
- launch persistent Chromium contexts
- expose `fetch(url, headers=None, timeout=...)`
- expose verification/session operations used by the config API
- serialize browser-mode JavDB fetches through a process-level lock
- convert page HTML to `scrapling.parser.Adaptor`
- attach response status metadata used by `scraper.core.security`

Suggested paths:

```text
data/browser-profiles/javdb/
data/cookies/javdb_storage_state.json
```

`data/browser-profiles/javdb/` is the main state. `javdb_storage_state.json` is
secondary and should be used for export, inspection, and compatibility, not as
the only source of truth.

### Fetcher Boundary

Keep `ScraplingFetcher` as the existing public fetcher boundary. Its behavior
should become:

- static mode: keep using `Fetcher.get(..., impersonate="chrome")`
- browser mode: delegate to `JavDBBrowserSession.fetch(...)`

`ScraplingFetcher` should not contain the detailed persistent-context lifecycle.
That keeps the existing call sites stable while giving browser state a clearer
owner.

`site_fetcher.build_site_fetcher()` remains the central entry point for source
mode selection. Only JavDB uses the persistent browser session.

### Verification APIs

Add endpoints under crawler config:

```text
GET  /api/crawler/config/javdb-session
POST /api/crawler/config/javdb-session/open
POST /api/crawler/config/javdb-session/close
POST /api/crawler/config/javdb-session/check
POST /api/crawler/config/javdb-session/export
DELETE /api/crawler/config/javdb-session
```

`GET /javdb-session` returns persisted and live status:

- `profile_exists`
- `storage_state_exists`
- `verification_browser_open`
- `last_check_at`
- `last_check_url`
- `last_status_code`
- `last_reason`
- `last_message`
- `logged_in_detected`
- `runtime_environment`

`POST /open` opens a headed persistent Chromium window when possible. It should
return a clear unsupported-environment response if the backend is headless and
cannot show a browser.

`POST /check` loads JavDB with the persistent profile and reports access state.

`POST /export` writes `data/cookies/javdb_storage_state.json` from the current
profile.

`DELETE /javdb-session` clears the profile and exported storage state after the
user explicitly requests reset.

### Runtime Environment Handling

The session service should classify runtime capability in a simple way:

- local GUI available: headed verification can open
- headless Docker/server: headed verification unavailable
- unknown: attempt to open and report launch errors clearly

The first implementation does not need to detect every OS/display variant. It
only needs deterministic user-facing responses and safe fallback behavior.

Docker/fnOS must persist:

```text
/app/data/browser-profiles/javdb
/app/data/cookies/javdb_storage_state.json
```

The README should document:

- mount `./data:/app/data`
- set `shm_size: "2gb"`
- keep browser mode concurrency low
- if profile works locally but fails on fnOS, re-verification may be required
  because the IP and browser environment changed

### Access State Reasons

Extend access/session reporting with these reasons:

```text
ok
no_browser_profile
profile_not_verified
profile_expired_or_blocked
browser_unavailable
browser_timeout
http_403
http_429
security_challenge
fetch_error
```

Mapping rules:

- no profile directory: `no_browser_profile`
- profile exists but a normal JavDB page is not detected: `profile_not_verified`
- browser mode returns 403 after using a profile: `profile_expired_or_blocked`
- Playwright launch failure: `browser_unavailable`
- navigation timeout: `browser_timeout`
- 429: `http_429`
- security keywords without 403/429: `security_challenge`
- successful normal page: `ok`

Update `/api/crawler/config/cookies/test` so browser mode no longer says
"重新导出 Cookie" as the primary action. Browser-mode failures should point the
user to the JavDB session workflow.

### Concurrency

JavDB browser mode should use a process-level lock. Only one JavDB browser fetch
may run at a time in the backend process.

Reasons:

- the persistent profile directory cannot be used by multiple Chromium
  instances at the same time
- concurrent browser contexts increase access-pattern risk
- current user configuration may set `LIST_MAX_WORKERS` and
  `DETAIL_MAX_WORKERS` above 1

The config UI may still allow worker values above 1 for static mode and other
sources, but it should show a warning when JavDB browser mode is active:

`JavDB 浏览器模式会自动串行访问，以降低安全验证触发概率。`

For browser mode, repeated 403 should fail fast after the first confirmed
profile-blocked result. Waiting through five long retries adds load and delays
feedback without improving the session state.

### Frontend

Update `/crawler/config` so the right side is a JavDB access panel instead of
only a cookie editor.

Add a session status area:

- current fetch mode
- profile status
- last check time
- last status code and reason
- last checked URL
- logged-in detection
- runtime environment

Add actions:

- open verification browser
- close verification browser
- check session
- export session state
- clear stale session

Keep the Cookie JSON editor for compatibility and fallback, but describe it as
secondary to the persistent browser session when `browser` mode is selected.

The cookie test alert should display profile-related reasons in browser mode and
should not imply that re-exporting Cookie JSON is the only fix.

### Docker/fnOS Deployment

The existing Docker image already includes Playwright/Chromium runtime work from
the previous browser-mode change. This design adds operational requirements:

```yaml
services:
  media-forge:
    volumes:
      - ./data:/app/data
    shm_size: "2gb"
```

The first version should not bundle noVNC. If the container has no GUI, the UI
should explain that the user must prepare the profile locally and mount/copy it
to the container.

Future work can add a remote verification surface, but that should be a
separate design because it introduces network exposure, browser lifecycle, and
access-control concerns.

## Testing

Backend tests:

- session manager resolves profile and storage-state paths under `data/`
- missing profile returns `no_browser_profile`
- Playwright launch failure maps to `browser_unavailable`
- Playwright timeout maps to `browser_timeout`
- browser-mode 403 with a profile maps to `profile_expired_or_blocked`
- storage state export writes the configured path
- browser fetch returns an adaptor with status metadata
- browser fetches are serialized by the process-level lock
- JavBus still uses static mode

Config API tests:

- session status endpoint reports profile and storage-state presence
- open endpoint returns unsupported-environment cleanly in headless mode
- close endpoint is idempotent
- check endpoint returns detailed access reasons
- export endpoint writes `javdb_storage_state.json`
- reset endpoint removes profile and storage-state files only
- `/cookies/test` keeps static-mode behavior
- `/cookies/test` reports profile/session guidance in browser mode

Frontend tests:

- config page shows JavDB session status
- browser mode displays session workflow actions
- static mode keeps Cookie JSON workflow usable
- check/open/export/clear buttons handle loading and disabled states
- browser-mode failed check displays profile-related guidance

Documentation:

- README documents local verification
- README documents Docker/fnOS profile mounting
- README documents `shm_size: "2gb"`
- README documents browser-mode serialization
- README states that profile portability is not guaranteed across IP/runtime
  changes

## Acceptance Criteria

- A local developer can open a JavDB verification browser from Media Forge,
  complete verification, close the browser, and then pass session check without
  manually exporting Cookie JSON.
- JavDB `browser` mode uses the persistent profile for list and detail fetches.
- Browser-mode JavDB fetches are serialized in one backend process.
- Docker/fnOS users can persist and mount `data/browser-profiles/javdb/`.
- Browser-mode 403 errors report profile/session guidance instead of only
  telling the user to re-export cookies.
- Existing static mode and JavBus behavior remain compatible.
