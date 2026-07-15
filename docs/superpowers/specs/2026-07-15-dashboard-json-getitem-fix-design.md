# Dashboard JSON Getitem Fix Design

## Context

The dashboard currently shows a partial degradation warning for the movie library section. The section error is:

```text
Operator 'getitem' is not supported on this expression
```

The failing path is `backend/app/modules/dashboard/service.py` inside `_count_movie_storage_statuses`. The PostgreSQL branch uses:

```python
Movie.storage_summary["storage_status"].as_string()
Movie.storage_summary["last_status"].as_string()
```

`Movie.storage_summary` is declared as `CompatibleJSON`, a SQLAlchemy `TypeDecorator` whose `impl` is `Text`. Although `CompatibleJSON.load_dialect_impl()` uses PostgreSQL `JSONB`, SQLAlchemy's expression comparator still does not expose JSON `getitem` on the wrapped column expression. SQLite tests do not catch this because the SQLite branch already uses `func.json_extract`.

## Goal

Fix the dashboard movie library degradation while preserving the SQL aggregation optimization. The dashboard should continue counting movie storage statuses without loading every `Movie` entity.

## Non-Goals

- Do not redesign dashboard UI.
- Do not change dashboard API response shape.
- Do not replace `CompatibleJSON` globally.
- Do not revert to Python-side full table scanning.
- Do not modify unrelated frontend query migration work.

## Design

Add a small dashboard-local helper:

```python
def _json_text_value(column, key: str, dialect_name: str):
    ...
```

The helper returns a SQLAlchemy expression that extracts a JSON scalar as text:

- SQLite: `func.json_extract(column, f"$.{key}")`
- PostgreSQL: `type_coerce(column, JSONB)[key].astext`
- Other dialects: `func.json_extract(column, f"$.{key}")` as a development fallback

Then `_count_movie_storage_statuses` uses this helper for both `storage_status` and `last_status`. The existing normalization rules remain unchanged:

- `completed` counts as `stored`
- `stored`, `storing`, and `not_stored` count as themselves
- `queued`, `running`, `pending`, `waiting_download`, and `moving` count as `storing`
- all other or missing values count as `not_stored`

Dashboard section fallback through `partial_errors` remains in place for real unexpected failures.

## Testing

Add a PostgreSQL dialect compilation test in `backend/tests/test_dashboard_overview.py`:

- Compile `_json_text_value(Movie.storage_summary, "storage_status", "postgresql")` with `postgresql.dialect()`
- Assert the compiled SQL references `storage_summary`
- Assert the compiled SQL uses PostgreSQL text extraction (`->>`)

Keep existing SQLite dashboard overview tests to verify real aggregate behavior under the local test database.

## Verification

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_dashboard_overview.py -v
```

Expected result:

- all dashboard overview tests pass
- PostgreSQL expression compilation test passes
- existing partial-error test still proves fallback behavior

