# Movie List PostgreSQL Array Filter Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `GET /api/content/movies?source_task_id=...` so PostgreSQL can execute movie list filters that check UUID, actor, and tag array containment.

**Architecture:** Keep the existing movie list query builder in `backend/app/modules/content/movies/queries.py` and replace only the PostgreSQL array literal construction. Add regression tests that compile the PostgreSQL SQLAlchemy statement and assert it uses `ARRAY[...]`, because the existing SQLite API tests cannot catch psycopg/PostgreSQL syntax failures.

**Tech Stack:** Python 3.14 in local `.venv`, FastAPI, SQLAlchemy 2.x, psycopg 3, PostgreSQL dialect compiler, pytest.

---

## Problem Summary

The reported request:

```text
GET http://localhost:18643/api/content/movies?source_task_id=700b4e30-6090-4221-a37a-4240f39f1208&page=1&limit=20&sort_by=code&sort_order=1
```

fails with:

```text
psycopg.errors.SyntaxError: syntax error at or near "$1"
LINE 4: WHERE movies.source_task_ids @> CAST(array($1::UUID) AS UUID...
```

The root cause is in `backend/app/modules/content/movies/queries.py`: the PostgreSQL branch builds array containment operands with `func.array(...)`, which compiles to invalid PostgreSQL function-call syntax such as `array(%(array_1)s::UUID)`. SQLAlchemy's PostgreSQL dialect has a dedicated `postgresql.array([...])` construct that compiles to valid `ARRAY[%(param_1)s::UUID]`.

## File Structure

- Modify: `backend/app/modules/content/movies/queries.py`
  - Replace `func.array(...)` plus `CAST(... AS ARRAY)` with a small helper that uses `sqlalchemy.dialects.postgresql.array`.
  - Apply the helper to `source_task_id`, `actors`, `actors_not`, `tags`, and `tags_not` filters.
- Modify: `backend/tests/test_content_movie_queries_sql.py`
  - Add PostgreSQL dialect compile tests for UUID and text array filters.
  - Keep existing SQLite behavior tests intact.

## Task 1: Add PostgreSQL Compile Regression Tests

**Files:**
- Modify: `backend/tests/test_content_movie_queries_sql.py:1-7`
- Modify: `backend/tests/test_content_movie_queries_sql.py:109-140`

- [ ] **Step 1: Extend test imports**

Change the top of `backend/tests/test_content_movie_queries_sql.py` from:

```python
from datetime import date
from decimal import Decimal

from backend.app.modules.content.movies.queries import MovieListFilters, list_movies_page
from shared.database.models.content import Movie
```

to:

```python
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from backend.app.modules.content.movies.queries import MovieListFilters, build_movie_list_statement, list_movies_page
from shared.database.models.content import Movie
```

- [ ] **Step 2: Add a local PostgreSQL SQL compiler helper**

Append this helper after `test_list_movies_page_preserves_sqlite_array_filter_fallback` in `backend/tests/test_content_movie_queries_sql.py`:

```python
def compile_postgresql_movie_list_sql(filters: MovieListFilters) -> str:
    statement = build_movie_list_statement(
        filters,
        sort_by="code",
        sort_order=1,
        dialect_name="postgresql",
    )
    return str(statement.compile(dialect=postgresql.dialect()))
```

- [ ] **Step 3: Add the failing source_task_id SQL regression test**

Append this test after `compile_postgresql_movie_list_sql`:

```python
def test_postgresql_source_task_id_filter_uses_array_constructor_sql() -> None:
    task_id = uuid.UUID("700b4e30-6090-4221-a37a-4240f39f1208")

    sql = compile_postgresql_movie_list_sql(MovieListFilters(source_task_id=str(task_id)))

    assert "movies.source_task_ids @> ARRAY[" in sql
    assert "array(" not in sql.lower()
```

- [ ] **Step 4: Add the text array SQL regression test**

Append this test after `test_postgresql_source_task_id_filter_uses_array_constructor_sql`:

```python
def test_postgresql_actor_and_tag_filters_use_array_constructor_sql() -> None:
    sql = compile_postgresql_movie_list_sql(
        MovieListFilters(
            actors="Actor A",
            actors_not="Actor B",
            tags="Tag A",
            tags_not="Tag B",
        )
    )

    assert sql.count("@> ARRAY[") == 4
    assert "movies.actors @> ARRAY[" in sql
    assert "movies.tags @> ARRAY[" in sql
    assert "array(" not in sql.lower()
```

- [ ] **Step 5: Run tests to verify they fail before implementation**

Run:

```bash
. .venv/bin/activate
python -m pytest backend/tests/test_content_movie_queries_sql.py::test_postgresql_source_task_id_filter_uses_array_constructor_sql backend/tests/test_content_movie_queries_sql.py::test_postgresql_actor_and_tag_filters_use_array_constructor_sql -v
```

Expected: both tests fail. The first failure should show that the SQL does not contain `movies.source_task_ids @> ARRAY[`, and both failures should expose `array(` in the compiled SQL.

- [ ] **Step 6: Commit the failing tests**

Run:

```bash
git add backend/tests/test_content_movie_queries_sql.py
git commit -m "test: cover postgres movie array filter sql"
```

## Task 2: Replace Invalid PostgreSQL Array Construction

**Files:**
- Modify: `backend/app/modules/content/movies/queries.py:3-10`
- Modify: `backend/app/modules/content/movies/queries.py:162-170`
- Modify: `backend/app/modules/content/movies/queries.py:242-258`

- [ ] **Step 1: Update PostgreSQL imports**

Change the imports at the top of `backend/app/modules/content/movies/queries.py` from:

```python
import sqlalchemy as sa
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, false, func, not_, or_, select
from sqlalchemy.dialects.postgresql import ARRAY as CompatibleARRAY
from sqlalchemy.orm import Session, selectinload
```

to:

```python
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, false, func, not_, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, selectinload
```

- [ ] **Step 2: Add a PostgreSQL array containment helper**

Add this helper immediately after `_parse_uuid` in `backend/app/modules/content/movies/queries.py`:

```python
def _postgres_array_contains(column: Any, value: Any, item_type: Any):
    return column.op("@>")(postgresql.array([value], type_=item_type))
```

- [ ] **Step 3: Replace the PostgreSQL source_task_id condition**

Change this block in `build_movie_list_statement`:

```python
        if filters.source_task_id:
            source_task_id = _parse_uuid(filters.source_task_id)
            if source_task_id is not None:
                # Use @> operator for array containment
                conditions.append(Movie.source_task_ids.op("@>")(func.cast(func.array(source_task_id), CompatibleARRAY(sa.dialects.postgresql.UUID))))
            else:
                conditions.append(false())
```

to:

```python
        if filters.source_task_id:
            source_task_id = _parse_uuid(filters.source_task_id)
            if source_task_id is not None:
                conditions.append(_postgres_array_contains(Movie.source_task_ids, source_task_id, postgresql.UUID(as_uuid=True)))
            else:
                conditions.append(false())
```

- [ ] **Step 4: Replace actor and tag array conditions**

Change this block in `build_movie_list_statement`:

```python
        for actor in split_csv(filters.actors):
            conditions.append(Movie.actors.op("@>")(func.cast(func.array(actor), CompatibleARRAY(sa.String))))
        for actor in split_csv(filters.actors_not):
            conditions.append(not_(Movie.actors.op("@>")(func.cast(func.array(actor), CompatibleARRAY(sa.String)))))
        for tag in split_csv(filters.tags):
            conditions.append(Movie.tags.op("@>")(func.cast(func.array(tag), CompatibleARRAY(sa.String))))
        for tag in split_csv(filters.tags_not):
            conditions.append(not_(Movie.tags.op("@>")(func.cast(func.array(tag), CompatibleARRAY(sa.String)))))
```

to:

```python
        for actor in split_csv(filters.actors):
            conditions.append(_postgres_array_contains(Movie.actors, actor, postgresql.TEXT()))
        for actor in split_csv(filters.actors_not):
            conditions.append(not_(_postgres_array_contains(Movie.actors, actor, postgresql.TEXT())))
        for tag in split_csv(filters.tags):
            conditions.append(_postgres_array_contains(Movie.tags, tag, postgresql.TEXT()))
        for tag in split_csv(filters.tags_not):
            conditions.append(not_(_postgres_array_contains(Movie.tags, tag, postgresql.TEXT())))
```

- [ ] **Step 5: Run focused tests to verify implementation**

Run:

```bash
. .venv/bin/activate
python -m pytest backend/tests/test_content_movie_queries_sql.py::test_postgresql_source_task_id_filter_uses_array_constructor_sql backend/tests/test_content_movie_queries_sql.py::test_postgresql_actor_and_tag_filters_use_array_constructor_sql -v
```

Expected: both tests pass.

- [ ] **Step 6: Commit the implementation**

Run:

```bash
git add backend/app/modules/content/movies/queries.py backend/tests/test_content_movie_queries_sql.py
git commit -m "fix: use postgres array constructors for movie filters"
```

## Task 3: Verify Movie List Regression Coverage

**Files:**
- Verify: `backend/app/modules/content/movies/queries.py`
- Verify: `backend/tests/test_content_movie_queries_sql.py`
- Verify: `backend/tests/test_content_movies_api.py`
- Verify: `backend/tests/test_task_delete_cascade.py`

- [ ] **Step 1: Run the movie query unit tests**

Run:

```bash
. .venv/bin/activate
python -m pytest backend/tests/test_content_movie_queries_sql.py -v
```

Expected: all tests in `backend/tests/test_content_movie_queries_sql.py` pass.

- [ ] **Step 2: Run existing API coverage for movie list filters**

Run:

```bash
. .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_list_movies_supports_original_filter_contract backend/tests/test_task_delete_cascade.py::test_list_movies_filter_by_source_task_id -v
```

Expected: both tests pass, confirming the SQLite fallback and API response contract still work.

- [ ] **Step 3: Run static import check for the changed module**

Run:

```bash
. .venv/bin/activate
python - <<'PY'
from backend.app.modules.content.movies.queries import MovieListFilters, build_movie_list_statement

statement = build_movie_list_statement(
    MovieListFilters(source_task_id="700b4e30-6090-4221-a37a-4240f39f1208"),
    sort_by="code",
    sort_order=1,
    dialect_name="postgresql",
)
print(statement)
PY
```

Expected: command exits with status 0 and prints a SQLAlchemy `SELECT` statement object without import errors.

- [ ] **Step 4: Verify the live endpoint against local PostgreSQL**

Start or reuse the backend server, then run:

```bash
curl -sS -i 'http://localhost:18643/api/content/movies?source_task_id=700b4e30-6090-4221-a37a-4240f39f1208&page=1&limit=20&sort_by=code&sort_order=1'
```

Expected: no `500 Internal Server Error`. If the local app requires authentication for this endpoint, repeat the request with the same `Authorization: Bearer ...` header used by the frontend session and expect `HTTP/1.1 200 OK`.

- [ ] **Step 5: Confirm no verification-only commit is needed**

Run:

```bash
git status --short
```

Expected: only `backend/app/modules/content/movies/queries.py` and `backend/tests/test_content_movie_queries_sql.py` have changed, and those files were already committed in Task 2. Do not create a documentation-only commit for this verification task.

## Self-Review Notes

- Spec coverage: the reported `source_task_id` movie list 500 is covered by `test_postgresql_source_task_id_filter_uses_array_constructor_sql` and the implementation replacement in `build_movie_list_statement`.
- Related risk coverage: actor and tag PostgreSQL array filters are covered because they used the same invalid `func.array(...)` pattern.
- Placeholder scan: the plan contains no open implementation placeholders; each code-edit step includes exact code.
- Type consistency: the helper name `_postgres_array_contains` is defined once and reused consistently; UUID filters use `postgresql.UUID(as_uuid=True)`, text filters use `postgresql.TEXT()`.
