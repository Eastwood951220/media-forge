# Fix PostgreSQL Array Type Cast Error (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the PostgreSQL type mismatch error when filtering movies by tags/actors using array containment operator.

**Root Cause:** psycopg automatically binds Python `str` parameters as `VARCHAR` type, not `TEXT`. Even though SQLAlchemy's `Text` type is used, psycopg's type inference overrides it. PostgreSQL's `@>` operator requires matching types: `text[] @> text[]`, not `text[] @> varchar[]`.

**Architecture:** Use SQLAlchemy's `cast()` function to explicitly cast each parameter value to `Text` type in the SQL, forcing PostgreSQL to treat it as `text` type.

**Tech Stack:** Python 3.12+, SQLAlchemy 2.0, PostgreSQL

## Global Constraints

- Do not change database schema or Alembic migrations.
- Do not change API response shapes or request parameters.
- All existing tests must continue to pass.

---

## File Structure

### Modify

- `backend/app/modules/content/movies/sql_builder.py`
  - Fix `_postgres_array_contains` to use `cast()` for explicit type conversion.

### Test

- `backend/tests/test_content_movie_queries_sql.py`
  - Add regression test for PostgreSQL array containment with explicit text cast.

---

### Task 1: Fix PostgreSQL Array Type Cast with cast()

**Files:**
- Modify: `backend/app/modules/content/movies/sql_builder.py:50-51`
- Test: `backend/tests/test_content_movie_queries_sql.py`

**Interfaces:**
- Consumes: `MovieListFilters`, `split_csv`
- Produces: Correct PostgreSQL array containment SQL with explicit `::text` cast

- [ ] **Step 1: Write failing test for PostgreSQL array type cast**

Append this test to `backend/tests/test_content_movie_queries_sql.py`:

```python
def test_postgresql_tag_filter_casts_value_to_text() -> None:
    """Regression test: PostgreSQL text[] columns must cast parameters to text type."""
    from sqlalchemy.dialects import postgresql

    statement = build_movie_list_statement(
        MovieListFilters(tags="VR"),
        sort_by="code",
        sort_order=1,
        dialect_name="postgresql",
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))

    # Should cast parameter to text type
    assert "::VARCHAR" not in sql
    assert "@>" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py::test_postgresql_tag_filter_casts_value_to_text -v
```

Expected: FAIL with `AssertionError` (SQL contains `::VARCHAR`)

- [ ] **Step 3: Fix the type cast in sql_builder.py**

In `backend/app/modules/content/movies/sql_builder.py`, add `cast` to the imports and fix `_postgres_array_contains`:

```python
from sqlalchemy import Select, Text, and_, cast, false, func, not_, or_, select
```

Then update `_postgres_array_contains` to use `cast()`:

```python
def _postgres_array_contains(column: Any, value: Any, item_type: Any):
    """Check if a PostgreSQL array column contains a value.

    Uses cast() to explicitly convert the value to the target type,
    preventing psycopg from binding Python str as VARCHAR.
    """
    return column.op("@>")(postgresql.array([cast(value, item_type)]))
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py::test_postgresql_tag_filter_casts_value_to_text -v
```

Expected: PASS

- [ ] **Step 5: Run all movie query tests to verify no regressions**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py tests/test_content_movies_api.py -v
```

Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/content/movies/sql_builder.py backend/tests/test_content_movie_queries_sql.py
git commit -m "fix: use cast() for PostgreSQL array containment to force text type"
```

---

### Task 2: Verify Runtime Fix

**Files:**
- None (verification only)

**Interfaces:**
- Consumes: Fixed `sql_builder.py`
- Produces: Confirmed working movie list API with tag/actor filters

- [ ] **Step 1: Start backend server and test the endpoint**

Run:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --port 18642 &
sleep 3
curl -s "http://localhost:18642/api/content/movies?tags=VR&page=1&limit=20&sort_by=code&sort_order=1" | head -20
pkill -f "uvicorn app.main:app"
```

Expected: JSON response with movie data (not 500 error)

---

## Final Verification

- [ ] Run `python -m pytest tests/ -v` — all tests pass
- [ ] Manually test `GET /api/content/movies?tags=VR` — returns 200 OK
