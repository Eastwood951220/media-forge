# Magnet Provider Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a source-neutral magnet/detail provider boundary so JavDB, JavBus, and future sources can refresh movie magnets without backend services depending on concrete spider implementations.

**Architecture:** Add provider dataclasses and a registry under `scraper/magnets`, then wrap current JavDB and JavBus detail-with-magnets behavior behind provider classes. Update backend magnet refresh to ask the provider registry for the right source instead of constructing `JavdbSpider` directly.

**Tech Stack:** Python 3.12+, SQLAlchemy 2.0, existing scraper site fetchers, existing JavDB/JavBus spiders, Pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-scraper-provider-boundaries-design.md`

## Global Constraints

- Do not create or use a Git worktree for this repository; work in the current checkout.
- Stage intended source files explicitly instead of using `git add .` or `git add -A`.
- Create commits grouped by functional change.
- Do not alter full crawler task execution in this phase.
- Preserve current JavDB magnet refresh behavior.
- Keep provider modules inside `scraper`; backend services consume provider registry functions.
- Scraper modules must not import `backend.*`.
- Do not add new database tables in this phase.
- `Movie` has `source_url` and `source_name`, but no `source` or `title` columns.
- Magnet refresh must derive source from URL with `determine_source`.
- Unknown movie/detail sources must fall back to `javdb` to preserve current behavior.
- Graphify marks `Movie`, `CrawlRun`, and `CrawlRunDetailTask` as bridge/god nodes, so do not add columns or model relationships for this provider boundary.
- Keep the implementation localized to `backend/app/modules/content/movies/magnet_refresh.py`, `scraper/magnets/`, `scraper/spiders/javdb/magnet_provider.py`, and `scraper/spiders/javbus/magnet_provider.py`.

---

## File Structure

- Create `scraper/magnets/__init__.py`: package exports.
- Create `scraper/magnets/provider.py`: source-neutral request, result, protocol, and registry.
- Create `scraper/spiders/javdb/magnet_provider.py`: JavDB adapter around current detail task behavior.
- Create `scraper/spiders/javbus/magnet_provider.py`: JavBus adapter around current detail task behavior.
- Create `scraper/tests/test_magnet_provider_registry.py`: registry and provider adapter tests.
- Modify `backend/app/modules/content/movies/magnet_refresh.py`: use `get_magnet_provider(source, fetcher=...)`.
- Modify `backend/tests/test_content_movies_api.py`: verify magnet refresh uses provider boundary and preserves persistence behavior.
- Do not modify `shared/database/models/content.py`, Alembic migrations, or SQL scripts for this phase.

---

### Task 1: Add Magnet Provider Protocol and Registry

**Files:**
- Create: `scraper/magnets/__init__.py`
- Create: `scraper/magnets/provider.py`
- Create: `scraper/tests/test_magnet_provider_registry.py`

**Interfaces:**
- Produces: `MovieDetailRequest(source: str, url: str, code: str = "", name: str = "", task_url_type: str = "", task_url_name: str = "")`.
- Produces: `MovieDetailPayload(data: dict[str, Any])`.
- Produces: `MagnetProvider` protocol with `fetch_detail_with_magnets(request: MovieDetailRequest) -> MovieDetailPayload`.
- Produces: `get_magnet_provider(source: str, *, fetcher) -> MagnetProvider`.

- [ ] **Step 1: Write failing registry tests**

Create `scraper/tests/test_magnet_provider_registry.py`:

```python
import pytest

from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest, get_magnet_provider


class DummyFetcher:
    def get(self, url: str, **kwargs):
        raise AssertionError("not used in registry type test")


def test_movie_detail_request_carries_source_context() -> None:
    request = MovieDetailRequest(
        source="javdb",
        url="https://javdb.com/v/abc",
        code="ABC-001",
        name="Example",
        task_url_type="actors",
        task_url_name="Actor",
    )

    assert request.source == "javdb"
    assert request.url == "https://javdb.com/v/abc"
    assert request.code == "ABC-001"
    assert request.task_url_name == "Actor"


def test_movie_detail_payload_wraps_existing_detail_shape() -> None:
    payload = MovieDetailPayload(data={"code": "ABC-001", "magnets": [{"name": "m"}]})

    assert payload.data["code"] == "ABC-001"
    assert payload.data["magnets"] == [{"name": "m"}]


def test_get_magnet_provider_returns_javdb_and_javbus_providers() -> None:
    assert get_magnet_provider("javdb", fetcher=DummyFetcher()).source == "javdb"
    assert get_magnet_provider("javbus", fetcher=DummyFetcher()).source == "javbus"


def test_get_magnet_provider_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="不支持的磁力来源"):
        get_magnet_provider("unknown", fetcher=DummyFetcher())
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest scraper/tests/test_magnet_provider_registry.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.magnets'`.

- [ ] **Step 3: Implement provider types and registry**

Create `scraper/magnets/provider.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class MovieDetailRequest:
    source: str
    url: str
    code: str = ""
    name: str = ""
    task_url_type: str = ""
    task_url_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MovieDetailPayload:
    data: dict[str, Any]


class MagnetProvider(Protocol):
    source: str

    def fetch_detail_with_magnets(self, request: MovieDetailRequest) -> MovieDetailPayload:
        ...


def get_magnet_provider(source: str, *, fetcher) -> MagnetProvider:
    if source == "javdb":
        from scraper.spiders.javdb.magnet_provider import JavdbMagnetProvider

        return JavdbMagnetProvider(fetcher=fetcher)
    if source == "javbus":
        from scraper.spiders.javbus.magnet_provider import JavbusMagnetProvider

        return JavbusMagnetProvider(fetcher=fetcher)
    raise ValueError(f"不支持的磁力来源: {source}")
```

Create `scraper/magnets/__init__.py`:

```python
from scraper.magnets.provider import MagnetProvider, MovieDetailPayload, MovieDetailRequest, get_magnet_provider

__all__ = [
    "MagnetProvider",
    "MovieDetailPayload",
    "MovieDetailRequest",
    "get_magnet_provider",
]
```

- [ ] **Step 4: Add temporary provider classes to satisfy the registry**

Create `scraper/spiders/javdb/magnet_provider.py`:

```python
from __future__ import annotations

from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest


class JavdbMagnetProvider:
    source = "javdb"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch_detail_with_magnets(self, request: MovieDetailRequest) -> MovieDetailPayload:
        raise NotImplementedError("JavDB magnet provider adapter is added in the next task")
```

Create `scraper/spiders/javbus/magnet_provider.py`:

```python
from __future__ import annotations

from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest


class JavbusMagnetProvider:
    source = "javbus"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch_detail_with_magnets(self, request: MovieDetailRequest) -> MovieDetailPayload:
        raise NotImplementedError("JavBus magnet provider adapter is added in a later task")
```

- [ ] **Step 5: Run registry tests**

Run: `python -m pytest scraper/tests/test_magnet_provider_registry.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scraper/magnets/__init__.py scraper/magnets/provider.py scraper/spiders/javdb/magnet_provider.py scraper/spiders/javbus/magnet_provider.py scraper/tests/test_magnet_provider_registry.py
git commit -m "Add magnet provider registry"
```

---

### Task 2: Implement JavDB Magnet Provider Adapter

**Files:**
- Modify: `scraper/spiders/javdb/magnet_provider.py`
- Modify: `scraper/tests/test_magnet_provider_registry.py`

**Interfaces:**
- Consumes: `JavdbSpider.run_single_detail_task(task: dict, **kwargs) -> dict`.
- Produces: `JavdbMagnetProvider.fetch_detail_with_magnets(request) -> MovieDetailPayload`.

- [ ] **Step 1: Write failing JavDB provider adapter test**

Append to `scraper/tests/test_magnet_provider_registry.py`:

```python
from scraper.magnets.provider import MovieDetailRequest
from scraper.spiders.javdb.magnet_provider import JavdbMagnetProvider


def test_javdb_magnet_provider_returns_detail_payload(monkeypatch) -> None:
    captured = {}

    def fake_run_single_detail_task(self, task, **kwargs):
        captured["task"] = task
        return {
            **task,
            "status": "completed",
            "detail": {
                "code": "ABC-001",
                "source_name": "Example",
                "magnets": [{"name": "magnet", "magnet": "magnet:?xt=urn:btih:abc"}],
            },
        }

    monkeypatch.setattr(
        "scraper.spiders.javdb.javdb_spider.JavdbSpider.run_single_detail_task",
        fake_run_single_detail_task,
    )

    provider = JavdbMagnetProvider(fetcher=DummyFetcher())
    payload = provider.fetch_detail_with_magnets(MovieDetailRequest(
        source="javdb",
        url="https://javdb.com/v/abc",
        code="ABC-001",
        name="Example",
        task_url_type="actors",
        task_url_name="Actor",
    ))

    assert captured["task"]["url"] == "https://javdb.com/v/abc"
    assert captured["task"]["code"] == "ABC-001"
    assert captured["task"]["_task_url_type"] == "actors"
    assert payload.data["code"] == "ABC-001"
    assert payload.data["magnets"][0]["name"] == "magnet"


def test_javdb_magnet_provider_raises_when_spider_fails(monkeypatch) -> None:
    def fake_run_single_detail_task(self, task, **kwargs):
        return {**task, "status": "failed", "reason": "blocked"}

    monkeypatch.setattr(
        "scraper.spiders.javdb.javdb_spider.JavdbSpider.run_single_detail_task",
        fake_run_single_detail_task,
    )

    provider = JavdbMagnetProvider(fetcher=DummyFetcher())

    with pytest.raises(RuntimeError, match="blocked"):
        provider.fetch_detail_with_magnets(MovieDetailRequest(
            source="javdb",
            url="https://javdb.com/v/abc",
            code="ABC-001",
        ))


def test_javdb_magnet_provider_raises_when_detail_is_empty(monkeypatch) -> None:
    def fake_run_single_detail_task(self, task, **kwargs):
        return {**task, "status": "completed", "detail": {}}

    monkeypatch.setattr(
        "scraper.spiders.javdb.javdb_spider.JavdbSpider.run_single_detail_task",
        fake_run_single_detail_task,
    )

    provider = JavdbMagnetProvider(fetcher=DummyFetcher())

    with pytest.raises(RuntimeError, match="javdb detail fetch failed"):
        provider.fetch_detail_with_magnets(MovieDetailRequest(
            source="javdb",
            url="https://javdb.com/v/empty",
            code="EMPTY-001",
        ))
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest scraper/tests/test_magnet_provider_registry.py::test_javdb_magnet_provider_returns_detail_payload -q`

Expected: FAIL because the adapter raises `NotImplementedError`.

- [ ] **Step 3: Implement the JavDB adapter**

Replace `fetch_detail_with_magnets` in `scraper/spiders/javdb/magnet_provider.py`:

```python
from scraper.spiders.javdb.javdb_spider import JavdbSpider
```

```python
    def fetch_detail_with_magnets(self, request: MovieDetailRequest) -> MovieDetailPayload:
        spider = JavdbSpider(fetcher=self.fetcher)
        task = {
            "url": request.url,
            "name": request.name or request.code or request.url,
            "code": request.code,
            "_task_url_type": request.task_url_type,
            "_task_url_name": request.task_url_name,
            "_task_source": request.source,
        }
        result = spider.run_single_detail_task(task)
        detail = result.get("detail") or {}
        if result.get("status") != "completed" or not detail:
            reason = result.get("reason") or "javdb detail fetch failed"
            raise RuntimeError(str(reason))
        return MovieDetailPayload(data=detail)
```

- [ ] **Step 4: Run provider tests**

Run: `python -m pytest scraper/tests/test_magnet_provider_registry.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/spiders/javdb/magnet_provider.py scraper/tests/test_magnet_provider_registry.py
git commit -m "Add JavDB magnet provider adapter"
```

---

### Task 3: Switch Backend Magnet Refresh to Provider Registry

**Files:**
- Modify: `backend/app/modules/content/movies/magnet_refresh.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes: `get_magnet_provider(source, fetcher=build_site_fetcher(source))`.
- Produces: `normalize_magnet_source(source: str) -> str`.
- Produces: `build_magnet_provider(source: str) -> MagnetProvider`.
- Produces: `_movie_detail_request(movie: Movie, detail: CrawlRunDetailTask) -> MovieDetailRequest`.
- Preserves: `execute_magnet_refresh_run(db, run, runtime) -> dict`.

- [ ] **Step 1: Write failing backend provider-boundary test**

In `backend/tests/test_content_movies_api.py`, locate existing magnet refresh tests and add:

```python
def test_magnet_refresh_uses_provider_registry_for_javdb(monkeypatch, db_session, test_user):
    from datetime import datetime
    from types import SimpleNamespace

    from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.content.movies import magnet_refresh
    from shared.database.models.content import Movie

    task = CrawlTask(name="磁力更新", storage_location="", owner_id=test_user.id)
    db_session.add(task)
    db_session.flush()
    movie = Movie(
        code="ABC-001",
        source_url="https://javdb.com/v/abc",
        source_name="Example",
        actors=[],
        tags=[],
        source_task_ids=[task.id],
        source_task_url_ids=[],
    )
    db_session.add(movie)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="magnet_refresh", queued_at=datetime.now())
    db_session.add(run)
    db_session.flush()
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=movie.code,
        source_url=movie.source_url,
        source_name=movie.source_name,
        source_url_name="磁力更新",
        task_url=movie.source_url,
        task_final_url=movie.source_url,
        task_url_type="magnet_refresh",
        status="pending_crawl",
        item_data={"movie_id": str(movie.id)},
        created_at=datetime.now(),
    ))
    db_session.commit()

    calls = []

    class FakeProvider:
        source = "javdb"

        def fetch_detail_with_magnets(self, request):
            calls.append(request)
            return magnet_refresh.MovieDetailPayload(data={
                "code": "ABC-001",
                "magnets": [{
                    "magnet": "magnet:?xt=urn:btih:abc",
                    "name": "ABC-001",
                    "size": 100,
                    "size_text": "100 MB",
                    "file_count": 1,
                    "file_text": "1 file",
                    "tags": [],
                    "has_chinese_sub": False,
                    "date": "2026-09-10",
                }],
            })

    monkeypatch.setattr(magnet_refresh, "build_magnet_provider", lambda source: FakeProvider())

    result = magnet_refresh.execute_magnet_refresh_run(db_session, run, SimpleNamespace(is_stop_requested=lambda run_id: False))

    assert result["saved"] == 1
    assert calls[0].source == "javdb"
    assert calls[0].url == "https://javdb.com/v/abc"
    assert calls[0].name == "Example"
```

- [ ] **Step 1b: Add helper-level source tests**

Add focused tests for helper behavior before changing implementation:

```python
def test_magnet_refresh_normalizes_unknown_source_to_javdb() -> None:
    from backend.app.modules.content.movies import magnet_refresh

    assert magnet_refresh.normalize_magnet_source("javdb") == "javdb"
    assert magnet_refresh.normalize_magnet_source("javbus") == "javbus"
    assert magnet_refresh.normalize_magnet_source("unknown") == "javdb"
    assert magnet_refresh.normalize_magnet_source("") == "javdb"
    assert magnet_refresh.normalize_magnet_source(None) == "javdb"
```

Expected initial failure: `normalize_magnet_source` does not exist yet.

- [ ] **Step 2: Run the test and verify it fails**

Run the focused magnet refresh test:

```bash
python -m pytest backend/tests/test_content_movies_api.py -q -k "magnet_refresh_uses_provider_registry or magnet_refresh_normalizes_unknown_source"
```

Expected: FAIL because `magnet_refresh` still builds `JavdbSpider` directly and does not expose `build_magnet_provider` or `MovieDetailPayload`.

- [ ] **Step 3: Update magnet refresh imports**

In `backend/app/modules/content/movies/magnet_refresh.py`, remove direct `JavdbSpider` import and add:

```python
from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest, get_magnet_provider
from scraper.tasks.task_utils import determine_source
```

Keep `build_site_fetcher`.

- [ ] **Step 4: Add source normalization and provider helpers**

Add these helpers near the old `build_spider` function:

```python
SUPPORTED_MAGNET_SOURCES = {"javdb", "javbus"}


def normalize_magnet_source(source: str | None) -> str:
    value = str(source or "").strip()
    return value if value in SUPPORTED_MAGNET_SOURCES else "javdb"


def build_magnet_provider(source: str):
    normalized = normalize_magnet_source(source)
    return get_magnet_provider(normalized, fetcher=build_site_fetcher(normalized))


def _movie_detail_request(movie: Movie, detail: CrawlRunDetailTask) -> MovieDetailRequest:
    source_url = movie.source_url or detail.source_url or ""
    source = normalize_magnet_source(determine_source(source_url))
    return MovieDetailRequest(
        source=source,
        url=source_url,
        code=movie.code or detail.code or "",
        name=movie.source_name or detail.source_name or movie.code or detail.code or source_url,
        task_url_type=detail.task_url_type or "",
        task_url_name=detail.source_url_name or "",
        extra={
            "detail_task_id": str(detail.id),
            "movie_id": str(movie.id),
            "task_url": detail.task_url or "",
            "task_final_url": detail.task_final_url or "",
        },
    )
```

Remove the old `build_spider()` helper only after tests no longer patch it.

- [ ] **Step 5: Replace direct spider execution**

Replace direct `spider.run_single_detail_task` use with:

```python
request = _movie_detail_request(movie, detail)
provider = build_magnet_provider(request.source)
payload = provider.fetch_detail_with_magnets(request)
detail_data = payload.data
magnets = list(detail_data.get("magnets") or [])
```

Keep the existing persistence call:

```python
upsert_magnets(db, movie.id, {"code": movie.code}, magnets)
```

When provider execution raises an exception, preserve the existing outer `except Exception as exc` path, which sets `detail.status = "save_failed"`, stores the truncated error text, increments `failed`, and appends a run log.

- [ ] **Step 6: Convert existing magnet refresh tests to provider monkeypatches**

In `test_execute_magnet_refresh_updates_only_magnets`, replace the local `Spider` class and `build_spider` monkeypatch with:

```python
class Provider:
    source = "javdb"

    def fetch_detail_with_magnets(self, request):
        return magnet_refresh.MovieDetailPayload(data={
            "code": "MAG-777",
            "source_name": "新标题不能覆盖",
            "actors": ["演员B"],
            "magnets": [
                {
                    "magnet": "magnet:?xt=urn:btih:abcdef",
                    "name": "MAG-777",
                    "size_text": "1.2GB",
                    "file_text": "1 file",
                    "has_chinese_sub": True,
                }
            ],
        })

monkeypatch.setattr(magnet_refresh, "build_magnet_provider", lambda source: Provider())
```

In `test_execute_magnet_refresh_marks_no_magnets_skipped`, replace the local `Spider` class and `build_spider` monkeypatch with:

```python
class Provider:
    source = "javdb"

    def fetch_detail_with_magnets(self, request):
        return magnet_refresh.MovieDetailPayload(data={"code": "NOMAG-1", "magnets": []})

monkeypatch.setattr(magnet_refresh, "build_magnet_provider", lambda source: Provider())
```

- [ ] **Step 7: Add JavBus provider-selection test**

Add this backend test:

```python
def test_magnet_refresh_uses_javbus_provider_for_javbus_url(monkeypatch, db_session, test_user):
    from datetime import datetime
    from types import SimpleNamespace

    from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.content.movies import magnet_refresh
    from shared.database.models.content import Movie

    task = CrawlTask(name="磁力更新", storage_location="", owner_id=test_user.id)
    db_session.add(task)
    db_session.flush()
    movie = Movie(code="BUS-001", source_url="https://www.javbus.com/BUS-001", source_name="Bus Movie", source_task_ids=[task.id])
    db_session.add(movie)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="magnet_refresh", queued_at=datetime.now())
    db_session.add(run)
    db_session.flush()
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=movie.code,
        source_url=movie.source_url,
        source_name=movie.source_name,
        source_url_name="磁力更新",
        task_url=movie.source_url,
        task_final_url=movie.source_url,
        task_url_type="magnet_refresh",
        status="pending_crawl",
        item_data={"movie_id": str(movie.id)},
        created_at=datetime.now(),
    ))
    db_session.commit()

    seen_sources = []

    class Provider:
        def fetch_detail_with_magnets(self, request):
            seen_sources.append(request.source)
            return magnet_refresh.MovieDetailPayload(data={
                "code": "BUS-001",
                "magnets": [{"magnet": "magnet:?xt=urn:btih:bus", "name": "BUS-001"}],
            })

    monkeypatch.setattr(magnet_refresh, "build_magnet_provider", lambda source: Provider())

    result = magnet_refresh.execute_magnet_refresh_run(db_session, run, SimpleNamespace(is_stop_requested=lambda run_id: False))

    assert result["saved"] == 1
    assert seen_sources == ["javbus"]
```

- [ ] **Step 8: Add unknown-source fallback test**

Add this backend test:

```python
def test_magnet_refresh_falls_back_to_javdb_for_unknown_source(monkeypatch, db_session, test_user):
    from datetime import datetime
    from types import SimpleNamespace

    from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.content.movies import magnet_refresh
    from shared.database.models.content import Movie

    task = CrawlTask(name="磁力更新", storage_location="", owner_id=test_user.id)
    db_session.add(task)
    db_session.flush()
    movie = Movie(code="UNK-001", source_url="https://example.test/UNK-001", source_name="Unknown Movie", source_task_ids=[task.id])
    db_session.add(movie)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="magnet_refresh", queued_at=datetime.now())
    db_session.add(run)
    db_session.flush()
    db_session.add(CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=movie.code,
        source_url=movie.source_url,
        source_name=movie.source_name,
        source_url_name="磁力更新",
        task_url=movie.source_url,
        task_final_url=movie.source_url,
        task_url_type="magnet_refresh",
        status="pending_crawl",
        item_data={"movie_id": str(movie.id)},
        created_at=datetime.now(),
    ))
    db_session.commit()

    seen_sources = []

    class Provider:
        def fetch_detail_with_magnets(self, request):
            seen_sources.append(request.source)
            return magnet_refresh.MovieDetailPayload(data={
                "code": "UNK-001",
                "magnets": [{"magnet": "magnet:?xt=urn:btih:unknown", "name": "UNK-001"}],
            })

    monkeypatch.setattr(magnet_refresh, "build_magnet_provider", lambda source: Provider())

    result = magnet_refresh.execute_magnet_refresh_run(db_session, run, SimpleNamespace(is_stop_requested=lambda run_id: False))

    assert result["saved"] == 1
    assert seen_sources == ["javdb"]
```

- [ ] **Step 9: Add provider failure test**

Add this backend test:

```python
def test_magnet_refresh_marks_provider_failure(db_session, test_user, monkeypatch) -> None:
    from datetime import datetime
    from types import SimpleNamespace

    from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.content.movies import magnet_refresh
    from shared.database.models.content import Movie

    task = CrawlTask(name="磁力更新", storage_location="", owner_id=test_user.id)
    db_session.add(task)
    db_session.flush()
    movie = Movie(code="FAIL-001", source_url="https://javdb.com/v/fail", source_name="Fail Movie", source_task_ids=[task.id])
    db_session.add(movie)
    db_session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="running", crawl_mode="magnet_refresh", queued_at=datetime.now())
    db_session.add(run)
    db_session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=movie.code,
        source_url=movie.source_url,
        source_name=movie.source_name,
        source_url_name="磁力更新",
        task_url=movie.source_url,
        task_final_url=movie.source_url,
        task_url_type="magnet_refresh",
        status="pending_crawl",
        item_data={"movie_id": str(movie.id)},
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()

    class Provider:
        def fetch_detail_with_magnets(self, request):
            raise RuntimeError("provider exploded")

    monkeypatch.setattr(magnet_refresh, "build_magnet_provider", lambda source: Provider())

    result = magnet_refresh.execute_magnet_refresh_run(db_session, run, SimpleNamespace(is_stop_requested=lambda run_id: False))

    db_session.refresh(detail)
    assert result["failed"] == 1
    assert detail.status == "save_failed"
    assert detail.error == "provider exploded"
```

- [ ] **Step 10: Run backend tests**

Run:

```bash
python -m pytest backend/tests/test_content_movies_api.py -q -k "magnet"
```

Expected: PASS.

- [ ] **Step 10b: Confirm Graphify-driven coupling constraints**

Run these checks after the backend implementation:

```bash
git diff --name-only
rg -n "source: Mapped|title: Mapped|source = mapped_column|title = mapped_column" shared/database/models backend/alembic sql
rg -n "JavdbSpider|JavbusSpider|run_single_detail_task" backend/app/modules/content/movies scraper/magnets scraper/spiders/*/magnet_provider.py
```

Expected:

- No `shared/database/models/content.py`, Alembic, or SQL files are modified.
- No new `Movie.source` or `Movie.title` fields exist.
- Backend content movie code does not import `JavdbSpider` or `JavbusSpider` directly.
- Direct `run_single_detail_task` calls remain inside scraper provider adapters.

- [ ] **Step 11: Commit**

```bash
git add backend/app/modules/content/movies/magnet_refresh.py backend/tests/test_content_movies_api.py
git commit -m "Use magnet provider registry in refresh"
```

---

### Task 4: Implement JavBus Magnet Provider Adapter

**Files:**
- Modify: `scraper/spiders/javbus/magnet_provider.py`
- Modify: `scraper/tests/test_magnet_provider_registry.py`

**Interfaces:**
- Consumes: `JavbusSpider.run_single_detail_task(task: dict, **kwargs) -> dict`.
- Produces: `JavbusMagnetProvider.fetch_detail_with_magnets(request) -> MovieDetailPayload`.

- [ ] **Step 1: Write failing JavBus provider adapter test**

Append to `scraper/tests/test_magnet_provider_registry.py`:

```python
from scraper.spiders.javbus.magnet_provider import JavbusMagnetProvider


def test_javbus_magnet_provider_returns_detail_payload(monkeypatch) -> None:
    def fake_run_single_detail_task(self, task, **kwargs):
        return {
            **task,
            "status": "completed",
            "detail": {
                "code": "ABC-001",
                "source": "javbus",
                "source_url": task["url"],
                "magnets": [{"name": "bus magnet", "magnet": "magnet:?xt=urn:btih:def"}],
            },
        }

    monkeypatch.setattr(
        "scraper.spiders.javbus.javbus_spider.JavbusSpider.run_single_detail_task",
        fake_run_single_detail_task,
    )

    provider = JavbusMagnetProvider(fetcher=DummyFetcher())
    payload = provider.fetch_detail_with_magnets(MovieDetailRequest(
        source="javbus",
        url="https://www.javbus.com/ABC-001",
        code="ABC-001",
        name="Example",
    ))

    assert payload.data["source"] == "javbus"
    assert payload.data["magnets"][0]["name"] == "bus magnet"


def test_javbus_magnet_provider_raises_when_spider_fails(monkeypatch) -> None:
    def fake_run_single_detail_task(self, task, **kwargs):
        return {**task, "status": "failed", "reason": "missing ajax params: gid"}

    monkeypatch.setattr(
        "scraper.spiders.javbus.javbus_spider.JavbusSpider.run_single_detail_task",
        fake_run_single_detail_task,
    )

    provider = JavbusMagnetProvider(fetcher=DummyFetcher())

    with pytest.raises(RuntimeError, match="missing ajax params"):
        provider.fetch_detail_with_magnets(MovieDetailRequest(
            source="javbus",
            url="https://www.javbus.com/ABC-001",
            code="ABC-001",
        ))


def test_javbus_magnet_provider_passes_task_context(monkeypatch) -> None:
    captured = {}

    def fake_run_single_detail_task(self, task, **kwargs):
        captured["task"] = task
        return {
            **task,
            "status": "completed",
            "detail": {
                "code": "ABC-001",
                "source": "javbus",
                "magnets": [{"name": "bus magnet", "magnet": "magnet:?xt=urn:btih:def"}],
            },
        }

    monkeypatch.setattr(
        "scraper.spiders.javbus.javbus_spider.JavbusSpider.run_single_detail_task",
        fake_run_single_detail_task,
    )

    provider = JavbusMagnetProvider(fetcher=DummyFetcher())
    provider.fetch_detail_with_magnets(MovieDetailRequest(
        source="javbus",
        url="https://www.javbus.com/ABC-001",
        code="ABC-001",
        task_url_type="magnet_refresh",
        task_url_name="磁力更新",
    ))

    assert captured["task"]["_task_source"] == "javbus"
    assert captured["task"]["_task_url_type"] == "magnet_refresh"
    assert captured["task"]["_task_url_name"] == "磁力更新"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest scraper/tests/test_magnet_provider_registry.py::test_javbus_magnet_provider_returns_detail_payload -q`

Expected: FAIL because the adapter raises `NotImplementedError`.

- [ ] **Step 3: Implement the JavBus adapter**

Replace `fetch_detail_with_magnets` in `scraper/spiders/javbus/magnet_provider.py`:

```python
from scraper.spiders.javbus.javbus_spider import JavbusSpider
```

```python
    def fetch_detail_with_magnets(self, request: MovieDetailRequest) -> MovieDetailPayload:
        spider = JavbusSpider(fetcher=self.fetcher)
        task = {
            "url": request.url,
            "name": request.name or request.code or request.url,
            "code": request.code,
            "_task_url_type": request.task_url_type,
            "_task_url_name": request.task_url_name,
            "_task_source": request.source,
        }
        result = spider.run_single_detail_task(task)
        detail = result.get("detail") or {}
        if result.get("status") != "completed" or not detail:
            reason = result.get("reason") or "javbus detail fetch failed"
            raise RuntimeError(str(reason))
        return MovieDetailPayload(data=detail)
```

- [ ] **Step 4: Run provider tests**

Run: `python -m pytest scraper/tests/test_magnet_provider_registry.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/spiders/javbus/magnet_provider.py scraper/tests/test_magnet_provider_registry.py
git commit -m "Add JavBus magnet provider adapter"
```

---

## Final Verification

- [ ] Run provider tests:

```bash
python -m pytest scraper/tests/test_magnet_provider_registry.py -q
```

- [ ] Run existing source spider tests:

```bash
python -m pytest scraper/tests/test_javbus_spider.py scraper/tests/test_javdb_spider_dedupe_callbacks.py -q
```

- [ ] Run movie content tests focused on magnets:

```bash
python -m pytest backend/tests/test_content_movies_api.py -q -k "magnet"
```

- [ ] Run crawler runtime tests that exercise detail task execution:

```bash
python -m pytest backend/tests/test_crawler_threaded_runtime.py -q -k "detail or source"
```

- [ ] Run movie persistence tests to confirm magnet refresh still avoids full movie rewrites:

```bash
python -m pytest backend/tests/test_movie_persistence.py backend/tests/test_content_movie_serializers.py -q
```

- [ ] Review Graphify output if available:

```bash
test -f graphify-out/GRAPH_REPORT.md && sed -n '1,120p' graphify-out/GRAPH_REPORT.md
command -v graphify >/dev/null && graphify update .
```

Expected: if Graphify is available, update the graph after implementation; if it is not available, rely on the focused tests and coupling searches above. Do not add a hard dependency on the currently missing `scripts/analyze_graphify_hotspots.py`.

- [ ] Search for direct magnet refresh source coupling:

```bash
rg -n "JavdbSpider|JavbusSpider|run_single_detail_task" backend/app/modules/content/movies scraper/magnets scraper/spiders/*/magnet_provider.py
```

Expected: backend magnet refresh imports provider registry, while direct spider calls are isolated inside scraper provider adapters.

- [ ] Check git status:

```bash
git status --short
```

Expected: clean working tree after commits.
