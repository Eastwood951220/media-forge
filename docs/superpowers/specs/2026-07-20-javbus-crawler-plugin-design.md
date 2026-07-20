# JavBus Crawler Plugin Refactor Design

Date: 2026-07-20  
Status: Approved for specification review  
Branch: `codex/javbus-crawler-plugin-refactor`

## Goal

Add JavBus crawling to Media Forge while preserving existing JavDB behavior. A crawl task URL must be classified as JavDB or JavBus at creation time. One task may contain URLs from both sites. JavBus list URLs must crawl until the site has no next page and must not use the configured maximum list page count.

JavBus detail pages expose magnet links through a follow-up Ajax request. The crawler must request that endpoint, persist every parsed magnet, and let the existing magnet persistence model select the best magnet automatically.

## Scope

This change covers the current crawler task creation flow, crawler runtime, JavDB spider migration to a site plugin interface, JavBus list/detail parsing, magnet persistence, and focused backend, scraper, and frontend tests. It does not add new sites, redesign the crawler UI, or change the existing magnet ranking policy.

## Confirmed Decisions

- Use a site plugin/interface architecture rather than a one-off URL router.
- Support JavBus list URLs and detail-page URLs.
- Allow JavDB and JavBus URLs in the same crawler task.
- Keep all parsed magnets; do not discard lower-ranked magnets in the spider.
- Reuse the existing persistence and `auto_select_best_magnet` behavior.
- JavDB continues to honor `MAX_LIST_PAGES`, incremental mode, existing-item checks, and current filtering/sorting behavior.
- JavBus ignores `MAX_LIST_PAGES` and uses its own list pagination link.
- Backend source detection is authoritative; frontend detection is for validation and presentation.

## Plugin Architecture

Introduce a small crawler site contract implemented by JavDB and JavBus adapters. The contract should expose the operations the runtime currently needs:

1. Collect detail tasks from one `CrawlTaskUrlEntry`.
2. Execute one detail task and return the normalized crawler item.
3. Extract a display name for a task URL where the site supports it.

The runtime owns scheduling, task/run state transitions, concurrency, logging, and result persistence. A source registry maps the normalized source name (`javdb` or `javbus`) to its plugin. The list phase resolves each input URL through that registry, so mixed-source tasks are handled independently. The detail phase resolves the plugin from the detail task's source metadata and does not assume JavDB.

The existing JavDB spider becomes the JavDB plugin implementation with its behavior preserved. Shared URL/source helpers and normalized task metadata should be used instead of duplicating source dispatch logic. If the current detail-task schema cannot carry a stable source field, make the smallest compatible schema change; retaining source metadata in the existing task item payload is acceptable when it preserves persistence and retry behavior without a migration.

## URL Detection and Normalization

Recognize these hosts case-insensitively:

| Host | Source |
| --- | --- |
| `javdb.com` and its subdomains | `javdb` |
| `javbus.com`, `www.javbus.com` | `javbus` |

Unknown hosts must be rejected during task URL creation with a client error rather than entering the runtime as an unsupported source.

JavDB final URLs keep the existing `page=1`, filter, and sort parameter rules. JavBus final URLs are normalized versions of the original URL and must not receive JavDB-only parameters such as `page=1`, `sort_type`, or JavDB filters. The frontend must hide or disable JavDB-specific controls for JavBus entries and must not display a misleading JavDB-style preview.

The backend remains the source of truth if frontend and backend classification differ. Source values must be persisted with the task URL entry and propagated to detail tasks.

## JavBus List and Detail Flow

For a JavBus list URL:

1. Request the current page.
2. Parse each `div.item a.movie-box` into a detail task, including the absolute detail URL, title, and code where available.
3. Parse `a#next` and follow it while a valid next URL exists.
4. Stop normally when there is no next URL, when a request fails, or when incremental mode reaches the existing-item threshold.

For a JavBus detail URL, create one detail task directly. If a code can be parsed from the URL or page metadata, perform the normal existing-item check. A missing code does not prevent a detail crawl, but it cannot participate in code-based deduplication.

JavBus list collection must not read or apply `MAX_LIST_PAGES`. JavDB list collection retains its current page limit and incremental behavior.

## JavBus Detail Parsing

Parse the fields available on the JavBus detail page and map them into the normalized movie item:

| JavBus field | Normalized field |
| --- | --- |
| `識別碼` | `code` |
| detail title / `screencap img[title]` | `title` / `source_name` |
| `發行日期` | `release_date` |
| `長度` | `duration` |
| `導演` | `director` |
| `發行商` | `maker` |
| `系列` | `series` |
| `類別` | `tags` |
| `演員` | `actors` |
| cover/screencap image | `cover_url` |

Fields absent from JavBus, including JavDB-specific rating data, are optional and must not cause the item to fail validation. Existing pipeline normalization and tag enrichment remain the final normalization layer.

## Magnet Ajax Flow

The detail page scripts must provide `gid`, `uc`, and `img`. Use those values to request:

`https://www.javbus.com/ajax/uncledatoolsbyajax.php?gid={gid}&lang=zh&img={img}&uc={uc}&floor=735`

Parse every magnet row from the Ajax response. For each row, retain the magnet URL, display name, size, file count when available, date, row tags, and the Chinese-subtitle marker when tags contain `中字` or `字幕`. Store the resulting list in the normalized `magnets` field. The spider must not select only one magnet; persistence continues to calculate and store the best magnet according to the existing ranking policy.

## Runtime and Persistence

The threaded runtime must obtain plugins from the source registry for both list and detail phases. A failure while collecting one URL must be recorded against that URL and must not abort other URLs in a mixed-source task. A failure while processing one detail task must mark that detail task as `crawl_failed` and allow the run to continue according to existing runtime semantics.

Existing movie validation and magnet persistence remain in force. JavBus items may be accepted when they have `source_name`, `code`, or `source_url`, and may omit fields unavailable from the site. Existing deduplication, retry, run progress, and database upsert behavior should remain unchanged except for carrying the source correctly.

## Error Handling

- Unknown source at task creation: reject with HTTP 400.
- JavBus list page request or parse failure: log the URL and mark its collection failure; continue other task URLs.
- Missing `gid`, `uc`, or `img`: mark the affected detail task failed with an actionable log entry.
- JavBus Ajax request failure or malformed response: mark only the affected detail task failed.
- No magnets: keep the item parseable when other required data is present; do not invent a magnet.
- No next-page link: treat as normal list completion.
- Incremental mode: use code existence checks and threshold behavior consistent with JavDB.

## Test and Verification Plan

Add focused coverage for:

- source detection, supported hosts, unknown-host rejection, and final URL normalization;
- JavBus list parsing, next-page traversal, detail URL handling, field mapping, and Ajax parsing of multiple magnets;
- runtime registry dispatch for mixed JavDB/JavBus tasks, with `MAX_LIST_PAGES` applied only to JavDB;
- source propagation into detail tasks and persistence;
- frontend URL recognition, JavBus control visibility, and final URL preview behavior.

Run the relevant backend pytest modules, scraper parser/runtime tests, and frontend Vitest tests. Run the frontend build when frontend code changes. Verification must also confirm that all parsed magnets reach persistence and that the existing automatic best-magnet selection still passes its current tests.

## Compatibility

Existing JavDB URLs, task payloads, crawler configuration, detail parsing, and magnet ranking must remain backward compatible. The new source value defaults to JavDB only for legacy persisted entries that already point to JavDB; unsupported or ambiguous new URLs must be rejected rather than silently treated as JavDB.
