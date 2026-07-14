# Graphify Hotspot Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce graphify-confirmed high-outdegree hotspots by moving narrow logic out of orchestration files and deleting only verified dead or redundant code.

**Architecture:** Use the current root `graphify-out/graph.json` as the priority input, then make small behavior-preserving extractions. Backend routers and services remain public entry points while pure helpers own tree building, storage sync/delete orchestration, retry selection, and queue snapshots; frontend pages keep composition while helpers/hooks own request policy, table columns, retry confirmation, and page action state.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, Vitest, React Testing Library.

## Global Constraints

- No database schema or Alembic migration changes.
- No API route, response shape, status code, event name, or UI behavior changes.
- No storage provider behavior changes.
- No crawler scraping semantics changes.
- No generated protobuf/gRPC changes.
- No committing graphify output artifacts.
- No speculative feature work beyond the existing `jav-scrapling` refactor and optimization scope.
- Do not revert or overwrite pre-existing uncommitted user changes.
- Use `rg` reference checks before deleting code or exports.

---

## File Structure

### Create

- `backend/app/modules/storage/index/tree.py`
  - Pure storage-index tree helpers: empty tree, record insertion, tree construction, known path extraction, code grouping.
- `backend/app/modules/content/movies/storage_sync_api.py`
  - Router-facing storage sync orchestration and `StorageIndexMissingError` translation boundary.
- `backend/app/modules/content/movies/delete_api.py`
  - Router-facing delete orchestration, provider opening, commit/rollback ownership for movie delete API.
- `backend/app/modules/crawler/runtime/retry.py`
  - Pure-ish retry/restart detail selection and reset helpers for `CrawlerRunService`.
- `frontend/src/request/repeatStrategy.ts`
  - Repeat strategy and pending-request execution helper used by the public request entry.
- `frontend/src/request/headers.ts`
  - Auth header construction helper.
- `frontend/src/pages/crawler/runs/components/RunTaskSummaryMetrics.tsx`
  - Summary metric tiles for run detail tasks.
- `frontend/src/pages/crawler/runs/components/RunTaskToolbar.tsx`
  - Status/keyword filters and retry batch buttons.
- `frontend/src/pages/crawler/runs/components/runTaskColumns.tsx`
  - `ColumnsType<CrawlRunDetailTask>` factory.
- `frontend/src/pages/crawler/runs/utils/retryConfirm.ts`
  - Ant Design confirmation helpers for retry actions.
- `frontend/src/pages/content/movies/hooks/useMovieStorageIndexActions.ts`
  - Storage index refresh and single-movie CD2 sync state/actions.
- `frontend/src/pages/content/movies/hooks/useMoviePageSortDefault.ts`
  - One-time sort default application.

### Modify

- `backend/app/modules/storage/index/store.py`
  - Delegate tree construction/grouping to `tree.py`; keep JSON IO and public store API.
- `backend/tests/test_storage_index_store.py`
  - Add direct helper tests for replacement/upsert and known paths.
- `backend/app/modules/storage/index/router.py`
  - Keep route behavior; use a small local or helper function only if it removes duplicated status/error handling.
- `backend/app/modules/content/movies/router.py`
  - Remove storage sync and delete orchestration from route functions.
- `backend/tests/test_content_movies_api.py`
  - Keep existing assertions passing; add focused assertions only if moved error translation is not covered.
- `backend/app/modules/crawler/runtime/service.py`
  - Delegate retry selection/reset logic.
- `backend/app/modules/crawler/runtime/threaded.py`
  - Remove unused imports/helpers after reference checks.
- `backend/tests/test_crawler_worker_service.py`
  - Keep existing retry/restart behavior tests passing; add one direct retry helper test if selection logic becomes independently testable.
- `frontend/src/request/index.ts`
  - Keep public request API and re-exports; delegate headers and repeat strategy.
- `frontend/src/request/__tests__/transform.test.ts`
  - Extend or add request tests for repeat strategy only if no existing coverage exists.
- `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
  - Keep controlled table composition; delegate metrics, toolbar, columns, confirmations.
- `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`
  - Existing retry behavior tests must continue to pass.
- `frontend/src/pages/content/movies/MovieListPage.tsx`
  - Delegate storage index/CD2 state and one-time sort default effect.
- `frontend/tests/movie-list.ui.test.tsx`
  - Existing movie list behavior must continue to pass.

---

### Task 1: Baseline And Deletion Evidence

**Files:**
- Read: `graphify-out/graph.json`
- Read: `graphify-out/GRAPH_REPORT.md`
- Read: `docs/superpowers/specs/2026-07-14-graphify-hotspot-cleanup-design.md`
- No source modifications in this task.

**Interfaces:**
- Consumes: existing `scripts/analyze_graphify_hotspots.py`.
- Produces: terminal evidence for hotspot order and deletion candidates. Later tasks use this evidence before removing code.

- [ ] **Step 1: Record current workspace state**

Run:

```bash
git status --short
```

Expected: existing user changes are visible. Do not revert them. Any later edits to those files must be based on reading their current contents first.

- [ ] **Step 2: Run current graphify hotspot analyzer**

Run:

```bash
python scripts/analyze_graphify_hotspots.py graphify-out/graph.json --top 25
```

Expected: report includes high-outdegree runtime files such as:

```text
backend/app/modules/crawler/runtime/threaded.py
backend/app/modules/crawler/runtime/service.py
backend/app/modules/content/movies/router.py
backend/app/modules/storage/index/store.py
frontend/src/request/index.ts
frontend/src/pages/crawler/runs/components/RunTaskTable.tsx
frontend/src/pages/content/movies/MovieListPage.tsx
```

- [ ] **Step 3: Capture import/reference checks before deleting anything**

Run:

```bash
rg "from backend\.app\.modules\.content\.movies\.persistence|from backend\.app\.modules\.crawler\.runtime\.executor|from backend\.app\.modules\.storage\.index\.store|from '@/request'|from '../request'|RunTaskTable|MovieListPage" backend frontend/src frontend/tests
```

Expected: references are printed. Use these results to decide whether a wrapper or export is safe to delete. If a candidate has any production reference, move the production reference first or keep the wrapper.

- [ ] **Step 4: Remove only generated Python cache artifacts if they are untracked**

Run:

```bash
git ls-files '**/__pycache__/*' '*.pyc'
```

Expected: no tracked cache files. If output is empty, remove untracked cache directories with:

```bash
find backend scraper shared -name '__pycache__' -type d -prune -exec rm -rf {} +
```

If `git ls-files` prints tracked cache paths, do not remove them in this task; list them in the final task notes for explicit review.

- [ ] **Step 5: Commit only cache cleanup if it changed tracked state**

Run:

```bash
git status --short
```

Expected: removing untracked cache directories usually produces no tracked diff and no commit is needed. If tracked cache files were removed intentionally after review, commit only those removals:

```bash
git add backend scraper shared
git commit -m "chore: remove generated python caches"
```

---

### Task 2: Extract Storage Index Tree Helpers

**Files:**
- Create: `backend/app/modules/storage/index/tree.py`
- Modify: `backend/app/modules/storage/index/store.py`
- Modify: `backend/tests/test_storage_index_store.py`

**Interfaces:**
- Consumes:
  - `StorageIndexRecord` from `backend.app.modules.storage.index.models`
- Produces:
  - `empty_tree(target_folder: str, indexed_at: str | None, *, version: int = 1) -> dict[str, Any]`
  - `insert_record(tree: dict[str, Any], record: StorageIndexRecord) -> None`
  - `tree_from_records(target_folder: str, records: list[StorageIndexRecord], *, indexed_at: str | None, version: int = 1) -> dict[str, Any]`
  - `known_code_folder_paths(tree: dict[str, Any]) -> set[str]`
  - `group_records_by_code(tree: dict[str, Any]) -> dict[str, list[StorageIndexRecord]]`

- [ ] **Step 1: Add focused helper tests**

Append these tests to `backend/tests/test_storage_index_store.py`:

```python
from backend.app.modules.storage.index.tree import (
    group_records_by_code,
    insert_record,
    known_code_folder_paths,
    tree_from_records,
)


def test_storage_index_tree_helpers_replace_duplicate_video_path():
    first = record()
    updated = StorageIndexRecord(
        code=first.code,
        path=first.path,
        target_folder=first.target_folder,
        storage_location=first.storage_location,
        file_name=first.file_name,
        size=first.size + 1,
        indexed_at="2026-07-14T00:00:00+00:00",
    )
    tree = tree_from_records("/嘿嘿/日本", [first], indexed_at=first.indexed_at)

    insert_record(tree, updated)

    grouped = group_records_by_code(tree)
    assert len(grouped["ALDN-206"]) == 1
    assert grouped["ALDN-206"][0].size == first.size + 1
    assert known_code_folder_paths(tree) == {first.target_folder}
```

- [ ] **Step 2: Run helper test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py::test_storage_index_tree_helpers_replace_duplicate_video_path -v
```

Expected: FAIL with `ModuleNotFoundError` or import error for `backend.app.modules.storage.index.tree`.

- [ ] **Step 3: Create `tree.py` with pure helper implementation**

Create `backend/app/modules/storage/index/tree.py`:

```python
from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from backend.app.modules.storage.index.models import StorageIndexRecord


def empty_tree(target_folder: str, indexed_at: str | None, *, version: int = 1) -> dict[str, Any]:
    return {
        "version": version,
        "target_folder": target_folder,
        "indexed_at": indexed_at,
        "categories": {},
    }


def insert_record(tree: dict[str, Any], record: StorageIndexRecord) -> None:
    category = tree.setdefault("categories", {}).setdefault(
        record.storage_location,
        {
            "path": str(PurePosixPath(record.target_folder).parent),
            "code_folders": {},
        },
    )
    folder_name = PurePosixPath(record.target_folder).name
    code_folder = category.setdefault("code_folders", {}).setdefault(
        folder_name,
        {
            "path": record.target_folder,
            "code": record.code,
            "videos": [],
        },
    )
    videos = code_folder.setdefault("videos", [])
    videos[:] = [video for video in videos if video.get("path") != record.path]
    videos.append(
        {
            "path": record.path,
            "file_name": record.file_name,
            "size": record.size,
            "indexed_at": record.indexed_at,
        }
    )


def tree_from_records(
    target_folder: str,
    records: list[StorageIndexRecord],
    *,
    indexed_at: str | None,
    version: int = 1,
) -> dict[str, Any]:
    tree = empty_tree(target_folder, indexed_at=indexed_at, version=version)
    for record in records:
        insert_record(tree, record)
    return tree


def known_code_folder_paths(tree: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for category in (tree.get("categories") or {}).values():
        for code_folder in (category.get("code_folders") or {}).values():
            path = str(code_folder.get("path") or "")
            if path:
                paths.add(path)
    return paths


def group_records_by_code(tree: dict[str, Any]) -> dict[str, list[StorageIndexRecord]]:
    grouped: dict[str, list[StorageIndexRecord]] = defaultdict(list)
    for category_name, category in (tree.get("categories") or {}).items():
        for _folder_name, code_folder in (category.get("code_folders") or {}).items():
            code = str(code_folder.get("code") or "").upper()
            target_folder = str(code_folder.get("path") or "")
            for video in code_folder.get("videos") or []:
                record = StorageIndexRecord(
                    code=code,
                    path=str(video["path"]),
                    target_folder=target_folder,
                    storage_location=str(category_name),
                    file_name=str(video["file_name"]),
                    size=int(video.get("size") or 0),
                    indexed_at=str(video["indexed_at"]),
                )
                grouped[record.code].append(record)
    return dict(grouped)
```

- [ ] **Step 4: Modify `store.py` to delegate tree behavior**

In `backend/app/modules/storage/index/store.py`:

1. Remove these imports:

```python
from collections import defaultdict
from pathlib import PurePosixPath
```

2. Add this import:

```python
from backend.app.modules.storage.index.tree import (
    empty_tree,
    group_records_by_code,
    insert_record,
    known_code_folder_paths,
    tree_from_records,
)
```

3. Replace method bodies:

```python
    def load_index_by_code(self) -> dict[str, list[StorageIndexRecord]]:
        return group_records_by_code(self.read_index_tree())
```

```python
    def tree_from_records(self, target_folder: str, records: list[StorageIndexRecord], *, indexed_at: str | None) -> dict[str, Any]:
        return tree_from_records(target_folder, records, indexed_at=indexed_at, version=self.TREE_VERSION)
```

```python
    def empty_tree(self, target_folder: str, indexed_at: str | None) -> dict[str, Any]:
        return empty_tree(target_folder, indexed_at=indexed_at, version=self.TREE_VERSION)
```

```python
    def known_code_folder_paths(self) -> set[str]:
        try:
            tree = self.read_index_tree()
        except StorageIndexMissingError:
            return set()
        return known_code_folder_paths(tree)
```

```python
    def _insert_record(self, tree: dict[str, Any], record: StorageIndexRecord) -> None:
        insert_record(tree, record)
```

- [ ] **Step 5: Run storage index tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_index_store.py backend/tests/test_storage_index_refresh.py backend/tests/test_storage_index_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit storage index helper extraction**

Run:

```bash
git add backend/app/modules/storage/index/tree.py backend/app/modules/storage/index/store.py backend/tests/test_storage_index_store.py
git commit -m "refactor: extract storage index tree helpers"
```

---

### Task 3: Thin Movies Router Storage Sync And Delete Actions

**Files:**
- Create: `backend/app/modules/content/movies/storage_sync_api.py`
- Create: `backend/app/modules/content/movies/delete_api.py`
- Modify: `backend/app/modules/content/movies/router.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Consumes:
  - `MovieStorageSyncRequest`
  - `MovieDeleteRequest`
  - `StorageConfigService`
  - existing `delete_movies`, `select_movies_for_storage_sync`, and storage sync services.
- Produces:
  - `sync_movies_from_request(db: Session, user_id: str, body: MovieStorageSyncRequest) -> dict`
  - `sync_single_movie_from_cd2(db: Session, user_id: str, movie_id: uuid.UUID) -> dict`
  - `delete_movies_from_request(db: Session, user_id: str, body: MovieDeleteRequest) -> tuple[str, dict]`

- [ ] **Step 1: Add router behavior coverage if missing**

Check existing coverage:

```bash
rg "storage-sync|cloud_only|database_and_cloud|StorageIndexMissingError|请选择要删除的影片|删除云存储文件夹失败" backend/tests/test_content_movies_api.py
```

If `StorageIndexMissingError` translation is not covered, add this test to `backend/tests/test_content_movies_api.py` using the existing app/client fixtures in that file:

```python
def test_movie_storage_sync_returns_400_when_index_missing(client, monkeypatch):
    from backend.app.modules.storage.index.store import StorageIndexMissingError
    from backend.app.modules.content.movies import storage_sync_service

    def raise_missing(*args, **kwargs):
        raise StorageIndexMissingError("存储索引不存在或尚未完成，请先刷新存储索引")

    monkeypatch.setattr(storage_sync_service, "sync_movies_storage_statuses", raise_missing)

    response = client.post("/api/content/movies/storage-sync", json={"movie_ids": []})

    assert response.status_code == 400
    assert "存储索引不存在" in response.json()["detail"]
```

If the file uses an authenticated client fixture name other than `client`, adapt only the fixture name to the existing local convention.

- [ ] **Step 2: Run new or existing targeted movie API test before implementation**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py -v
```

Expected: currently PASS if no new test was needed, or FAIL only if the added test exposes missing translation behavior.

- [ ] **Step 3: Create `storage_sync_api.py`**

Create `backend/app/modules/content/movies/storage_sync_api.py`:

```python
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.schemas import MovieStorageSyncRequest
from backend.app.modules.content.movies.storage_sync_service import (
    select_movies_for_storage_sync,
    sync_movies_storage_statuses,
    sync_single_movie_storage_status_from_cd2,
)
from backend.app.modules.storage.index.store import StorageIndexMissingError
from shared.database.models.content import Movie


def sync_movies_from_request(db: Session, user_id: str, body: MovieStorageSyncRequest) -> dict:
    filters = body.filters.model_dump() if body.filters else {}
    movies = select_movies_for_storage_sync(db, movie_ids=body.movie_ids, filters=filters)
    try:
        payload = sync_movies_storage_statuses(db, user_id=user_id, movies=movies)
    except StorageIndexMissingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return payload.to_dict()


def sync_single_movie_from_cd2(db: Session, user_id: str, movie_id: uuid.UUID) -> dict:
    movie = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="影片不存在")
    return sync_single_movie_storage_status_from_cd2(db, user_id=user_id, movie=movie)
```

- [ ] **Step 4: Create `delete_api.py`**

Create `backend/app/modules/content/movies/delete_api.py`:

```python
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.content.movies.delete_service import (
    CloudMovieDeleteError,
    UnsupportedMovieDeleteMode,
    delete_movies,
)
from backend.app.modules.content.movies.schemas import MovieDeleteRequest
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.tasks.events import publish_movie_storage_updated
from shared.database.models.content import Movie


def delete_movies_from_request(db: Session, user_id: str, body: MovieDeleteRequest) -> tuple[str, dict]:
    if not body.movie_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要删除的影片")

    movies = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id.in_(body.movie_ids)).all()
    if not movies:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="影片不存在")

    config_service = StorageConfigService()

    try:
        if body.mode in {"cloud_only", "database_and_cloud"}:
            with config_service.open_provider() as (_config, provider):
                result = delete_movies(db=db, movies=movies, mode=body.mode, provider=provider)
        else:
            result = delete_movies(db=db, movies=movies, mode=body.mode, provider=None)
        db.commit()
    except UnsupportedMovieDeleteMode as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CloudMovieDeleteError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "删除云存储文件夹失败", "failed_folders": exc.failed_folders},
        ) from exc

    if body.mode == "cloud_only":
        for movie in movies:
            publish_movie_storage_updated(db, user_id, movie.id)

    return "删除成功", result.to_dict()
```

- [ ] **Step 5: Replace orchestration in `router.py`**

In `backend/app/modules/content/movies/router.py`:

1. Remove unused imports after the move:

```python
import json
from sqlalchemy import func, not_, or_, select
from backend.app.modules.content.movies.delete_service import (
    CloudMovieDeleteError,
    UnsupportedMovieDeleteMode,
    delete_movies,
)
from backend.app.modules.content.movies.storage_status import normalized_movie_storage_status
from backend.app.modules.storage.index.store import StorageIndexMissingError
from shared.database.models.content import MovieFilter
```

2. Add imports:

```python
from backend.app.modules.content.movies.delete_api import delete_movies_from_request
from backend.app.modules.content.movies.storage_sync_api import (
    sync_movies_from_request,
    sync_single_movie_from_cd2,
)
```

3. Replace route bodies:

```python
@router.post("/storage-sync")
def sync_movie_storage_statuses(
    body: MovieStorageSyncRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    return success(data=sync_movies_from_request(db, str(current_user.id), body))
```

```python
@router.post("/{movie_id}/storage-sync/cd2")
def sync_single_movie_storage_status_from_cd2(
    movie_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    return success(data=sync_single_movie_from_cd2(db, str(current_user.id), movie_id))
```

```python
@router.post("/delete")
def delete_content_movies(
    body: MovieDeleteRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    msg, payload = delete_movies_from_request(db, str(current_user.id), body)
    return success(msg=msg, data=payload)
```

- [ ] **Step 6: Run movie API and persistence tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_content_movies_api.py backend/tests/test_movie_persistence.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit movies router thinning**

Run:

```bash
git add backend/app/modules/content/movies/storage_sync_api.py backend/app/modules/content/movies/delete_api.py backend/app/modules/content/movies/router.py backend/tests/test_content_movies_api.py
git commit -m "refactor: thin movie router actions"
```

---

### Task 4: Extract Crawler Runtime Retry Helpers

**Files:**
- Create: `backend/app/modules/crawler/runtime/retry.py`
- Modify: `backend/app/modules/crawler/runtime/service.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes:
  - `CrawlRun`
  - `CrawlRunDetailTask`
  - `ENDED_RUN_STATUSES`
  - `RESTARTABLE_DETAIL_STATUSES`
- Produces:
  - `ensure_run_can_restart(db: Session, run: CrawlRun) -> None`
  - `prepare_run_for_restart(db: Session, run: CrawlRun) -> None`
  - `select_retry_details(db: Session, run: CrawlRun, *, detail_ids: list[uuid.UUID] | None, retry_all: bool) -> tuple[list[CrawlRunDetailTask], str]`
  - `mark_details_for_retry(details: list[CrawlRunDetailTask]) -> None`

- [ ] **Step 1: Add direct retry helper tests**

Append to `backend/tests/test_crawler_worker_service.py` near existing retry tests:

```python
def test_select_retry_details_rejects_non_failed_detail(db_session):
    import uuid
    from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
    from backend.app.modules.crawler.runtime.retry import select_retry_details

    run = CrawlRun(task_name="任务", status="completed", crawl_mode="incremental")
    db_session.add(run)
    db_session.flush()
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name="任务",
        code="SAVED-001",
        source_url="https://example.test/saved",
        source_name="saved",
        status="saved",
    )
    db_session.add(detail)
    db_session.commit()

    with pytest.raises(ValueError, match="只能重试 crawl_failed 状态的子任务"):
        select_retry_details(db_session, run, detail_ids=[detail.id], retry_all=False)
```

If this test file uses a fixture name other than `db_session`, adapt the fixture name to the local convention.

- [ ] **Step 2: Run helper test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py::test_select_retry_details_rejects_non_failed_detail -v
```

Expected: FAIL with `ModuleNotFoundError` for `backend.app.modules.crawler.runtime.retry`.

- [ ] **Step 3: Create `retry.py`**

Create `backend/app/modules/crawler/runtime/retry.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.modules.crawler.runtime.details import (
    ENDED_RUN_STATUSES,
    RESTARTABLE_DETAIL_STATUSES,
    clear_run_detail_tasks,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)


def ensure_run_can_restart(db: Session, run: CrawlRun) -> None:
    if run.status not in {"stopped", "failed"}:
        raise ValueError("只能重启已停止或失败的运行")
    if run.task_id is not None:
        return
    restartable_count = (
        db.query(CrawlRunDetailTask)
        .filter(
            CrawlRunDetailTask.run_id == run.id,
            CrawlRunDetailTask.status.in_(RESTARTABLE_DETAIL_STATUSES),
        )
        .count()
    )
    if restartable_count == 0:
        raise ValueError("没有关联任务或未完成子任务，无法重启")


def prepare_run_for_restart(db: Session, run: CrawlRun) -> None:
    if has_detail_phase_started(db, run):
        reset_unfinished_detail_tasks_to_pending(db, run)
    else:
        clear_run_detail_tasks(db, run)
    run.status = "queued"
    run.queued_at = datetime.now()
    run.started_at = None
    run.finished_at = None
    run.result = None
    run.error = None


def select_retry_details(
    db: Session,
    run: CrawlRun,
    *,
    detail_ids: list[uuid.UUID] | None,
    retry_all: bool,
) -> tuple[list[CrawlRunDetailTask], str]:
    if run.status not in ENDED_RUN_STATUSES:
        raise ValueError("运行中不能重试失败子任务")

    if retry_all:
        details = (
            db.query(CrawlRunDetailTask)
            .filter(
                CrawlRunDetailTask.run_id == run.id,
                CrawlRunDetailTask.status == "crawl_failed",
            )
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        retry_label = "全部失败"
    else:
        if not detail_ids:
            raise ValueError("请选择要重新爬取的失败子任务")
        details = (
            db.query(CrawlRunDetailTask)
            .filter(CrawlRunDetailTask.id.in_(detail_ids))
            .order_by(CrawlRunDetailTask.created_at.asc())
            .all()
        )
        found_ids = {detail.id for detail in details}
        missing_ids = [detail_id for detail_id in detail_ids if detail_id not in found_ids]
        if missing_ids:
            raise ValueError("包含无效的子任务选择")
        retry_label = "选中项" if len(details) > 1 else "单条"

    if not details:
        raise ValueError("没有爬取失败的子任务可重试")
    for detail in details:
        if detail.run_id != run.id:
            raise ValueError("包含不属于当前运行的子任务")
        if detail.status != "crawl_failed":
            raise ValueError("只能重试 crawl_failed 状态的子任务")
    return details, retry_label


def mark_details_for_retry(details: list[CrawlRunDetailTask]) -> None:
    for detail in details:
        detail.status = "pending_crawl"
        detail.error = None
        detail.item_data = None
        detail.crawled_at = None
        detail.saved_at = None
```

- [ ] **Step 4: Update `service.py` to delegate restart and retry selection**

In `backend/app/modules/crawler/runtime/service.py`:

1. Remove imports no longer used directly:

```python
from sqlalchemy import func
from backend.app.models.crawl_run import CrawlRunDetailTask
from backend.app.modules.crawler.runtime.details import (
    ENDED_RUN_STATUSES,
    RESTARTABLE_DETAIL_STATUSES,
    clear_run_detail_tasks,
    has_detail_phase_started,
    reset_unfinished_detail_tasks_to_pending,
)
```

2. Keep `reset_unfinished_detail_tasks_to_pending` imported if `stop_run()` still calls it. Otherwise import only that function:

```python
from backend.app.modules.crawler.runtime.details import reset_unfinished_detail_tasks_to_pending
```

3. Add:

```python
from backend.app.modules.crawler.runtime.retry import (
    ensure_run_can_restart,
    mark_details_for_retry,
    prepare_run_for_restart,
    select_retry_details,
)
```

4. In `restart_run()`, replace the status/task/detail reset block with:

```python
        ensure_run_can_restart(self.db, run)
        prepare_run_for_restart(self.db, run)
```

5. In `retry_failed_details()`, replace the detail query and validation block with:

```python
        details, retry_label = select_retry_details(
            self.db,
            run,
            detail_ids=detail_ids,
            retry_all=retry_all,
        )
        mark_details_for_retry(details)
```

Keep the run status reset, commit, runtime enqueue, events, and log behavior in `service.py`.

- [ ] **Step 5: Remove genuinely unused imports from `threaded.py`**

Run:

```bash
python -m compileall backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runtime/threaded.py
```

Then use `rg` and editor diagnostics to remove imports from `threaded.py` that have no references in that file. Do not move threaded scraping behavior in this task unless a duplicated queue/status payload is found by reference checks.

- [ ] **Step 6: Run crawler runtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_threaded_url_completion_refresh.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit crawler runtime helper extraction**

Run:

```bash
git add backend/app/modules/crawler/runtime/retry.py backend/app/modules/crawler/runtime/service.py backend/app/modules/crawler/runtime/threaded.py backend/tests/test_crawler_worker_service.py
git commit -m "refactor: extract crawler retry helpers"
```

---

### Task 5: Split Request Entry And Run Task Table

**Files:**
- Create: `frontend/src/request/headers.ts`
- Create: `frontend/src/request/repeatStrategy.ts`
- Modify: `frontend/src/request/index.ts`
- Create: `frontend/src/pages/crawler/runs/components/RunTaskSummaryMetrics.tsx`
- Create: `frontend/src/pages/crawler/runs/components/RunTaskToolbar.tsx`
- Create: `frontend/src/pages/crawler/runs/components/runTaskColumns.tsx`
- Create: `frontend/src/pages/crawler/runs/utils/retryConfirm.ts`
- Modify: `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx`
- Modify: `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`

**Interfaces:**
- Produces:
  - `globalHeaders() -> Record<string, string>`
  - `requestWithStrategy<T>(config: RequestConfig) -> Promise<T>`
  - `RunTaskSummaryMetrics({ summary }: { summary: RunTaskSummary })`
  - `RunTaskToolbar(props: RunTaskToolbarProps)`
  - `createRunTaskColumns(args: CreateRunTaskColumnsArgs) -> ColumnsType<CrawlRunDetailTask>`
  - `confirmRetryTask(args)`, `confirmRetrySelected(args)`, `confirmRetryAllFailed(args)`

- [ ] **Step 1: Create request header helper**

Create `frontend/src/request/headers.ts`:

```ts
import {getToken} from '@/utils/auth'

const AUTHORIZATION_HEADER = 'Authorization'

export function globalHeaders(): Record<string, string> {
    const token = getToken()

    return {
        ...(token ? {[AUTHORIZATION_HEADER]: `Bearer ${token}`} : {}),
    }
}
```

- [ ] **Step 2: Create repeat strategy helper**

Create `frontend/src/request/repeatStrategy.ts`:

```ts
import {cancelRequest, removeRequestController} from './cancel'
import {getRequestCache} from './cache'
import {service} from './instance'
import type {RepeatStrategy, RequestConfig, RequestPendingRecord} from './types'
import {getRequestKey, getRequestMethod} from './utils'

const pendingRequests = new Map<string, RequestPendingRecord>()

export function getRepeatStrategy(config: RequestConfig): RepeatStrategy {
    if (config.repeatStrategy) {
        return config.repeatStrategy
    }

    if (config.isDedupe === false) {
        return 'none'
    }

    return getRequestMethod(config) === 'get' ? 'reuse' : 'none'
}

export function requestWithStrategy<T = unknown>(config: RequestConfig): Promise<T> {
    const strategy = getRepeatStrategy(config)
    const key = getRequestKey(config)

    if (getRequestMethod(config) === 'get' && config.cache) {
        const cached = getRequestCache<T>(config.cacheKey || key)
        if (cached !== undefined) {
            return Promise.resolve(cached)
        }
    }

    if (strategy === 'none') {
        return service.request<T, T>(config)
    }

    const pending = pendingRequests.get(key)

    if (strategy === 'reuse' || strategy === 'ignore-new') {
        if (pending) {
            return pending.promise as Promise<T>
        }
    }

    if (strategy === 'cancel-prev' && pending) {
        cancelRequest(key, '取消上一次相同请求')
    }

    const promise = service.request<T, T>(config).finally(() => {
        pendingRequests.delete(key)
        removeRequestController(key)
    })

    pendingRequests.set(key, {promise})
    return promise
}
```

- [ ] **Step 3: Thin `request/index.ts`**

In `frontend/src/request/index.ts`:

1. Remove the auth and repeat-strategy internals from this file. The removed declarations are exactly these names:

```ts
import {getToken} from '@/utils/auth'
import {getRequestCache} from './cache'
import type {RequestPendingRecord} from './types'
import {getRequestKey, getRequestMethod} from './utils'
const AUTHORIZATION_HEADER = 'Authorization'
const pendingRequests = new Map<string, RequestPendingRecord>()
function getRepeatStrategy(config: RequestConfig): RepeatStrategy
function requestWithStrategy<T = unknown>(config: RequestConfig): Promise<T>
```

2. Add:

```ts
import {globalHeaders} from './headers'
import {requestWithStrategy} from './repeatStrategy'
```

3. Keep this export so callers do not change:

```ts
export {globalHeaders}
```

- [ ] **Step 4: Create run task metrics component**

Create `frontend/src/pages/crawler/runs/components/RunTaskSummaryMetrics.tsx`:

```tsx
import AnimatedNumber from '@/components/AnimatedNumber'
import type { RunTaskSummary } from '@/api/crawlerRun/types'
import styles from '../RunDetailPage.module.less'

interface RunTaskSummaryMetricsProps {
  summary: RunTaskSummary
}

function RunTaskSummaryMetrics({ summary }: RunTaskSummaryMetricsProps) {
  return (
    <div className={styles.summaryMetrics}>
      {[
        ['总数', summary.total, styles.metricTotal],
        ['完成', summary.completed, styles.metricCompleted],
        ['等待', summary.waiting, styles.metricWaiting],
        ['跳过', summary.skipped, styles.metricSkipped],
        ['失败', summary.failed, styles.metricFailed],
      ].map(([label, value, className]) => (
        <div key={label} className={`${styles.metricTile} ${className}`}>
          <div className={styles.metricLabel}>{label}</div>
          <div className={styles.metricValue}>
            <AnimatedNumber value={Number(value)} duration={1.5} separator="," />
          </div>
        </div>
      ))}
    </div>
  )
}

export default RunTaskSummaryMetrics
```

- [ ] **Step 5: Create retry confirmation helpers**

Create `frontend/src/pages/crawler/runs/utils/retryConfirm.ts`:

```ts
import { Modal } from 'antd'

export function confirmRetryTask(detailId: string, onRetryTask: (detailId: string) => Promise<void>, onDone: () => void) {
  Modal.confirm({
    title: '重新爬取失败子任务',
    content: '确认重新爬取该失败子任务？',
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      await onRetryTask(detailId)
      onDone()
    },
  })
}

export function confirmRetrySelected(detailIds: string[], onRetrySelected: (detailIds: string[]) => Promise<void>, onDone: () => void) {
  Modal.confirm({
    title: '重新爬取选中项',
    content: `确认重新爬取选中的 ${detailIds.length} 个失败子任务？`,
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      await onRetrySelected(detailIds)
      onDone()
    },
  })
}

export function confirmRetryAllFailed(failedCount: number, onRetryAllFailed: () => Promise<void>, onDone: () => void) {
  Modal.confirm({
    title: '重新爬取全部失败',
    content: `确认重新爬取全部 ${failedCount} 个失败子任务？`,
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      await onRetryAllFailed()
      onDone()
    },
  })
}
```

- [ ] **Step 6: Create run task columns factory**

Create `frontend/src/pages/crawler/runs/components/runTaskColumns.tsx`:

```tsx
import { Button, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { CrawlRunDetailTask } from '@/api/crawlerRun/types'
import { runDetailStatusLabels } from '../utils/status'

interface CreateRunTaskColumnsArgs {
  retryEnabled: boolean
  actionLoading: 'stop' | 'restart' | 'retry' | null
  onRetryTask: (detailId: string) => void
}

export function createRunTaskColumns({
  retryEnabled,
  actionLoading,
  onRetryTask,
}: CreateRunTaskColumnsArgs): ColumnsType<CrawlRunDetailTask> {
  return [
    { title: '番号', dataIndex: 'code', key: 'code', width: 120 },
    { title: '来源', dataIndex: 'source_name', key: 'source_name', ellipsis: true },
    {
      title: 'URL来源',
      dataIndex: 'source_url_name',
      key: 'source_url_name',
      width: 140,
      ellipsis: true,
      render: (_, record) => record.source_url_name || record.task_url_type || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const { text, color } = runDetailStatusLabels[status] || { text: status, color: 'default' }
        return <Tag color={color}>{text}</Tag>
      },
    },
    { title: '错误', dataIndex: 'error', key: 'error', ellipsis: true },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) =>
        retryEnabled && record.status === 'crawl_failed' ? (
          <Button
            type="link"
            size="small"
            loading={actionLoading === 'retry'}
            onClick={() => onRetryTask(record.id)}
          >
            重新爬取
          </Button>
        ) : null,
    },
  ]
}
```

- [ ] **Step 7: Create run task toolbar component**

Create `frontend/src/pages/crawler/runs/components/RunTaskToolbar.tsx`:

```tsx
import { Button, Input, Select } from 'antd'
import styles from '../RunDetailPage.module.less'
import { runDetailStatusLabels } from '../utils/status'

interface RunTaskToolbarProps {
  statusFilter: string | undefined
  keyword: string
  retryEnabled: boolean
  selectedFailedCount: number
  failedCount: number
  actionLoading: 'stop' | 'restart' | 'retry' | null
  onStatusChange: (value: string | undefined) => void
  onKeywordSearch: (value: string) => void
  onRetrySelected: () => void
  onRetryAllFailed: () => void
}

function RunTaskToolbar({
  statusFilter,
  keyword,
  retryEnabled,
  selectedFailedCount,
  failedCount,
  actionLoading,
  onStatusChange,
  onKeywordSearch,
  onRetrySelected,
  onRetryAllFailed,
}: RunTaskToolbarProps) {
  return (
    <div className={styles.filterSection}>
      <div className={styles.filterControls}>
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 120 }}
          value={statusFilter}
          onChange={(value) => onStatusChange(value)}
          options={Object.entries(runDetailStatusLabels).map(([key, { text }]) => ({
            value: key,
            label: text,
          }))}
        />
        <Input.Search
          placeholder="搜索番号或名称"
          allowClear
          value={keyword}
          onSearch={(value) => onKeywordSearch(value)}
          style={{ width: 200 }}
        />
      </div>
      <div className={styles.filterActions}>
        {retryEnabled && selectedFailedCount > 0 && (
          <Button loading={actionLoading === 'retry'} onClick={onRetrySelected}>
            重新爬取选中项
          </Button>
        )}
        {retryEnabled && failedCount > 0 && (
          <Button loading={actionLoading === 'retry'} onClick={onRetryAllFailed}>
            重新爬取全部失败
          </Button>
        )}
      </div>
    </div>
  )
}

export default RunTaskToolbar
```

- [ ] **Step 8: Rewrite `RunTaskTable.tsx` as composition**

Replace the body of `frontend/src/pages/crawler/runs/components/RunTaskTable.tsx` with the same public props and these internals:

```tsx
import { useMemo, useState } from 'react'
import { Card, Table } from 'antd'
import type { CrawlRunDetailTask, RunTaskSummary } from '@/api/crawlerRun/types'
import styles from '../RunDetailPage.module.less'
import RunTaskSummaryMetrics from './RunTaskSummaryMetrics'
import RunTaskToolbar from './RunTaskToolbar'
import { createRunTaskColumns } from './runTaskColumns'
import { confirmRetryAllFailed, confirmRetrySelected, confirmRetryTask } from '../utils/retryConfirm'
```

Inside the component:

```tsx
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const retryEnabled = runStatus === 'completed' || runStatus === 'failed' || runStatus === 'stopped'
  const failedTasks = useMemo(() => tasks.filter((task) => task.status === 'crawl_failed'), [tasks])
  const selectedFailedIds = selectedRowKeys.map(String)
  const clearSelection = () => setSelectedRowKeys([])
  const columns = useMemo(
    () => createRunTaskColumns({
      retryEnabled,
      actionLoading,
      onRetryTask: (detailId) => confirmRetryTask(detailId, onRetryTask, clearSelection),
    }),
    [retryEnabled, actionLoading, onRetryTask],
  )
```

Render header:

```tsx
      <div className={styles.taskTableHeader}>
        <RunTaskSummaryMetrics summary={summary} />
        <RunTaskToolbar
          statusFilter={statusFilter}
          keyword={keyword}
          retryEnabled={retryEnabled}
          selectedFailedCount={selectedFailedIds.length}
          failedCount={failedTasks.length}
          actionLoading={actionLoading}
          onStatusChange={onStatusChange}
          onKeywordSearch={onKeywordSearch}
          onRetrySelected={() => confirmRetrySelected(selectedFailedIds, onRetrySelected, clearSelection)}
          onRetryAllFailed={() => confirmRetryAllFailed(failedTasks.length, onRetryAllFailed, clearSelection)}
        />
      </div>
```

Keep the existing `Table` props unchanged.

- [ ] **Step 9: Run request and run-detail tests**

Run:

```bash
cd frontend
npm test -- src/request/__tests__/transform.test.ts src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
```

Expected: PASS.

- [ ] **Step 10: Commit request and run task table split**

Run:

```bash
git add frontend/src/request/headers.ts frontend/src/request/repeatStrategy.ts frontend/src/request/index.ts frontend/src/pages/crawler/runs/components/RunTaskSummaryMetrics.tsx frontend/src/pages/crawler/runs/components/RunTaskToolbar.tsx frontend/src/pages/crawler/runs/components/runTaskColumns.tsx frontend/src/pages/crawler/runs/utils/retryConfirm.ts frontend/src/pages/crawler/runs/components/RunTaskTable.tsx frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
git commit -m "refactor: split request and run task table helpers"
```

---

### Task 6: Extract Movie List Page Action Hooks And Final Verification

**Files:**
- Create: `frontend/src/pages/content/movies/hooks/useMovieStorageIndexActions.ts`
- Create: `frontend/src/pages/content/movies/hooks/useMoviePageSortDefault.ts`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Modify: `frontend/tests/movie-list.ui.test.tsx`

**Interfaces:**
- Produces:
  - `useMovieStorageIndexActions(args: { reload: () => void }) -> { indexRefreshing, cd2SyncingId, handleRefreshStorageIndex, handleCd2Sync }`
  - `useMoviePageSortDefault(args: { loaded: boolean; config: unknown; resetSort: (sort: { sortBy: string; sortOrder: number }) => void }) -> void`

- [ ] **Step 1: Create storage index/CD2 action hook**

Create `frontend/src/pages/content/movies/hooks/useMovieStorageIndexActions.ts`:

```ts
import { useCallback, useState } from 'react'
import { App } from 'antd'
import { refreshStorageIndex, type StorageIndexRefreshMode } from '@/api/storage/storageIndex'
import { syncMovieStorageStatusFromCd2 } from '@/api/movie'
import type { Movie } from '@/api/movie/types'

interface UseMovieStorageIndexActionsArgs {
  reload: () => void
}

export function useMovieStorageIndexActions({ reload }: UseMovieStorageIndexActionsArgs) {
  const { message } = App.useApp()
  const [indexRefreshing, setIndexRefreshing] = useState<StorageIndexRefreshMode | null>(null)
  const [cd2SyncingId, setCd2SyncingId] = useState<string | null>(null)

  const handleRefreshStorageIndex = useCallback(async (mode: StorageIndexRefreshMode) => {
    setIndexRefreshing(mode)
    try {
      await refreshStorageIndex(mode)
      message.success(`${mode === 'full' ? '全量' : '增量'}索引任务启动成功`)
    } catch (error) {
      const text = error instanceof Error ? error.message : '存储索引任务启动失败'
      if (text.includes('正在进行中')) {
        message.warning('存储索引任务正在进行中')
      } else {
        message.error(text.includes('启动失败') ? text : `存储索引任务启动失败：${text}`)
      }
    } finally {
      setIndexRefreshing(null)
    }
  }, [message])

  const handleCd2Sync = useCallback(async (movie: Movie) => {
    setCd2SyncingId(movie._id)
    try {
      const result = await syncMovieStorageStatusFromCd2(movie._id)
      message.success(`CD2同步完成：${result.status === 'stored' ? '已存储' : '未存储'}`)
      reload()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'CD2同步失败')
    } finally {
      setCd2SyncingId(null)
    }
  }, [reload, message])

  return {
    indexRefreshing,
    cd2SyncingId,
    handleRefreshStorageIndex,
    handleCd2Sync,
  }
}
```

- [ ] **Step 2: Create one-time sort default hook**

Create `frontend/src/pages/content/movies/hooks/useMoviePageSortDefault.ts`:

```ts
import { useEffect, useRef } from 'react'
import { parseSortDefault } from '../utils/sort'

interface UseMoviePageSortDefaultArgs {
  loaded: boolean
  config: unknown
  resetSort: (sort: { sortBy: string; sortOrder: number }) => void
}

export function useMoviePageSortDefault({ loaded, config, resetSort }: UseMoviePageSortDefaultArgs) {
  const configSortParsed = useRef(false)

  useEffect(() => {
    if (!loaded || configSortParsed.current) return
    const sortDefault = parseSortDefault(config)
    if (sortDefault) {
      resetSort(sortDefault)
      configSortParsed.current = true
    }
  }, [loaded, config, resetSort])
}
```

- [ ] **Step 3: Thin `MovieListPage.tsx`**

In `frontend/src/pages/content/movies/MovieListPage.tsx`:

1. Remove imports no longer used:

```ts
import { useCallback, useEffect, useRef, useState } from 'react'
import { App } from 'antd'
import { refreshStorageIndex, type StorageIndexRefreshMode } from '@/api/storage/storageIndex'
import { syncMovieStorageStatusFromCd2 } from '@/api/movie'
import { parseSortDefault } from './utils/sort'
```

2. Use:

```ts
import { useMemo } from 'react'
import { Button, Dropdown, Space } from 'antd'
import type { StorageIndexRefreshMode } from '@/api/storage/storageIndex'
import { useMoviePageSortDefault } from './hooks/useMoviePageSortDefault'
import { useMovieStorageIndexActions } from './hooks/useMovieStorageIndexActions'
```

3. Replace local state and callbacks:

```ts
  const storageIndex = useMovieStorageIndexActions({ reload: list.reload })
```

4. Replace sort effect:

```ts
  useMoviePageSortDefault({
    loaded: configHook.loaded,
    config: configHook.config,
    resetSort: list.resetSort,
  })
```

5. Replace references:

```ts
onCd2Sync: storageIndex.handleCd2Sync,
cd2SyncingId: storageIndex.cd2SyncingId,
onClick: ({ key }) => void storageIndex.handleRefreshStorageIndex(key as StorageIndexRefreshMode),
loading={storageIndex.indexRefreshing !== null}
```

- [ ] **Step 4: Run movie list tests**

Run:

```bash
cd frontend
npm test -- tests/movie-list.ui.test.tsx src/pages/content/movies/__tests__/movie-delete.test.tsx src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Run full targeted verification**

Run backend:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_graphify_hotspots.py backend/tests/test_storage_index_store.py backend/tests/test_storage_index_refresh.py backend/tests/test_storage_index_api.py backend/tests/test_content_movies_api.py backend/tests/test_movie_persistence.py backend/tests/test_crawler_worker_service.py backend/tests/test_crawler_threaded_url_completion_refresh.py -v
```

Run frontend:

```bash
cd frontend
npm run lint
npm test -- src/request/__tests__/transform.test.ts src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx tests/movie-list.ui.test.tsx src/pages/content/movies/__tests__/movie-delete.test.tsx src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
npm run build
```

Expected: PASS. If a command fails because of pre-existing workspace changes, record the command, failing test, and reason in the final implementation report.

- [ ] **Step 6: Run graphify hotspot analyzer again**

Run:

```bash
python scripts/analyze_graphify_hotspots.py graphify-out/graph.json --top 25
```

Expected: graph may still show old numbers if graphify has not been updated, but source files should now be thinner by line count and responsibility. Do not commit graphify output.

- [ ] **Step 7: Commit movie page hook extraction**

Run:

```bash
git add frontend/src/pages/content/movies/hooks/useMovieStorageIndexActions.ts frontend/src/pages/content/movies/hooks/useMoviePageSortDefault.ts frontend/src/pages/content/movies/MovieListPage.tsx frontend/tests/movie-list.ui.test.tsx
git commit -m "refactor: extract movie list page actions"
```

- [ ] **Step 8: Final status check**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing user changes remain. Do not stage unrelated files.
