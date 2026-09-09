# Actress Profile Content Design

## Context

Media Forge currently has a content movie list, and movie rows store actress names as array values on `Movie.actors`. There is no persistent actress profile entity or actress list page.

Crawler task URLs already carry a `url_type`. JavDB actor URLs are recognized as `actors`, and the task list can already run a full task, run selected URLs, and jump to movies filtered by task. The requested first version should add a task-card action that is available only when a task has at least one actor URL, fetch actress profile data from `https://db.avjoho.com/`, and show saved profiles in content management.

The pasted avjoho sample page uses stable content areas:

- `h1.entry-title` for display name and kana in parentheses.
- `.gazou img` for the main image.
- `.profile`, `.birthplace`, `.blood-type`, `.shumi-tokugi`, `.name`, `.maker`, and `.sns` table rows for profile fields.
- `.profile2` for a short biography.
- `h2` with following links for representative works.
- `.yarpp-thumbnail` blocks for similar actresses.

JavDB actor listing pages provide matching candidates:

- `.actor-section-name` can contain one or more comma-separated primary names.
- `.section-meta` can contain aliases or a movie count such as `339 部影片`; movie-count meta values must be ignored.
- Existing task `name` and `url_name` values are additional fallback candidates.

## Goals

1. Add a persistent actress profile content entity.
2. Add content management navigation, a `/content/actresses` card list page, and a standalone actress detail page.
3. Add a task-card action that is available only for tasks containing `actors` task URLs.
4. Implement one-click actress data fetching with automatic avjoho matching.
5. Use JavDB actor names and aliases as avjoho matching candidates.
6. Fall back to manual avjoho URL input when automatic matching fails.
7. Make the fetch idempotent: fetching the same actress again updates the existing profile instead of creating duplicates.

## Non-Goals

- Do not add batch syncing across multiple tasks in the first version.
- Do not add a full actress detail editor in the first version.
- Do not change movie crawl execution semantics.
- Do not write actress profile data back into existing movie rows.
- Do not add storage integration for actress images; store the remote image URL.
- Do not expand support beyond JavDB actor task URLs and avjoho profile pages.

## Design

### Data Model

Add a shared database model such as `ActressProfile` in `shared.database.models.content`.

Recommended columns:

- `id`
- `display_name`
- `reading`
- `aliases`
- `canonical_names`
- `source_url`
- `source_site`
- `source_task_ids`
- `source_task_url_ids`
- `image_url`
- `debut_date`
- `birth_date`
- `height_cm`
- `bust_cm`
- `waist_cm`
- `hip_cm`
- `cup`
- `birthplace`
- `blood_type`
- `hobbies`
- `biography`
- `exclusive_maker`
- `sns_links`
- `representative_works`
- `similar_actresses`
- `raw_profile`
- `last_fetched_at`
- timestamps

Use array or JSON-compatible types through existing shared helpers where appropriate. `aliases`, `canonical_names`, and source ID lists should stay queryable enough for list search and dedupe. Complex page-derived structures such as SNS links, works, similar actresses, and raw parsed fields can live in JSON.

Add indexes on `display_name`, `source_url`, `source_task_ids`, and a GIN-style index for aliases/canonical names where supported. Put table creation and table modification statements in a versioned SQL script under `sql/`, and add the matching Alembic migration automatically so application migrations stay current.

### JavDB Candidate Extraction

Extend JavDB parser support with an actor-section metadata parser. It should accept the fetched actor page and return:

- `primary_names`: split `.actor-section-name` by comma, trim, and preserve order.
- `aliases`: collect `.section-meta` text values, split comma-separated aliases, trim, and discard values matching movie-count text such as `1928 部影片`.

The existing `parse_page_section_name` behavior can keep returning the first primary name for task naming. The new parser should be separate so task-name extraction remains stable.

### Avjoho Fetch and Parse

Create a content actress service module under `backend/app/modules/content/actresses/`.

The fetch flow for a task:

1. Load the owned task.
2. Select task URLs where `url_type == "actors"`.
3. For each actor URL, fetch the JavDB page with the existing site fetcher.
4. Extract candidate names from JavDB primary names, aliases, task URL `url_name`, and task name.
5. If the request includes a manual avjoho URL, try that URL first.
6. Otherwise try `https://db.avjoho.com/{url-encoded-candidate}/` for each candidate.
7. Treat a page as matched only when the avjoho parser finds a valid profile title and profile content.
8. Upsert the saved actress profile.

The avjoho parser should extract the fields shown in the sample and keep the raw table values in `raw_profile`. Dates can be normalized when parsing is unambiguous; otherwise preserve the raw text and leave normalized date fields empty. Measurements should parse numeric centimeters from strings like `B90cm W62cm H93cm`.

### Upsert and Deduping

Deduplicate primarily by normalized `source_url` when present. If an existing profile has no source URL match, look for overlap between candidate names and existing `display_name`, `aliases`, or `canonical_names`.

On update:

- Replace fields derived from the current avjoho source page.
- Merge aliases and canonical names without duplicates.
- Merge source task IDs and source task URL IDs without duplicates.
- Refresh `last_fetched_at`.

This supports repeated one-click fetches and lets aliases improve future matching.

### API

Add a router prefix:

`/api/content/actresses`

Endpoints:

- `GET ""`: paginated list with `page`, `limit`, `keyword`, and optional `source_task_id`.
- `POST "/fetch-from-task"`: body includes `task_id` and optional `avjoho_url`. Returns the saved profile and matching metadata.

The fetch endpoint should return a structured result:

- `profile`
- `matched_candidate`
- `attempted_candidates`
- `used_manual_url`

If no profile is found automatically, return a 404-style application error with attempted candidates so the frontend can open the manual URL prompt.

### Frontend

Add a content actress API module under `frontend/src/api/content/actresses`.

Add routes and a menu entry:

- Route: `/content/actresses`
- Detail route: `/content/actresses/$id`
- Tag title: `女优列表`
- Sidebar item under content management: `女优列表`

The list page should use a card grid rather than a table. It should follow the existing content-management density where practical: compact toolbar, keyword search, card results, and pagination. Pagination page sizes must be multiples of 8, with a default of 24 and selectable sizes of 8, 16, 24, and 40. First-version card content:

- image
- name
- alias summary
- debut date
- birth date
- body metrics
- birthplace
- exclusive maker
- last fetched time

Clicking a card opens the standalone detail route `/content/actresses/$id`. The detail page should show the complete saved avjoho profile:

- image
- display name and reading
- aliases and canonical names
- debut date
- birth date
- height and measurements
- cup
- birthplace
- blood type
- hobbies
- biography
- exclusive maker
- SNS links
- representative works
- similar actresses
- source URL
- last fetched time

The detail page should also include a `最近影片` section. It queries local `Movie` rows through the actress profile's associated `source_task_ids` and `source_task_url_ids`, not by actress name matching. Because `Movie` stores `source_task_ids` but does not directly store task URL IDs, use `source_task_url_ids` to load `crawl_task_urls.url`, then find `crawl_run_detail_tasks` with matching `task_url`, matching parent crawl run `task_id`, and non-empty `movie_id`. Sort matched movies by `release_date` descending with missing dates last, and return 10 rows. Each movie item shows cover image, `code`, and title. The first version does not need to add a new movie detail route; movie cards can link to the existing movie source URL when available or stay non-navigating when no URL exists.

Add a task-card action such as `获取女优资料`. It should render only when the task has at least one URL whose `url_type` is `actors`; disabled state should follow the same runtime readiness and idle checks as other fetch-like actions.

Interaction flow:

1. User clicks `获取女优资料`.
2. Frontend calls `POST /api/content/actresses/fetch-from-task` with `task_id`.
3. On success, show a success message and invalidate actress list queries.
4. If automatic matching fails, open a modal with one URL input for avjoho URL.
5. Submitting the modal retries the same endpoint with `avjoho_url`.
6. On success, offer navigation to `/content/actresses`.

### Error Handling

- Return 404 when the task does not exist or is not owned by the current user.
- Return 400 when the task has no `actors` URLs.
- Return 400 when a manual avjoho URL is not an HTTP(S) URL on `db.avjoho.com`.
- Return a not-found error when automatic candidate attempts find no parseable profile.
- Surface JavDB access-state failures with the existing access guard message where possible.
- For each actor task URL, stop after the first successful avjoho profile match. If at least one profile is saved and another actor task URL fails, include that failure in the response metadata instead of failing the whole request.

## Testing

Backend:

- Add JavDB parser tests for actor primary names and aliases, including comma-separated Chinese/Japanese names and movie-count filtering.
- Add avjoho parser tests using the pasted sample HTML for profile fields, SNS links, representative works, and similar actresses.
- Add service tests for automatic candidate ordering, manual URL validation, source URL dedupe, alias dedupe, task URL ID based recent movie lookup, and task ownership/no-actor rejection.
- Add router tests for list pagination and fetch-from-task responses.

Frontend:

- Add task-card tests proving `获取女优资料` appears only for actor tasks and calls the handler.
- Add page/API tests for actress list rendering and query params.
- Add fetch interaction tests covering automatic success and automatic failure followed by manual URL retry.

Verification commands:

- `cd backend && python -m pytest tests/ -v` or focused content/crawler tests when practical.
- `python -m pytest scraper/tests -v` for parser changes that live under `scraper/`.
- `cd frontend && pnpm test -- <focused test files>` for focused UI coverage.
- `cd frontend && pnpm build` for frontend type and build verification.
