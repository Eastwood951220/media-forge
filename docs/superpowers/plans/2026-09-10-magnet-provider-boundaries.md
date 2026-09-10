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

---

## File Structure

- Create `scraper/magnets/__init__.py`: package exports.
- Create `scraper/magnets/provider.py`: source-neutral request, result, protocol, and registry.
- Create `scraper/spiders/javdb/magnet_provider.py`: JavDB adapter around current detail task behavior.
- Create `scraper/spiders/javbus/magnet_provider.py`: JavBus adapter around current detail task behavior.
- Create `scraper/tests/test_magnet_provider_registry.py`: registry and provider adapter tests.
- Modify `backend/app/modules/content/movies/magnet_refresh.py`: use `get_magnet_provider(source, fetcher=...)`.
- Modify `backend/tests/test_content_movies_api.py`: verify magnet refresh uses provider boundary and preserves persistence behavior.

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
- Preserves: `execute_magnet_refresh_run(db, run, runtime) -> dict`.

- [ ] **Step 1: Write failing backend provider-boundary test**

In `backend/tests/test_content_movies_api.py`, locate existing magnet refresh tests and add:

```python
def test_magnet_refresh_uses_provider_registry(monkeypatch, db_session, test_user):
    from backend.app.modules.content.movies import magnet_refresh
    from shared.database.models.content import Movie

    movie = Movie(
        code="ABC-001",
        title="Example",
        source_url="https://javdb.com/v/abc",
        source="javdb",
        actors=[],
        tags=[],
        source_task_ids=[],
        source_task_url_ids=[],
    )
    db_session.add(movie)
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

    monkeypatch.setattr(magnet_refresh, "get_magnet_provider", lambda source, fetcher: FakeProvider())
    monkeypatch.setattr(magnet_refresh, "build_site_fetcher", lambda source: object())

    run = magnet_refresh.create_magnet_refresh_run(db_session, test_user.id, [movie.id])
    result = magnet_refresh.execute_magnet_refresh_run(db_session, run, runtime=type("Runtime", (), {
        "is_stop_requested": lambda self, run_id: False,
    })())

    assert result["processed"] == 1
    assert calls[0].source == "javdb"
    assert calls[0].url == "https://javdb.com/v/abc"
```

- [ ] **Step 2: Run the test and verify it fails**

Run the focused magnet refresh test:

```bash
python -m pytest backend/tests/test_content_movies_api.py -q -k "magnet_refresh_uses_provider_registry"
```

Expected: FAIL because `magnet_refresh` still builds `JavdbSpider` directly and does not expose `MovieDetailPayload` or `get_magnet_provider`.

- [ ] **Step 3: Update magnet refresh imports**

In `backend/app/modules/content/movies/magnet_refresh.py`, remove direct `JavdbSpider` import and add:

```python
from scraper.magnets.provider import MovieDetailPayload, MovieDetailRequest, get_magnet_provider
```

Keep `build_site_fetcher`.

- [ ] **Step 4: Replace direct spider execution**

Replace direct `spider.run_single_detail_task` use with:

```python
source = movie.source or "javdb"
provider = get_magnet_provider(source, fetcher=build_site_fetcher(source))
payload = provider.fetch_detail_with_magnets(MovieDetailRequest(
    source=source,
    url=movie.source_url,
    code=movie.code or "",
    name=movie.title or movie.source_name or movie.code or "",
))
detail_data = payload.data
magnets = list(detail_data.get("magnets") or [])
```

Keep the existing persistence call:

```python
upsert_magnets(db, movie.id, {"code": movie.code}, magnets)
```

When provider execution raises an exception, preserve the existing detail-task failure behavior and error message pattern.

- [ ] **Step 5: Run backend tests**

Run:

```bash
python -m pytest backend/tests/test_content_movies_api.py -q -k "magnet"
```

Expected: PASS.

- [ ] **Step 6: Commit**

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
