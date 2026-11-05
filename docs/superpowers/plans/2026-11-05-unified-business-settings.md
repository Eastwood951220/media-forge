# Unified Business Settings Implementation Plan

Goal: move existing business settings to application_settings, excluding database/Redis bootstrap and browser-local connection settings.
Architecture: shared SQLAlchemy store with per-key JSON values; existing validated module services and APIs delegate to it; transactional, idempotent legacy import before workers. Explicit file paths remain legacy adapters for import/tests only, never automatic production fallback.
Spec: ../specs/2026-11-05-unified-business-settings-design.md

- [x] Add application_settings model, migration, shared SettingsStore and tests for reads, partial updates and missing-only import.
- [x] Switch storage/scraping/crawler production reads and writes; retain explicit legacy adapters for migration.
- [x] Switch movie query area and cookies (including agent sync and scraper readers).
- [x] Switch backup settings and archive export/restore; preserve old archives and omitted secrets.
- [x] Add startup schema readiness + atomic import before workers; remove storage environment injection; register model in bootstrap/Alembic.
- [x] Expose authenticated unified namespace APIs using existing validators and secret masking.
- [x] Run focused then cross-module tests, inspect integration and commit functional groups.

Parallel boundaries: backup owns backend/app/modules/backup and its tests; cookies/movie_filters owns those domain adapters and tests. Root owns shared store, bootstrap, module config services, unified API and integration. Store contract: shared.settings_store.SettingsStore(session_factory=None), read(namespace)->dict, write(namespace, values, only_missing=False)->None, import_namespaces(mapping)->None. SECRET_KEYS maps namespaces to secret key sets. Default factory is shared.database.session.get_session_factory (resolved at instantiation); no cached results.

Verification: 116 cross-module backend tests passed (before one additional unified/legacy roundtrip regression, which also passed); 7 scraper tests passed; PostgreSQL migration SQL and single Alembic head checked. Three unrelated Docker init address-guard tests fail in unchanged init logic and are excluded from the final affected-area run. Code review found no blocker; namespace-wide concurrent range validation remains as before (per-key updates prevent unrelated field overwrites).
