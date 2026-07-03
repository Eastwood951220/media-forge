# Movie Filters Cache Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/content/movies/filters?type=` use the `movie_filters` cache when available, keep the current `movies`-table fallback when the cache is empty, and sync `movie_filters` after crawler runs save movies.

**Architecture:** Reuse the existing `scraper.database.repositories.filter_repository.sync_movie_filters()` repository instead of introducing a new sync path. The content API will prefer `MovieFilter` rows, then fall back to the current dynamic distinct query from `Movie`; the crawler runtime will rebuild the cache after a completed run so production `movie_filters` no longer stays empty.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL ARRAY/SQLite-compatible tests, Pytest.

---

## Current API Situation

- `shared/database/models/content.py` defines `MovieFilter`, and the Alembic migration creates `movie_filters`.
- `scraper/database/repositories/filter_repository.py` already contains `sync_movie_filters(session)`, copied from the original `jav-scrapling` behavior.
- `backend/app/modules/content/movies/router.py` currently ignores `MovieFilter` and builds `/api/content/movies/filters?type=` values directly from `Movie`.
- `backend/app/modules/crawler/runtime/service.py` currently completes crawler runs without calling `sync_movie_filters()`.
- The original `jav-scrapling` route read `MovieFilter` first and fell back to dynamic `Movie` queries only when the cache had no names.
- The frontend needs no API shape change: `frontend/src/api/movie/index.ts` already calls `/api/content/movies/filters` and expects `string[]`.

## File Structure

- Modify `backend/app/modules/content/movies/router.py`: import `MovieFilter`, add a cache-reader helper, and make `list_filters()` prefer cached rows before falling back to current dynamic movie scanning.
- Modify `backend/tests/test_content_movies_api.py`: add regression coverage for cached filter values and empty-cache fallback.
- Modify `backend/app/modules/crawler/runtime/service.py`: call `sync_movie_filters(db)` after a successful crawler run and log counts.
- Modify `backend/tests/test_crawler_worker_service.py`: add a crawler-runtime test proving saved movies populate `movie_filters`.

---

### Task 1: Prefer `movie_filters` In The Filters API

**Files:**
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/tests/test_content_movies_api.py`

- [ ] **Step 1: Write the failing cached-filter API test**

Modify the import near the top of `backend/tests/test_content_movies_api.py` from:

```python
from shared.database.models.content import Movie, MovieMagnet
```

to:

```python
from shared.database.models.content import Movie, MovieFilter, MovieMagnet
```

Append this test after `test_movie_filter_options`:

```python
def test_movie_filter_options_prefer_movie_filters_cache(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    session.add(Movie(
        code="CACHE-001",
        source_url="https://javdb.com/v/cache001",
        source_name="缓存回退验证",
        actors=["电影演员"],
        tags=["电影标签"],
        director="电影导演",
        maker="电影片商",
        series="电影系列",
        source_task_ids=[TASK_ID_A],
    ))
    session.add(MovieFilter(type="actor", name="缓存演员", count=1))
    session.add(MovieFilter(type="tag", name="缓存标签", count=1))
    session.add(MovieFilter(type="director", name="缓存导演", count=1))
    session.add(MovieFilter(type="maker", name="缓存片商", count=1))
    session.add(MovieFilter(type="series", name="缓存系列", count=1))
    session.commit()
    session.close()

    actor_response = client.get("/api/content/movies/filters?type=actor", headers=headers)
    tag_response = client.get("/api/content/movies/filters?type=tag", headers=headers)
    director_response = client.get("/api/content/movies/filters?type=director", headers=headers)
    maker_response = client.get("/api/content/movies/filters?type=maker", headers=headers)
    series_response = client.get("/api/content/movies/filters?type=series", headers=headers)

    assert actor_response.status_code == HTTPStatus.OK
    assert actor_response.json()["data"] == ["缓存演员"]
    assert tag_response.json()["data"] == ["缓存标签"]
    assert director_response.json()["data"] == ["缓存导演"]
    assert maker_response.json()["data"] == ["缓存片商"]
    assert series_response.json()["data"] == ["缓存系列"]
```

- [ ] **Step 2: Run the cached-filter test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_movie_filter_options_prefer_movie_filters_cache -v
```

Expected: FAIL because `/api/content/movies/filters?type=actor` returns `["电影演员"]` from `movies` instead of `["缓存演员"]` from `movie_filters`.

- [ ] **Step 3: Implement cached filter lookup**

Modify `backend/app/modules/content/movies/router.py`.

Change this import:

```python
from shared.database.models.content import Movie
```

to:

```python
from shared.database.models.content import Movie, MovieFilter
```

Add this helper immediately after `_sqlite_filter_values`:

```python
def _cached_filter_values(db: Session, filter_type: str) -> list[str]:
    return list(db.scalars(
        select(MovieFilter.name)
        .where(MovieFilter.type == filter_type, MovieFilter.name != "")
        .distinct()
        .order_by(MovieFilter.name.asc())
    ).all())
```

Replace the current `list_filters()` function with this version:

```python
@router.get("/filters")
def list_filters(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    type: str = Query(..., description="actor, tag, director, maker, series"),
) -> dict:
    if type not in VALID_FILTER_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid filter type: {type}")

    cached_names = _cached_filter_values(db, type)
    if cached_names:
        return success(data=cached_names)

    if db.bind.dialect.name == "sqlite":
        return success(data=_sqlite_filter_values(db, type))
    if type == "actor":
        names = db.scalars(select(func.unnest(Movie.actors).label("name")).distinct().order_by("name")).all()
    elif type == "tag":
        names = db.scalars(select(func.unnest(Movie.tags).label("name")).distinct().order_by("name")).all()
    else:
        column = getattr(Movie, type)
        names = db.scalars(select(column).where(column != "", column.is_not(None)).distinct().order_by(column.asc())).all()
    return success(data=[name for name in names if name])
```

- [ ] **Step 4: Run API filter tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py::test_movie_filter_options backend/tests/test_content_movies_api.py::test_movie_filter_options_prefer_movie_filters_cache -v
```

Expected: PASS. The existing `test_movie_filter_options` proves empty `movie_filters` still falls back to `movies`; the new test proves cached rows win when present.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "fix: prefer cached movie filter options"
```

---

### Task 2: Sync `movie_filters` After Successful Crawler Runs

**Files:**
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Write the failing crawler sync test**

Modify the import near the top of `backend/tests/test_crawler_worker_service.py` from:

```python
from shared.database.models.content import Movie, MovieMagnet
```

to:

```python
from shared.database.models.content import Movie, MovieFilter, MovieMagnet
```

Add this stub class after `PersistingMovieServiceStub`:

```python
class FilterSyncMovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "FILTER-001", "url": "https://javdb.com/v/filter001", "name": "FILTER 001"}
        ])
        kwargs["on_item_saved"](
            {"code": "FILTER-001", "url": "https://javdb.com/v/filter001", "name": "FILTER 001"},
            {
                "code": "FILTER-001",
                "source_url": "https://javdb.com/v/filter001",
                "source_name": "FILTER 001",
                "title": "FILTER 001",
                "actors": ["演员缓存A", "演员缓存B"],
                "tags": ["标签缓存A"],
                "director": "导演缓存A",
                "maker": "片商缓存A",
                "series": "系列缓存A",
            },
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}
```

Append this test after `test_execute_run_persists_movie_before_marking_detail_saved`:

```python
def test_execute_run_syncs_movie_filters_after_movie_persistence(monkeypatch) -> None:
    from backend.app.modules.crawler.runtime.service import _execute_run

    monkeypatch.setattr("scraper.services.movie_service.MovieService", lambda: FilterSyncMovieServiceStub())
    session = TestingSessionLocal()
    run, runtime = create_run_with_task("filter-sync")

    _execute_run(session, session.get(CrawlRun, run.id), runtime)

    rows = session.scalars(select(MovieFilter).order_by(MovieFilter.type.asc(), MovieFilter.name.asc())).all()
    assert [(row.type, row.name, row.count) for row in rows] == [
        ("actor", "演员缓存A", 0),
        ("actor", "演员缓存B", 0),
        ("director", "导演缓存A", 0),
        ("maker", "片商缓存A", 0),
        ("series", "系列缓存A", 0),
        ("tag", "标签缓存A", 0),
    ]
```

- [ ] **Step 2: Run the crawler sync test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_execute_run_syncs_movie_filters_after_movie_persistence -v
```

Expected: FAIL because `_execute_run()` saves the movie but leaves `movie_filters` empty.

- [ ] **Step 3: Sync filters after a successful run**

Modify `backend/app/modules/crawler/runtime/service.py`.

Inside `_execute_run()`, find this block:

```python
        _append_run_log(
            str(run.id),
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
            "INFO",
        )
        event_bus.publish(RunStatusEvent(
            run_id=str(run.id),
            status="completed",
            task_name=run.task_name or "",
        ))
```

Replace it with:

```python
        _append_run_log(
            str(run.id),
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
            "INFO",
        )
        try:
            from scraper.database.repositories.filter_repository import sync_movie_filters

            sync_result = sync_movie_filters(db)
            _append_run_log(
                str(run.id),
                f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, "
                f"导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}",
                "INFO",
            )
        except Exception as sync_exc:
            logger.warning("Failed to sync movie filters for run %s: %s", run.id, sync_exc)
            _append_run_log(str(run.id), f"筛选列表同步失败: {sync_exc}", "WARNING")
        event_bus.publish(RunStatusEvent(
            run_id=str(run.id),
            status="completed",
            task_name=run.task_name or "",
        ))
```

- [ ] **Step 4: Run crawler runtime tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS. If any test fails because it expects no filter sync side effects, update only that test's assertion to account for the new `movie_filters` rows created from saved movies.

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/app/modules/crawler/runtime/service.py backend/tests/test_crawler_worker_service.py
git commit -m "fix: sync movie filters after crawler runs"
```

---

### Task 3: Regression Verification

**Files:**
- Verify: `backend/app/modules/content/movies/router.py`
- Verify: `backend/app/modules/crawler/runtime/service.py`
- Verify: `backend/tests/test_content_movies_api.py`
- Verify: `backend/tests/test_crawler_worker_service.py`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py backend/tests/test_crawler_worker_service.py -v
```

Expected: PASS. This proves the filter endpoint reads cache/fallback correctly and crawler runtime populates the cache.

- [ ] **Step 2: Run backend test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

Expected: PASS. This catches regressions in crawler runs, task deletion, model metadata, and content movie APIs.

- [ ] **Step 3: Confirm no frontend API changes are required**

Run:

```bash
rg -n "fetchFilters|/filters" frontend/src/api/movie frontend/src/pages/content/movies
```

Expected output includes:

```text
frontend/src/api/movie/index.ts:...export function fetchFilters(type: FilterType): Promise<string[]> {
frontend/src/api/movie/index.ts:...return request.get<string[]>(`${BASE_URL}/filters`, { type })
```

No frontend code changes are needed because the response remains `success(data=list[str])`, which the request layer unwraps to `string[]`.

- [ ] **Step 4: Commit verification notes if test-only changes remain**

If Task 3 required no source changes, do not create a commit. If a test assertion was adjusted in Step 2, commit only that test file:

```bash
git add backend/tests/test_crawler_worker_service.py
git commit -m "test: align crawler worker filter sync expectations"
```

---

## Self-Review Result

- Spec coverage: The plan covers the current `/api/content/movies/filters?type=` behavior, empty `movie_filters` fallback, cached-row preference, and crawler-driven cache population.
- Placeholder scan: No placeholder implementation steps remain; each code step includes concrete snippets and exact commands.
- Type consistency: `MovieFilter`, `sync_movie_filters(db)`, `list_filters()`, and existing `success(data=...)` response shapes match the current repository code.
