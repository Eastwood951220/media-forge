# Fix PostgreSQL Array Type Cast Error

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the PostgreSQL type mismatch error when filtering movies by tags/actors using array containment operator.

**Root Cause:** The `sql_builder.py` uses `postgresql.TEXT()` as the item type for array containment checks, which generates `VARCHAR` casts. However, the database columns (`actors`, `tags`) are defined as `text[]` (via `CompatibleARRAY(Text)`), and PostgreSQL does not support `text[] @> character varying[]` without explicit casting.

**Architecture:** Change the item type from `postgresql.TEXT()` to `Text` from SQLAlchemy core, which maps to PostgreSQL's native `text` type and is compatible with `text[]` columns.

**Tech Stack:** Python 3.12+, SQLAlchemy 2.0, PostgreSQL

## Global Constraints

- Do not change database schema or Alembic migrations.
- Do not change API response shapes or request parameters.
- All existing tests must continue to pass.

---

## File Structure

### Modify

- `backend/app/modules/content/movies/sql_builder.py`
  - Fix `_postgres_array_contains` to use `Text` type instead of `postgresql.TEXT()` for string array columns.

### Test

- `backend/tests/test_content_movie_queries_sql.py`
  - Add regression test for PostgreSQL array containment with string values.

---

### Task 1: Fix PostgreSQL Array Type Cast

**Files:**
- Modify: `backend/app/modules/content/movies/sql_builder.py:50-51,128-135`
- Test: `backend/tests/test_content_movie_queries_sql.py`

**Interfaces:**
- Consumes: `MovieListFilters`, `split_csv`
- Produces: Correct PostgreSQL array containment SQL with `text` type instead of `varchar`

- [ ] **Step 1: Write failing test for PostgreSQL array type cast**

Append this test to `backend/tests/test_content_movie_queries_sql.py`:

```python
def test_postgresql_tag_filter_uses_text_type_not_varchar() -> None:
    """Regression test: PostgreSQL text[] columns must use text type, not varchar."""
    from sqlalchemy import inspect
    from sqlalchemy.dialects import postgresql

    statement = build_movie_list_statement(
        MovieListFilters(tags="VR"),
        sort_by="code",
        sort_order=1,
        dialect_name="postgresql",
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))

    # Should use TEXT type, not VARCHAR
    assert "::VARCHAR" not in sql or "::text" in sql.lower()
    # Should use array containment operator
    assert "@>" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py::test_postgresql_tag_filter_uses_text_type_not_varchar -v
```

Expected: FAIL with `AssertionError` (SQL contains `::VARCHAR` instead of `::text`)

- [ ] **Step 3: Fix the type cast in sql_builder.py**

In `backend/app/modules/content/movies/sql_builder.py`, change the import and fix the type usage:

Add `Text` to the imports:

```python
from sqlalchemy import Select, Text, and_, false, func, not_, or_, select
```

Then update the PostgreSQL array conditions to use `Text` instead of `postgresql.TEXT()`:

```python
    # PostgreSQL array conditions
    if dialect_name == "postgresql":
        if filters.source_task_id:
            source_task_id = _parse_uuid(filters.source_task_id)
            if source_task_id is not None:
                conditions.append(_postgres_array_contains(Movie.source_task_ids, source_task_id, postgresql.UUID(as_uuid=True)))
            else:
                conditions.append(false())
        for actor in split_csv(filters.actors):
            conditions.append(_postgres_array_contains(Movie.actors, actor, Text))
        for actor in split_csv(filters.actors_not):
            conditions.append(not_(_postgres_array_contains(Movie.actors, actor, Text)))
        for tag in split_csv(filters.tags):
            conditions.append(_postgres_array_contains(Movie.tags, tag, Text))
        for tag in split_csv(filters.tags_not):
            conditions.append(not_(_postgres_array_contains(Movie.tags, tag, Text)))
        if filters.actors_count_min is not None:
            conditions.append(func.array_length(Movie.actors, 1) >= filters.actors_count_min)
        if filters.actors_count_max is not None:
            conditions.append(func.array_length(Movie.actors, 1) <= filters.actors_count_max)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movie_queries_sql.py::test_postgresql_tag_filter_uses_text_type_not_varchar -v
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
git commit -m "fix: use Text type for PostgreSQL array containment instead of VARCHAR"
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
sleep 2
curl -s "http://localhost:18642/api/content/movies?search=VR&tags=VR&page=1&limit=20&sort_by=code&sort_order=1" | head -20
```

Expected: JSON response with movie data (not 500 error)

- [ ] **Step 2: Stop the server**

Run:

```bash
pkill -f "uvicorn app.main:app"
```

---

## Final Verification

- [ ] Run `python -m pytest tests/ -v` — all tests pass
- [ ] Run `npm run build` in `frontend/` — build succeeds
- [ ] Manually test `GET /api/content/movies?tags=VR` — returns 200 OK
