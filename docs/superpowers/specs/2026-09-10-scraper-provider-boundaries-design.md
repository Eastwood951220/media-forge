# Scraper Provider Boundaries Design

## Context

Media Forge has two related crawler concerns that are beginning to grow:

- Actress profile collection: the API currently starts from a crawler task actor URL, extracts JavDB actor names and aliases, finds a matching avjoho profile, parses the profile, and upserts `ActressProfile`.
- Movie magnet collection: JavDB and JavBus spiders already parse movie details and magnets, but the capability is embedded in each site's spider flow and backend services call concrete spider methods directly.

The current actress profile flow works, but the boundary is wrong for future growth. `backend/app/modules/content/actresses/service.py` owns HTTP fetching, avjoho search parsing, avjoho profile parsing, JavDB actor metadata fetching, candidate building, and database upsert. That mixes site scraping with content business logic.

The existing scraper package already has the better home for site-specific behavior:

- `scraper/spiders/javdb/` owns JavDB parsing and spider behavior.
- `scraper/spiders/javbus/` owns JavBus parsing and spider behavior.
- `scraper/fetchers/site_fetcher.py` builds site-specific fetchers.
- `scraper/spiders/registry.py` maps a source key to a site spider.

This design moves scraper-only concerns into `scraper` while keeping backend modules responsible for API validation, task ownership, persistence, serialization, and realtime/runtime orchestration.

One important transport constraint: avjoho must have its own site configuration. The current `build_site_fetcher` implementation falls back to `JAVDB_SITE` for any source other than `javbus`, so adding `build_site_fetcher("avjoho")` without first adding `AVJOHO_SITE` would send JavDB headers and cookies to `db.avjoho.com`. The migration must add an explicit avjoho branch before backend services use a scraper fetcher for avjoho.

## Goals

1. Make `scraper` the single place for site fetch and parse logic.
2. Keep backend content modules focused on application behavior and persistence.
3. Allow future actress sources beyond avjoho without rewriting the content API.
4. Allow future magnet sources and source-specific magnet refresh behavior beyond the current JavDB implementation.
5. Preserve existing crawler task execution behavior during the first migration phase.
6. Keep each migration phase independently testable and shippable.

## Non-Goals

- Do not redesign the whole crawler runtime in one step.
- Do not change current database schema in the actress provider migration unless a later feature needs new stored fields.
- Do not change the public actress API shape during the provider migration.
- Do not replace existing JavDB Agent mode in this design.
- Do not add new external data sources in the first phase; create boundaries that make them easy to add later.
- Do not merge actress profile data into movie rows.

## Boundary Rules

### Scraper Package Responsibilities

The `scraper` package owns:

- HTTP fetches for external source pages.
- Source-specific URL construction and validation helpers.
- HTML parsing into scraper payload dataclasses or dictionaries.
- Source-specific fallback logic that does not require the application database.
- Site capability methods such as actor metadata extraction, profile lookup, profile fetch, detail fetch, and magnet fetch.

The `scraper` package must not import backend modules. This keeps it usable by backend runtime, scripts, and isolated scraper tests.

### Backend Responsibilities

Backend modules own:

- Authentication and authorization.
- Loading `CrawlTask` and `CrawlTaskUrl` rows.
- Deciding which task URL IDs are allowed for a request.
- Upserting `ActressProfile`, `Movie`, and `MovieMagnet` rows.
- Returning API responses and errors.
- Logging application-specific failures.
- Connecting scraper payloads to local task IDs, run IDs, and task URL IDs.

Backend may import scraper providers and payload types. Scraper must not import backend content services.

## Target Scraper Layout

```text
scraper/
  profiles/
    __init__.py
    actress.py
  magnets/
    __init__.py
    provider.py
  spiders/
    avjoho/
      __init__.py
      avjoho_parser.py
      avjoho_spider.py
    javdb/
      actor_profile.py
      magnet_provider.py
      javdb_parser.py
      javdb_spider.py
    javbus/
      actor_profile.py
      magnet_provider.py
      javbus_parser.py
      javbus_spider.py
```

The exact split can be introduced gradually. Phase 1 only needs `scraper/profiles/actress.py`, `scraper/spiders/avjoho/*`, and `scraper/spiders/javdb/actor_profile.py`.

## Actress Provider Design

### Shared Scraper Payloads

Create source-neutral dataclasses in `scraper/profiles/actress.py`:

- `ActorMetadata`: primary names, aliases, source URL, source site.
- `ActressProfilePayload`: normalized profile fields currently parsed from avjoho.
- `ActressProfileMatch`: matched profile, attempted URLs, candidate names, source names.

These dataclasses contain no SQLAlchemy model and no FastAPI exception.

### JavDB Actor Metadata

Move JavDB actor metadata extraction behind `scraper/spiders/javdb/actor_profile.py`.

Public functions:

- `parse_actor_metadata(page, source_url: str) -> ActorMetadata`
- `fetch_actor_metadata(fetcher, url: str) -> ActorMetadata`

The existing `parse_actor_section_metadata(page)` in `javdb_parser.py` can either delegate to the new parser or remain as a compatibility wrapper. The important part is that backend code stops reaching into generic parser internals for actor profile matching.

### Avjoho Profile Source

Move the current avjoho parser into `scraper/spiders/avjoho/avjoho_parser.py`.

Add `AVJOHO_SITE` to `scraper/config/sites.py` and update `scraper/fetchers/site_fetcher.py` so `build_site_fetcher("avjoho")` uses:

- `base_url`: `https://db.avjoho.com`
- `cookie_file`: `avjoho_cookies.json`
- headers containing a browser `User-Agent`
- no JavDB or JavBus cookies

Create `scraper/spiders/avjoho/avjoho_spider.py` with an `AvjohoActressSpider` that owns:

- Direct profile URL validation for `db.avjoho.com`.
- Candidate URL construction from names.
- Search URL construction and search result extraction.
- HTTP fetch through the injected fetcher.
- Profile fetch and parse.
- Name matching between candidate names and returned profile names.

Public methods:

- `build_direct_profile_urls(names: list[str]) -> list[str]`
- `build_search_names(names: list[str]) -> list[str]`
- `find_profile_urls_by_search(name: str) -> list[str]`
- `fetch_profile(url: str) -> ActressProfilePayload | None`
- `find_first_matching_profile(names: list[str], manual_url: str | None = None) -> ActressProfileMatch`

The spider should return structured failed attempts for automatic candidate 404s or parse misses but should not raise FastAPI exceptions. For a manually supplied URL, invalid host/scheme and fetch-not-found failures must raise scraper-domain exceptions so backend can return a user-visible error instead of `matched=false`.

### Backend Actress Service After Migration

`backend/app/modules/content/actresses/service.py` should become an orchestrator:

1. Load the task and selected `task_url_id`.
2. Verify the URL is a supported actor URL.
3. Use `scraper.spiders.javdb.actor_profile.fetch_actor_metadata`.
4. Build the candidate name list from metadata, task URL name, and task name.
5. Use `AvjohoActressSpider.find_first_matching_profile`.
6. Upsert the returned payload into `ActressProfile`.
7. Return the existing API response structure.

The service should no longer contain raw `urlopen`, avjoho HTML parser code, or avjoho search result parser code.

## Magnet Provider Design

The magnet provider work should happen after the actress provider migration. It should not be mixed into the same implementation batch.

Create a small source-neutral protocol in `scraper/magnets/provider.py`:

- `MovieDetailRequest`: source, detail URL, optional code, optional source task metadata.
- `MovieDetailPayload`: existing movie detail shape plus magnets.
- `MagnetProvider`: protocol with `fetch_detail_with_magnets(request) -> MovieDetailPayload`.

Then adapt site implementations:

- JavDB provider delegates to existing `JavdbSpider.run_single_detail_task` or a smaller parser/fetch method.
- JavBus provider delegates to existing detail fetch plus Ajax magnet fetch.

Backend services such as `backend/app/modules/content/movies/magnet_refresh.py` should depend on the provider factory instead of constructing `JavdbSpider` directly. The threaded crawler runtime can remain unchanged until a later pass because it already uses site spiders for full task execution.

## Phasing

### Phase 1: Actress Scraper Provider Migration

Move current actress scraping and parsing code into scraper modules without changing the public API or database schema. This is the highest-value cleanup and the least risky because tests can compare the same behavior through a new boundary.

### Phase 2: Magnet Provider Boundary

Introduce source-neutral magnet/detail provider interfaces and move direct backend dependency on JavDB magnet refresh behind that boundary. This enables JavBus or other source magnet refresh without touching content service code again.

### Phase 3: Additional Data Sources

After the first two phases, adding a new actress or magnet source should mean creating a provider under `scraper/spiders/<source>/` and registering it in a provider registry. Backend should only receive the normalized payload.

## Error Handling

Scraper providers should raise or return scraper-domain errors:

- `ProfileSourceNotFound`
- `ProfileSourceInvalidUrl`
- `ProfileSourceAccessBlocked`
- `ProfileSourceParseError`
- `MagnetSourceAccessBlocked`
- `MagnetSourceParseError`

Backend catches these and maps them to existing API messages. FastAPI `HTTPException` stays in backend routers/services.

HTTP 404 during automatic avjoho candidate attempts is not an application error by itself; it is a failed candidate. HTTP 404 for a manually supplied avjoho URL should become a user-visible failure.

## Testing Requirements

Scraper tests:

- JavDB actor metadata parses primary names and aliases.
- Avjoho parser extracts current profile fields.
- Avjoho spider direct candidate URLs, search result URLs, manual URL validation, and first-match behavior are unit-tested with fake fetchers.
- JavDB and JavBus magnet provider adapters preserve current magnet payload shape.

Backend tests:

- Actress fetch endpoint behavior stays stable after scraper migration.
- Backend service no longer needs network monkeypatches on private avjoho functions; tests monkeypatch provider factory or fake provider methods.
- Magnet refresh can select a provider based on movie/source metadata or explicit request source.

Verification commands:

- `python -m pytest scraper/tests/test_javdb_actor_metadata.py scraper/tests/test_avjoho_spider.py -q`
- `python -m pytest backend/tests/test_content_actresses_api.py -q`
- `python -m pytest backend/tests/test_content_movies_api.py -q`
- `python -m pytest scraper/tests/test_javbus_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py -q`

## Acceptance Criteria

- No backend content actress module contains raw external HTML parsing.
- No backend content actress module calls `urlopen` directly.
- Adding a second actress profile source requires adding scraper provider code and a registry entry, not changing upsert logic.
- Existing actress API and frontend behavior continue to pass.
- Magnet refresh has a provider boundary before adding JavBus or other source-specific magnet refresh.
