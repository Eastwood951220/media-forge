# Graphify-Guided Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make graphify output actionable for runtime code analysis, then refactor the remaining graph-confirmed hotspots without changing behavior.

**Architecture:** First tighten graphify inputs and add a deterministic hotspot analyzer so future graph output is not dominated by generated code or tests. Then split current high-coupling runtime modules into focused helpers while keeping existing public imports stable until consumers are rewired. Frontend work follows the existing page pattern: hooks own state/effects, utils own pure behavior, and components own rendering.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, pytest, React 19, Vite 8, TypeScript 6, Ant Design 6, Vitest, React Testing Library.

## Global Constraints

- No database schema or Alembic migration changes.
- No API route or response shape changes.
- No frontend route, visible layout, or copy changes.
- No scraper behavior changes.
- No storage provider behavior changes.
- No changes to generated protobuf/gRPC code.
- No committing `graphify-out` analysis artifacts.
- Existing public imports must stay compatible until all consumers are rewired.
- Do not stage unrelated untracked files, including `docs/superpowers/plans/2026-07-06-cohesion-coupling-follow-up.md`.

---

## File Structure

### Create

- `scripts/analyze_graphify_hotspots.py`
  - Reads graphify `graph.json`, filters generated/test/noise files, warns on stale commit, and prints top runtime hotspots.
- `backend/tests/test_graphify_hotspots.py`
  - Unit tests for the hotspot analyzer filtering and stale-commit reporting.
- `backend/app/modules/crawler/runtime/detail_index.py`
  - Owns crawl run detail lookup by code/source URL.
- `backend/app/modules/crawler/runtime/progress.py`
  - Owns progress counters and runtime progress writes.
- `backend/app/modules/crawler/runtime/callbacks.py`
  - Owns crawler callback construction and callback side effects.
- `backend/app/modules/crawler/runtime/finalize.py`
  - Owns final run result/status aggregation and movie filter sync.
- `backend/app/modules/storage/worker/download_flow.py`
  - Owns magnet submit and poll/recover download flow.
- `backend/app/modules/storage/worker/existing_target_flow.py`
  - Owns target-folder fallback when download files are missing.
- `backend/app/modules/storage/worker/file_pipeline.py`
  - Owns scan/classify/rename/move/verify/cleanup for found files.
- `backend/app/modules/content/movies/magnet_identity.py`
  - Owns magnet hash and dedupe key.
- `backend/app/modules/content/movies/magnet_scoring.py`
  - Owns magnet size parsing, subtitle detection, and scoring.
- `backend/app/modules/content/movies/magnet_persistence.py`
  - Owns magnet normalization/upsert/best selection.
- `backend/app/modules/content/movies/movie_persistence.py`
  - Owns movie upsert and source task ID append.
- `backend/app/modules/content/movies/filter_sync.py`
  - Owns movie filter rebuild.
- `backend/app/modules/content/movies/storage_locations.py`
  - Owns storage location and target folder spec construction.
- `backend/app/modules/content/movies/storage_scan.py`
  - Owns remote entry normalization, video matching, and provider scan.
- `frontend/src/pages/content/movies/hooks/useMovieListActions.tsx`
- `frontend/src/pages/content/movies/hooks/useMovieUrlDetail.ts`
- `frontend/src/pages/content/movies/utils/detailFilter.ts`
- `frontend/src/pages/storage/tasks/hooks/useStorageSubTaskDetail.ts`
- `frontend/src/pages/storage/tasks/hooks/useStorageSubTaskRealtime.ts`
- `frontend/src/pages/storage/tasks/utils/subtaskStatus.ts`
- `frontend/src/pages/storage/tasks/components/SubtaskInfoCard.tsx`
- `frontend/src/pages/storage/tasks/components/SubtaskFilesCard.tsx`
- `frontend/src/pages/init/hooks/useInitConnectionTests.ts`
- `frontend/src/pages/init/hooks/useInitSubmit.ts`
- `frontend/src/pages/init/components/PostgresConfigSection.tsx`
- `frontend/src/pages/init/components/RedisConfigSection.tsx`
- `frontend/src/pages/init/utils/initParams.ts`
- `frontend/src/pages/init/__tests__/init-page.test.tsx`

### Modify

- `.graphifyignore`
- `backend/app/modules/crawler/runtime/executor.py`
- `backend/tests/test_crawler_worker_service.py`
- `backend/app/modules/storage/worker/steps.py`
- `backend/tests/test_storage_worker_pipeline.py`
- `backend/app/modules/content/movies/persistence.py`
- `backend/app/modules/content/movies/storage_status.py`
- `backend/tests/test_movie_persistence.py`
- `backend/tests/test_content_movies_api.py`
- `frontend/src/pages/content/movies/MovieListPage.tsx`
- `frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts`
- `frontend/src/pages/content/movies/utils/sort.ts`
- `frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx`
- `frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx`
- `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`
- `frontend/src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx`
- `frontend/src/pages/init/InitPage.tsx`

---

### Task 1: Clean Graphify Inputs And Add Hotspot Analyzer

**Files:**
- Modify: `.graphifyignore`
- Create: `scripts/analyze_graphify_hotspots.py`
- Create: `backend/tests/test_graphify_hotspots.py`

**Interfaces:**
- Produces:
  - `scripts.analyze_graphify_hotspots.is_noise_path(path: str) -> bool`
  - `scripts.analyze_graphify_hotspots.analyze_graph(graph_path: Path, *, top: int = 10, repo_root: Path | None = None) -> str`
  - CLI: `python scripts/analyze_graphify_hotspots.py graphify-out/graph.json --top 10`

- [ ] **Step 1: Add analyzer tests**

Create `backend/tests/test_graphify_hotspots.py`:

```python
import json
from pathlib import Path

from scripts.analyze_graphify_hotspots import analyze_graph, is_noise_path


def test_is_noise_path_filters_generated_and_tests() -> None:
    assert is_noise_path("shared/integrations/storage_providers/clouddrive2/proto/clouddrive_pb2_grpc.py")
    assert is_noise_path("backend/tests/test_storage_worker_pipeline.py")
    assert is_noise_path("frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx")
    assert is_noise_path("scraper/tests/test_movie_result.py")
    assert not is_noise_path("backend/app/modules/crawler/runtime/executor.py")
    assert not is_noise_path("frontend/src/pages/content/movies/MovieListPage.tsx")


def test_analyze_graph_filters_noise_and_warns_when_stale(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({
        "built_at_commit": "oldcommit",
        "nodes": [
            {
                "id": "proto",
                "label": "CloudDriveFileSrv",
                "source_file": "shared/integrations/storage_providers/clouddrive2/proto/clouddrive_pb2_grpc.py",
            },
            {
                "id": "executor",
                "label": "executor.py",
                "source_file": "backend/app/modules/crawler/runtime/executor.py",
            },
            {
                "id": "movie",
                "label": "Movie",
                "source_file": "shared/database/models/content.py",
            },
        ],
        "links": [
            {"source": "executor", "target": "movie"},
            {"source": "executor", "target": "movie"},
            {"source": "proto", "target": "movie"},
        ],
    }))

    report = analyze_graph(graph_path, top=5, repo_root=Path.cwd())

    assert "WARNING: graph built_at_commit differs from current HEAD" in report
    assert "backend/app/modules/crawler/runtime/executor.py" in report
    assert "clouddrive_pb2_grpc.py" not in report
```

- [ ] **Step 2: Run analyzer tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_graphify_hotspots.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.analyze_graphify_hotspots'`.

- [ ] **Step 3: Update `.graphifyignore`**

Append these entries if they are not already present:

```gitignore
# Generated protocol files
shared/integrations/storage_providers/clouddrive2/proto/

# Tests are excluded from architecture hotspot analysis
backend/tests/
frontend/src/**/__tests__/
scraper/tests/

# Python bytecode created during local test runs
**/__pycache__/
*.pyc
```

Keep the existing `graphify-out/`, dependency, build, coverage, env, and `data/` exclusions.

- [ ] **Step 4: Create analyzer script**

Create `scripts/analyze_graphify_hotspots.py`:

```python
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

NOISE_PARTS = (
    "/__tests__/",
    "/node_modules/",
    "/graphify-out/",
    "/proto/",
    "/__pycache__/",
)
NOISE_PREFIXES = (
    "backend/tests/",
    "scraper/tests/",
    "shared/integrations/storage_providers/clouddrive2/proto/",
)
RUNTIME_PREFIXES = (
    "backend/app/",
    "frontend/src/",
    "shared/",
    "scraper/",
)


def is_noise_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    if normalized.startswith(NOISE_PREFIXES):
        return True
    return any(part in f"/{normalized}" for part in NOISE_PARTS)


def is_runtime_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized.startswith(RUNTIME_PREFIXES) and not is_noise_path(normalized)


def current_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "<unknown>"


def _node_label(node: dict[str, Any]) -> str:
    label = str(node.get("label") or node.get("id") or "")
    source_file = str(node.get("source_file") or "")
    source_location = str(node.get("source_location") or "")
    suffix = f":{source_location}" if source_location else ""
    return f"{label} [{source_file}{suffix}]"


def _format_counter(title: str, counter: Counter[str], nodes: dict[str, dict[str, Any]], top: int) -> list[str]:
    lines = [title]
    for node_id, count in counter.most_common(top):
        node = nodes[node_id]
        lines.append(f"- {count:>4} {_node_label(node)}")
    if len(lines) == 1:
        lines.append("- none")
    return lines


def analyze_graph(graph_path: Path, *, top: int = 10, repo_root: Path | None = None) -> str:
    repo_root = repo_root or Path.cwd()
    graph = json.loads(graph_path.read_text())
    nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
    runtime_nodes = {
        node_id
        for node_id, node in nodes.items()
        if is_runtime_path(str(node.get("source_file") or ""))
    }
    degree: Counter[str] = Counter()
    outdegree: Counter[str] = Counter()
    indegree: Counter[str] = Counter()
    for link in graph.get("links", []):
        source = str(link.get("source"))
        target = str(link.get("target"))
        if source in runtime_nodes and target in runtime_nodes:
            degree[source] += 1
            degree[target] += 1
            outdegree[source] += 1
            indegree[target] += 1

    built_at = str(graph.get("built_at_commit") or "<missing>")
    head = current_head(repo_root)
    lines = [
        f"Graph: {graph_path}",
        f"built_at_commit: {built_at}",
        f"current_head: {head}",
    ]
    if built_at != "<missing>" and head != "<unknown>" and built_at != head:
        lines.append("WARNING: graph built_at_commit differs from current HEAD")
    lines.append("")
    lines.extend(_format_counter("Top runtime degree", degree, nodes, top))
    lines.append("")
    lines.extend(_format_counter("Top runtime outdegree", outdegree, nodes, top))
    lines.append("")
    lines.extend(_format_counter("Top runtime indegree", indegree, nodes, top))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter graphify hotspots for runtime code review.")
    parser.add_argument("graph", type=Path, help="Path to graphify graph.json")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    print(analyze_graph(args.graph, top=args.top))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run analyzer tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_graphify_hotspots.py -v
```

Expected: PASS.

- [ ] **Step 6: Run analyzer against current graph**

Run:

```bash
source .venv/bin/activate
python scripts/analyze_graphify_hotspots.py graphify-out/graph.json --top 10
```

Expected:
- output includes `WARNING: graph built_at_commit differs from current HEAD`;
- output does not include `clouddrive_pb2_grpc.py`;
- output does not include `backend/tests/`.

- [ ] **Step 7: Commit**

```bash
git add .graphifyignore scripts/analyze_graphify_hotspots.py backend/tests/test_graphify_hotspots.py
git commit -m "tooling: filter graphify hotspots"
```

---

### Task 2: Extract Crawler Runtime Detail Index And Progress

**Files:**
- Create: `backend/app/modules/crawler/runtime/detail_index.py`
- Create: `backend/app/modules/crawler/runtime/progress.py`
- Modify: `backend/app/modules/crawler/runtime/executor.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Produces:
  - `DetailTaskIndex`
  - `DetailTaskIndex.remember(detail: CrawlRunDetailTask) -> None`
  - `DetailTaskIndex.find(task_info: dict[str, Any], item_data: dict[str, Any] | None = None) -> CrawlRunDetailTask | None`
  - `new_progress() -> dict[str, int]`
  - `increment_progress(progress: dict[str, int], key: str, amount: int = 1) -> None`
  - `write_progress(runtime: CrawlerRuntimeState, run_id: str, progress: dict[str, int]) -> None`

- [ ] **Step 1: Add detail index and progress tests**

Append to `backend/tests/test_crawler_worker_service.py`:

```python
def test_detail_task_index_finds_by_code_and_source_url() -> None:
    import uuid
    from backend.app.models.crawl_run import CrawlRunDetailTask
    from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex

    detail = CrawlRunDetailTask(
        run_id=uuid.uuid4(),
        task_name="task",
        code="ABC-001",
        source_url="https://example.test/abc",
        source_name="Movie",
        status="pending_crawl",
    )
    index = DetailTaskIndex()
    index.remember(detail)

    assert index.find({"code": "ABC-001"}) is detail
    assert index.find({"url": "https://example.test/abc"}) is detail
    assert index.find({"code": "ABC-002"}) is None


def test_progress_helpers_write_runtime_progress() -> None:
    from backend.app.modules.crawler.runtime.progress import increment_progress, new_progress, write_progress

    class Runtime:
        def __init__(self) -> None:
            self.writes: list[tuple[str, dict[str, int]]] = []

        def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
            self.writes.append((run_id, dict(progress)))

    runtime = Runtime()
    progress = new_progress()
    increment_progress(progress, "saved")
    increment_progress(progress, "total", 3)
    write_progress(runtime, "run-1", progress)

    assert runtime.writes == [("run-1", {"total": 3, "saved": 1, "failed": 0, "skipped": 0, "save_failed": 0})]
```

- [ ] **Step 2: Run new tests and verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_detail_task_index_finds_by_code_and_source_url tests/test_crawler_worker_service.py::test_progress_helpers_write_runtime_progress -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `detail_index.py`**

Create `backend/app/modules/crawler/runtime/detail_index.py`:

```python
from __future__ import annotations

from typing import Any

from backend.app.models.crawl_run import CrawlRunDetailTask


class DetailTaskIndex:
    def __init__(self) -> None:
        self.by_code: dict[str, CrawlRunDetailTask] = {}
        self.by_source_url: dict[str, CrawlRunDetailTask] = {}

    def remember(self, detail: CrawlRunDetailTask) -> None:
        if detail.code:
            self.by_code[str(detail.code)] = detail
        if detail.source_url:
            self.by_source_url[str(detail.source_url)] = detail

    def find(
        self,
        task_info: dict[str, Any],
        item_data: dict[str, Any] | None = None,
    ) -> CrawlRunDetailTask | None:
        item_data = item_data or {}
        code = item_data.get("code") or task_info.get("code")
        source_url = task_info.get("url") or task_info.get("source_url") or item_data.get("source_url")
        if code and code in self.by_code:
            return self.by_code[str(code)]
        if source_url and source_url in self.by_source_url:
            return self.by_source_url[str(source_url)]
        return None
```

- [ ] **Step 4: Create `progress.py`**

Create `backend/app/modules/crawler/runtime/progress.py`:

```python
from __future__ import annotations

from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState

ProgressState = dict[str, int]


def new_progress() -> ProgressState:
    return {"total": 0, "saved": 0, "failed": 0, "skipped": 0, "save_failed": 0}


def increment_progress(progress: ProgressState, key: str, amount: int = 1) -> None:
    progress[key] = int(progress.get(key, 0)) + amount


def write_progress(runtime: CrawlerRuntimeState, run_id: str, progress: ProgressState) -> None:
    runtime.write_progress(run_id, progress)
```

- [ ] **Step 5: Rewire executor detail/progress helpers**

In `backend/app/modules/crawler/runtime/executor.py`:

```python
from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
from backend.app.modules.crawler.runtime.progress import increment_progress, new_progress, write_progress
```

Replace local dictionaries and nested `remember_detail`/`find_detail` with:

```python
detail_index = DetailTaskIndex()
progress = new_progress()
```

Use:

```python
detail_index.remember(detail)
detail = detail_index.find(task_info, item_data)
increment_progress(progress, "saved")
write_progress(runtime, str(run.id), progress)
```

Preserve the same progress keys and increments currently used in `execute_run()`.

- [ ] **Step 6: Run crawler worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/crawler/runtime/detail_index.py backend/app/modules/crawler/runtime/progress.py backend/app/modules/crawler/runtime/executor.py backend/tests/test_crawler_worker_service.py
git commit -m "refactor: extract crawler runtime detail progress"
```

---

### Task 3: Extract Crawler Runtime Callbacks And Finalization

**Files:**
- Create: `backend/app/modules/crawler/runtime/callbacks.py`
- Create: `backend/app/modules/crawler/runtime/finalize.py`
- Modify: `backend/app/modules/crawler/runtime/executor.py`
- Modify: `backend/tests/test_crawler_worker_service.py`

**Interfaces:**
- Consumes:
  - `DetailTaskIndex`
  - `ProgressState`
  - `increment_progress(...)`
  - `write_progress(...)`
- Produces:
  - `CrawlerCallbackContext`
  - `build_crawl_callbacks(context: CrawlerCallbackContext) -> CrawlCallbacks`
  - `finalize_run(db: Session, run: CrawlRun, runtime: CrawlerRuntimeState, result: dict | None, *, stopped: bool) -> None`

- [ ] **Step 1: Add callback context import regression**

Append to `backend/tests/test_crawler_worker_service.py`:

```python
def test_crawler_callback_context_builds_callbacks(db_session) -> None:
    import uuid
    from backend.app.models.crawl_run import CrawlRun
    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.crawler.runtime.callbacks import CrawlerCallbackContext, build_crawl_callbacks
    from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
    from backend.app.modules.crawler.runtime.progress import new_progress

    task = CrawlTask(id=uuid.uuid4(), name="task", owner_id=uuid.uuid4())
    run = CrawlRun(id=uuid.uuid4(), task_id=task.id, task_name=task.name, status="running")

    class Runtime:
        def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
            return None

        def is_stop_requested(self, run_id: str) -> bool:
            return False

    callbacks = build_crawl_callbacks(CrawlerCallbackContext(
        db=db_session,
        run=run,
        task=task,
        runtime=Runtime(),
        detail_index=DetailTaskIndex(),
        progress=new_progress(),
    ))

    assert callable(callbacks.on_item_saved)
    assert callable(callbacks.on_detail_failed)
    assert callable(callbacks.log_callback)
```

- [ ] **Step 2: Run new regression and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py::test_crawler_callback_context_builds_callbacks -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `callbacks.py`**

Create `backend/app/modules/crawler/runtime/callbacks.py`. Move the callback-related nested functions from `execute_run()` into a dataclass-backed builder:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.movies.persistence import append_source_task_id, upsert_movie_with_magnets
from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
from backend.app.modules.crawler.runtime.engine import CrawlCallbacks
from backend.app.modules.crawler.runtime.events import append_run_log_for_run, publish_run_detail_updated
from backend.app.modules.crawler.runtime.progress import ProgressState, increment_progress, write_progress
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState
from backend.app.modules.crawler.runtime.source_task_names import find_existing_movie_codes, movie_code_exists


@dataclass
class CrawlerCallbackContext:
    db: Session
    run: CrawlRun
    task: CrawlTask
    runtime: CrawlerRuntimeState
    detail_index: DetailTaskIndex
    progress: ProgressState


def build_crawl_callbacks(context: CrawlerCallbackContext, *, include_list_callbacks: bool = True) -> CrawlCallbacks:
    db = context.db
    run = context.run
    task = context.task
    runtime = context.runtime
    detail_index = context.detail_index
    progress = context.progress

    def on_tasks_batch_created(items: list[dict[str, Any]]) -> None:
        skipped_count = 0
        created_details: list[CrawlRunDetailTask] = []
        for item in items:
            is_skipped = item.get("status") == "skipped"
            reason = item.get("reason") if is_skipped else None
            detail = detail_index.find(item)
            if detail is None:
                detail = CrawlRunDetailTask(
                    run_id=run.id,
                    task_name=task.name,
                    code=item.get("code"),
                    source_url=item.get("url", ""),
                    source_name=item.get("name", ""),
                    status="skipped" if is_skipped else "pending_crawl",
                    error=reason,
                    created_at=datetime.now(),
                )
                db.add(detail)
                db.flush()
            elif detail.status not in {"saved", "skipped"}:
                detail.status = "skipped" if is_skipped else "pending_crawl"
                detail.error = reason
                detail.item_data = None
                detail.crawled_at = None
                detail.saved_at = None
            detail_index.remember(detail)
            created_details.append(detail)
            if is_skipped:
                skipped_count += 1
                if append_source_task_id(db, item.get("code"), task.id):
                    append_run_log_for_run(db, run, f"已存在影片追加任务ID: {item.get('code')} -> {task.id}", "INFO", code=item.get("code"))
        increment_progress(progress, "total", len(items))
        increment_progress(progress, "skipped", skipped_count)
        write_progress(runtime, str(run.id), progress)
        db.commit()
        publish_run_detail_updated(db, run, created_details)
        if items:
            append_run_log_for_run(db, run, f"创建子任务 {len(items)} 条，跳过 {skipped_count} 条")

    def on_item_saved(task_info: dict[str, Any], item_data: dict[str, Any]) -> None:
        detail = detail_index.find(task_info, item_data)
        code = item_data.get("code") or task_info.get("code") or "-"
        item_data_with_task_ids = {**item_data, "source_task_ids": [task.id]}
        try:
            movie_id = upsert_movie_with_magnets(db, item_data_with_task_ids)
            if detail:
                detail.status = "saved"
                detail.item_data = item_data
                detail.error = None
                detail.crawled_at = datetime.now()
                detail.saved_at = datetime.now()
            increment_progress(progress, "saved")
            append_run_log_for_run(db, run, f"入库成功: {code}", "INFO", code=code, movie_id=str(movie_id))
        except Exception as exc:
            if detail:
                detail.status = "save_failed"
                detail.item_data = item_data
                detail.error = str(exc)[:500]
                detail.crawled_at = datetime.now()
                detail.saved_at = None
            increment_progress(progress, "save_failed")
            append_run_log_for_run(db, run, f"入库失败: {code}: {exc}", "ERROR", code=code)
        write_progress(runtime, str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])

    def on_detail_failed(task_info: dict[str, Any], error: str) -> None:
        detail = detail_index.find(task_info)
        if detail:
            detail.status = "crawl_failed"
            detail.error = error[:500]
            detail.crawled_at = datetime.now()
        increment_progress(progress, "failed")
        write_progress(runtime, str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
        append_run_log_for_run(db, run, f"爬取失败: {task_info.get('code') or task_info.get('url')}: {error}", "ERROR")

    def on_item_already_exists(task_info: dict[str, Any]) -> None:
        detail = detail_index.find(task_info)
        code = task_info.get("code")
        was_skipped = detail is not None and detail.status == "skipped"
        if detail:
            detail.status = "skipped"
            detail.error = "already_exists"
            detail.crawled_at = detail.crawled_at or datetime.now()
            detail.saved_at = None
        append_source_task_id(db, code, task.id)
        if not was_skipped:
            increment_progress(progress, "skipped")
        write_progress(runtime, str(run.id), progress)
        db.commit()
        if detail:
            publish_run_detail_updated(db, run, [detail])
        append_run_log_for_run(db, run, f"跳过已存在影片并追加任务ID: {code}", "INFO", code=code)

    def log_callback(message: str, level: str = "INFO") -> None:
        append_run_log_for_run(db, run, message, level)

    def db_check_callback(codes: list[str]) -> set[str]:
        existing_codes = find_existing_movie_codes(db, codes)
        if existing_codes:
            append_run_log_for_run(db, run, f"列表阶段发现已存在影片 {len(existing_codes)} 条", "INFO")
        return existing_codes

    def on_detail_check_callback(code: str) -> bool:
        exists = movie_code_exists(db, code)
        if exists:
            append_run_log_for_run(db, run, f"详情阶段跳过已存在影片: {code}", "INFO", code=code)
        return exists

    return CrawlCallbacks(
        on_tasks_batch_created=on_tasks_batch_created if include_list_callbacks else None,
        on_item_saved=on_item_saved,
        on_detail_failed=on_detail_failed,
        on_item_already_exists=on_item_already_exists,
        log_callback=log_callback,
        db_check_callback=db_check_callback if include_list_callbacks else None,
        on_detail_check_callback=on_detail_check_callback,
        stop_check=lambda: runtime.is_stop_requested(str(run.id)),
    )
```

- [ ] **Step 4: Create `finalize.py`**

Create `backend/app/modules/crawler/runtime/finalize.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.modules.content.movies.persistence import sync_movie_filters
from backend.app.modules.crawler.runtime.details import count_run_detail_tasks, reset_unfinished_detail_tasks_to_pending
from backend.app.modules.crawler.runtime.events import append_run_log_for_run, publish_run_detail_updated, publish_run_updated
from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState

logger = logging.getLogger(__name__)


def finalize_run(
    db: Session,
    run: CrawlRun,
    runtime: CrawlerRuntimeState,
    result: dict | None,
    *,
    stopped: bool,
) -> None:
    if stopped:
        reset_details = reset_unfinished_detail_tasks_to_pending(db, run)
        if reset_details:
            publish_run_detail_updated(db, run, reset_details)

    total_count = count_run_detail_tasks(db, run.id)
    saved_count = count_run_detail_tasks(db, run.id, "saved")
    save_failed_count = count_run_detail_tasks(db, run.id, "save_failed")
    crawl_failed_count = count_run_detail_tasks(db, run.id, "crawl_failed")
    skipped_count = count_run_detail_tasks(db, run.id, "skipped")
    run.result = {
        **(result or {}),
        "total_tasks": total_count,
        "saved": saved_count,
        "save_failed": save_failed_count,
        "crawl_failed": crawl_failed_count,
        "skipped_tasks": skipped_count,
        "stopped": stopped,
    }
    if stopped:
        run.status = "stopped"
        run.error = run.error or "用户停止任务"
        append_run_log_for_run(
            db,
            run,
            f"任务已停止: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
            "WARNING",
        )
    else:
        run.status = "completed"
        append_run_log_for_run(
            db,
            run,
            f"任务完成: 总计={total_count}, 已保存={saved_count}, 入库失败={save_failed_count}, 爬取失败={crawl_failed_count}, 跳过={skipped_count}",
            "INFO",
        )
        try:
            sync_result = sync_movie_filters(db)
            append_run_log_for_run(
                db,
                run,
                f"筛选列表已同步: 演员={sync_result['actors']}, 标签={sync_result['tags']}, "
                f"导演={sync_result['directors']}, 片商={sync_result['makers']}, 系列={sync_result['series']}",
                "INFO",
            )
        except Exception as sync_exc:
            logger.warning("Failed to sync movie filters for run %s: %s", run.id, sync_exc)
            append_run_log_for_run(db, run, f"筛选列表同步失败: {sync_exc}", "WARNING")

    run.finished_at = datetime.now()
    db.commit()
    publish_run_updated(db, run)
```

- [ ] **Step 5: Rewire `executor.py`**

In `executor.py`, import:

```python
from backend.app.modules.crawler.runtime.callbacks import CrawlerCallbackContext, build_crawl_callbacks
from backend.app.modules.crawler.runtime.detail_index import DetailTaskIndex
from backend.app.modules.crawler.runtime.finalize import finalize_run
from backend.app.modules.crawler.runtime.progress import new_progress
```

Use `DetailTaskIndex` to preload details immediately after the run/task are loaded, before the detail-restart branch is evaluated:

```python
detail_index = DetailTaskIndex()
progress = new_progress()
for detail in db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).all():
    detail_index.remember(detail)
callback_context = CrawlerCallbackContext(
    db=db,
    run=run,
    task=task,
    runtime=runtime,
    detail_index=detail_index,
    progress=progress,
)
```

For detail restart:

```python
callbacks=build_crawl_callbacks(callback_context, include_list_callbacks=False)
```

For normal crawl:

```python
callbacks=build_crawl_callbacks(callback_context, include_list_callbacks=True)
```

Replace the final result aggregation block with:

```python
stopped = runtime.is_stop_requested(str(run.id)) or bool((result or {}).get("stopped"))
finalize_run(db, run, runtime, result, stopped=stopped)
```

- [ ] **Step 6: Run crawler worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_crawler_worker_service.py tests/test_crawler_engine.py -v
```

Expected: PASS.

- [ ] **Step 7: Verify executor is thinner**

Run:

```bash
rg -n "def on_|def db_check_callback|def log_callback|sync_movie_filters|count_run_detail_tasks|reset_unfinished_detail_tasks_to_pending" backend/app/modules/crawler/runtime/executor.py
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/crawler/runtime/callbacks.py backend/app/modules/crawler/runtime/finalize.py backend/app/modules/crawler/runtime/executor.py backend/tests/test_crawler_worker_service.py
git commit -m "refactor: split crawler runtime executor"
```

---

### Task 4: Split Storage Magnet Attempt Flow

**Files:**
- Create: `backend/app/modules/storage/worker/download_flow.py`
- Create: `backend/app/modules/storage/worker/existing_target_flow.py`
- Create: `backend/app/modules/storage/worker/file_pipeline.py`
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Produces:
  - `DownloadFlowResult(found_files: list[dict], submit_task_exists: bool)`
  - `run_download_flow(context, magnet: dict, download_folder: str, download_root: str) -> DownloadFlowResult | None`
  - `handle_existing_target_fallback(context, magnet: dict, preview_name: str, target_paths: list[str], download_folder: str, config: dict) -> bool | None`
  - `run_found_files_pipeline(context, magnet: dict, found_files: list[dict], target_paths: list[str], download_folder: str, config: dict) -> bool`

- [ ] **Step 1: Add flow module import regression**

Append to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_storage_attempt_flow_modules_export_public_functions() -> None:
    from backend.app.modules.storage.worker.download_flow import DownloadFlowResult, run_download_flow
    from backend.app.modules.storage.worker.existing_target_flow import handle_existing_target_fallback
    from backend.app.modules.storage.worker.file_pipeline import run_found_files_pipeline

    assert DownloadFlowResult(found_files=[], submit_task_exists=False).found_files == []
    assert callable(run_download_flow)
    assert callable(handle_existing_target_fallback)
    assert callable(run_found_files_pipeline)
```

- [ ] **Step 2: Run new regression and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py::test_storage_attempt_flow_modules_export_public_functions -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `download_flow.py`**

Create `backend/app/modules/storage/worker/download_flow.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from backend.app.modules.storage.worker.download import (
    is_submit_task_exists_error,
    poll_downloaded_video_files,
    recover_existing_downloaded_video_files,
)
from backend.app.modules.storage.worker.target_files import ensure_directory_chain


@dataclass
class DownloadFlowResult:
    found_files: list[dict]
    submit_task_exists: bool


def run_download_flow(context, magnet: dict, download_folder: str, download_root: str) -> DownloadFlowResult | None:
    provider = context.provider
    subtask = context.subtask
    magnet_url = magnet.get("magnet_url", "")
    context.set_step("submit_magnet")
    submit_task_exists = False
    try:
        context.log(
            "INFO",
            "准备提交磁力到 CloudDrive2",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder},
            step="submit_magnet",
        )
        ensure_directory_chain(provider, download_folder)
        result = provider.submit_offline_download(magnet_url, download_folder)
        context.log(
            "INFO",
            "磁力链接已提交",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder, "result_paths": getattr(result, "result_paths", [])},
            step="submit_magnet",
        )
    except Exception as exc:
        if not is_submit_task_exists_error(exc):
            context.log("ERROR", f"提交磁力失败: {exc}", {"magnet_id": magnet.get("id")}, step="submit_magnet")
            return None
        submit_task_exists = True
        context.log("WARNING", "磁力链接已存在 (code 10008)，搜索现有下载中", {"magnet_id": magnet.get("id")}, step="submit_magnet")

    context.set_step("waiting_download")
    search_terms = [subtask.movie_code]
    if submit_task_exists:
        found_files = recover_existing_downloaded_video_files(
            context,
            search_terms=search_terms,
            task_download_folder=download_folder,
            download_root=download_root,
        )
    else:
        found_files = poll_downloaded_video_files(
            context,
            search_terms=search_terms,
            task_download_folder=download_folder,
            download_root=download_root,
        )
    return DownloadFlowResult(found_files=found_files, submit_task_exists=submit_task_exists)
```

- [ ] **Step 4: Create `existing_target_flow.py`**

Move the no-files target fallback branch from `execute_current_magnet_attempt()` into `backend/app/modules/storage/worker/existing_target_flow.py`:

```python
from __future__ import annotations

from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.results import (
    mark_subtask_skipped_for_existing_targets,
    mark_subtask_success_from_existing_targets,
)
from backend.app.modules.storage.worker.target_files import (
    copy_existing_target_to_missing_targets,
    find_existing_target_files,
)
from backend.app.modules.storage.worker.verify_ops import verify_moved_files


def handle_existing_target_fallback(
    context,
    magnet: dict,
    preview_name: str,
    target_paths: list[str],
    download_folder: str,
    config: dict,
) -> bool | None:
    subtask = context.subtask
    expected_names = [preview_name]
    existing_result = find_existing_target_files(context.provider, target_paths, expected_names)
    context.log(
        "INFO",
        "检查目标目录是否已存在视频文件",
        {
            "search_method": "list_sub_files",
            "storage_mode": getattr(subtask, "storage_mode", ""),
            "expected_names": expected_names,
            "checked_targets": existing_result.checked_targets,
            "existing_targets": existing_result.existing_targets,
            "missing_targets": existing_result.missing_targets,
            "source_path": existing_result.source_path,
            "existing_files": existing_result.existing_files,
        },
        step="waiting_download",
    )
    if existing_result.all_targets_exist:
        mark_subtask_skipped_for_existing_targets(context, existing_result, preview_name)
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True
    if getattr(subtask, "storage_mode", "") == "multiple" and existing_result.any_target_exists:
        copied_files = copy_existing_target_to_missing_targets(context, existing_result)
        subtask.renamed_files = []
        subtask.moved_files = copied_files
        subtask.skipped_files = []
        context.publish_subtask()
        context.set_step("verify_result")
        if not verify_moved_files(context, copied_files):
            return False
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        mark_subtask_success_from_existing_targets(context, copied_files, existing_result, magnet)
        return True
    return None
```

- [ ] **Step 5: Create `file_pipeline.py`**

Move the found-files branch from `execute_current_magnet_attempt()` into `backend/app/modules/storage/worker/file_pipeline.py`. Required function:

```python
from __future__ import annotations

from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.file_ops import scan_found_files
from backend.app.modules.storage.worker.move_ops import move_renamed_videos
from backend.app.modules.storage.worker.rename_ops import rename_selected_videos
from backend.app.modules.storage.worker.results import mark_subtask_skipped_for_move_result
from backend.app.modules.storage.worker.timeline import classify_scanned_files
from backend.app.modules.storage.worker.verify_ops import verify_moved_files


def run_found_files_pipeline(
    context,
    magnet: dict,
    found_files: list[dict],
    target_paths: list[str],
    download_folder: str,
    config: dict,
) -> bool:
    subtask = context.subtask
    tags = list(magnet.get("tags") or [])
    total_size = sum(int(file.get("size") or 0) for file in found_files)
    context.log(
        "INFO",
        f"下载完成: 检测到 {len(found_files)} 个文件, 总大小 {total_size / (1024 * 1024):.1f} MB",
        {"file_count": len(found_files), "total_size": total_size},
        step="waiting_download",
    )

    context.set_step("scan_files")
    scanned = scan_found_files(found_files)
    context.log("INFO", f"扫描到 {len(scanned)} 个文件", {"file_count": len(scanned)}, step="scan_files")

    context.set_step("select_videos")
    classified = classify_scanned_files(scanned, config)
    context.log(
        "INFO",
        f"文件筛选: videos={len(classified.selected_videos)}, excluded={len(classified.excluded_files)}, subtitles={len(classified.subtitle_files)}, covers={len(classified.cover_files)}, other={len(classified.other_files)}",
        step="select_videos",
    )
    if not classified.selected_videos:
        context.log("WARNING", "扫描到文件但未识别到主视频", {"magnet_id": magnet.get("id"), "file_count": len(scanned)}, step="select_videos")
        return False

    context.set_step("rename_files")
    renamed_files = rename_selected_videos(context, classified.selected_videos, tags)

    context.set_step("move_files")
    move_result = move_renamed_videos(context, renamed_files, target_paths)
    moved_files = move_result.moved_files
    skipped_files = move_result.skipped_files
    subtask.renamed_files = renamed_files
    subtask.moved_files = moved_files
    subtask.skipped_files = skipped_files
    context.publish_subtask()
    if move_result.all_targets_exist:
        mark_subtask_skipped_for_move_result(context, "target_exists", skipped_files, target_paths)
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True

    if move_result.all_rename_name_exists:
        mark_subtask_skipped_for_move_result(context, "rename_name_exists", skipped_files, target_paths)
        context.set_step("cleanup_files")
        cleanup_download_folder(context, download_folder, config)
        return True

    if not moved_files:
        context.log("WARNING", "没有文件完成移动或复制", {"skipped_files": skipped_files}, step="move_files")
        return False

    context.set_step("verify_result")
    if not verify_moved_files(context, moved_files):
        return False

    context.set_step("cleanup_files")
    cleanup_download_folder(context, download_folder, config)

    subtask.result = {"status": "success", "files": moved_files}
    context.log("INFO", "磁力任务处理成功", {"magnet_id": magnet.get("id"), "files": moved_files}, step="cleanup_files", event="magnet_success")
    return True
```

This keeps the found-files branch behavior byte-for-byte equivalent at the event/step/status level while removing CloudDrive submission and existing-target fallback coupling from the file operation pipeline.

- [ ] **Step 6: Rewire `steps.py`**

In `execute_current_magnet_attempt()`:

```python
download_result = run_download_flow(context, magnet, download_folder, download_root)
if download_result is None:
    return False
found_files = download_result.found_files
if not found_files:
    context.log(
        "WARNING",
        "未在下载目录找到可用视频文件",
        {"magnet_id": magnet.get("id"), "task_download_folder": download_folder, "download_root": download_root},
        step="waiting_download",
    )
    if download_result.submit_task_exists:
        fallback_result = handle_existing_target_fallback(context, magnet, preview_name, target_paths, download_folder, config)
        if fallback_result is not None:
            return fallback_result
    return False
return run_found_files_pipeline(context, magnet, found_files, target_paths, download_folder, config)
```

Keep prepare planning/logging and `execute_subtask_pipeline()` in `steps.py`.

- [ ] **Step 7: Run storage worker tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_storage_worker_pipeline.py tests/test_storage_worker_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Verify moved flow logic is absent from `steps.py`**

Run:

```bash
rg -n "submit_offline_download|poll_downloaded_video_files|recover_existing_downloaded_video_files|find_existing_target_files|copy_existing_target_to_missing_targets|scan_found_files|classify_scanned_files|rename_selected_videos|move_renamed_videos|verify_moved_files" backend/app/modules/storage/worker/steps.py
```

Expected: no output except import lines if a compatibility import is temporarily needed. Remove unused imports before committing.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/worker/download_flow.py backend/app/modules/storage/worker/existing_target_flow.py backend/app/modules/storage/worker/file_pipeline.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "refactor: split storage magnet attempt flow"
```

---

### Task 5: Split Movie Magnet And Movie Persistence Modules

**Files:**
- Create: `backend/app/modules/content/movies/magnet_identity.py`
- Create: `backend/app/modules/content/movies/magnet_scoring.py`
- Create: `backend/app/modules/content/movies/magnet_persistence.py`
- Create: `backend/app/modules/content/movies/movie_persistence.py`
- Create: `backend/app/modules/content/movies/filter_sync.py`
- Modify: `backend/app/modules/content/movies/persistence.py`
- Modify: `backend/tests/test_movie_persistence.py`

**Interfaces:**
- Produces:
  - `extract_info_hash(magnet_url: str | None) -> str`
  - `build_magnet_dedupe_key(movie_id: str, magnet: dict[str, Any]) -> str`
  - `parse_size_mb(value: Any) -> float`
  - `compute_magnet_weight(magnet: dict[str, Any]) -> int`
  - `normalize_magnet(movie_id: UUID, magnet: dict[str, Any]) -> dict[str, Any] | None`
  - `upsert_magnets(session: Session, movie_id: UUID, movie: dict[str, Any], magnets: list[dict[str, Any]]) -> int`
  - `auto_select_best_magnet(session: Session, movie_id: UUID) -> None`
  - `upsert_movie(session: Session, item: dict[str, Any]) -> UUID`
  - `append_source_task_id(session: Session, code: str | None, task_id: UUID) -> bool`
  - `sync_movie_filters(session: Session) -> dict[str, int]`
  - `persistence.py` re-exports the existing public names.

- [ ] **Step 1: Add pure magnet tests**

Append to `backend/tests/test_movie_persistence.py`:

```python
def test_magnet_identity_and_scoring_helpers() -> None:
    from backend.app.modules.content.movies.magnet_identity import build_magnet_dedupe_key, extract_info_hash
    from backend.app.modules.content.movies.magnet_scoring import compute_magnet_weight, parse_size_mb

    assert extract_info_hash("magnet:?xt=urn:btih:ABCDEF") == "abcdef"
    assert parse_size_mb("1.5 GB") == 1536
    assert parse_size_mb("1024 KB") == 1
    assert parse_size_mb("1 TB") == 1024 * 1024
    assert build_magnet_dedupe_key("movie-1", {"name": "a", "size_text": "1 GB"})
    assert compute_magnet_weight({"name": "ABC 中文字幕", "size_text": "3 GB", "file_count": 1}) > compute_magnet_weight({"name": "ABC", "size_text": "500 MB", "file_count": 10})
```

- [ ] **Step 2: Add module export regression**

Append to `backend/tests/test_movie_persistence.py`:

```python
def test_movie_persistence_facade_exports_existing_public_functions() -> None:
    from backend.app.modules.content.movies import persistence
    from backend.app.modules.content.movies import magnet_identity, magnet_persistence, magnet_scoring, movie_persistence, filter_sync

    assert persistence.extract_info_hash is magnet_identity.extract_info_hash
    assert persistence.compute_magnet_weight is magnet_scoring.compute_magnet_weight
    assert persistence.upsert_magnets is magnet_persistence.upsert_magnets
    assert persistence.upsert_movie is movie_persistence.upsert_movie
    assert persistence.append_source_task_id is movie_persistence.append_source_task_id
    assert persistence.sync_movie_filters is filter_sync.sync_movie_filters
```

- [ ] **Step 3: Run new tests and verify they fail**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_movie_persistence.py::test_magnet_identity_and_scoring_helpers tests/test_movie_persistence.py::test_movie_persistence_facade_exports_existing_public_functions -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Move identity and scoring helpers**

Create:

```text
backend/app/modules/content/movies/magnet_identity.py
backend/app/modules/content/movies/magnet_scoring.py
```

Move these definitions from `persistence.py`:

```python
magnet_identity.py:
extract_info_hash
build_magnet_dedupe_key

magnet_scoring.py:
parse_size_mb  # rename from _parse_size_mb
has_chinese_sub  # rename from _has_chinese_sub
compute_magnet_weight
```

Update internal calls to use the public renamed functions.

- [ ] **Step 5: Move movie and magnet persistence helpers**

Create:

```text
backend/app/modules/content/movies/movie_persistence.py
backend/app/modules/content/movies/magnet_persistence.py
backend/app/modules/content/movies/filter_sync.py
```

Move these definitions from `persistence.py`:

```python
movie_persistence.py:
_movie_unique_value
upsert_movie
append_source_task_id

magnet_persistence.py:
_to_float
normalize_magnet  # rename from _normalize_magnet
upsert_magnets
auto_select_best_magnet
upsert_movie_with_magnets

filter_sync.py:
sync_movie_filters
```

Update `magnet_persistence.py` imports:

```python
from backend.app.modules.content.movies.magnet_identity import build_magnet_dedupe_key, extract_info_hash
from backend.app.modules.content.movies.magnet_scoring import compute_magnet_weight, parse_size_mb
from backend.app.modules.content.movies.movie_persistence import upsert_movie
```

- [ ] **Step 6: Convert `persistence.py` to facade**

Replace `backend/app/modules/content/movies/persistence.py` with imports/re-exports:

```python
from __future__ import annotations

from backend.app.modules.content.movies.filter_sync import sync_movie_filters
from backend.app.modules.content.movies.magnet_identity import build_magnet_dedupe_key, extract_info_hash
from backend.app.modules.content.movies.magnet_persistence import (
    auto_select_best_magnet,
    normalize_magnet,
    upsert_magnets,
    upsert_movie_with_magnets,
)
from backend.app.modules.content.movies.magnet_scoring import compute_magnet_weight, has_chinese_sub, parse_size_mb
from backend.app.modules.content.movies.movie_persistence import append_source_task_id, upsert_movie

__all__ = [
    "append_source_task_id",
    "auto_select_best_magnet",
    "build_magnet_dedupe_key",
    "compute_magnet_weight",
    "extract_info_hash",
    "has_chinese_sub",
    "normalize_magnet",
    "parse_size_mb",
    "sync_movie_filters",
    "upsert_magnets",
    "upsert_movie",
    "upsert_movie_with_magnets",
]
```

- [ ] **Step 7: Run movie persistence tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_movie_persistence.py tests/test_content_movies_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Verify duplicate implementations are gone**

Run:

```bash
rg -n "^def |^class " backend/app/modules/content/movies/persistence.py
```

Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/content/movies/magnet_identity.py backend/app/modules/content/movies/magnet_scoring.py backend/app/modules/content/movies/magnet_persistence.py backend/app/modules/content/movies/movie_persistence.py backend/app/modules/content/movies/filter_sync.py backend/app/modules/content/movies/persistence.py backend/tests/test_movie_persistence.py
git commit -m "refactor: split movie persistence helpers"
```

---

### Task 6: Split Movie Storage Status Scan Modules

**Files:**
- Create: `backend/app/modules/content/movies/storage_locations.py`
- Create: `backend/app/modules/content/movies/storage_scan.py`
- Modify: `backend/app/modules/content/movies/storage_status.py`
- Modify: `backend/tests/test_content_movies_api.py`

**Interfaces:**
- Produces:
  - `storage_locations.build_movie_storage_target_folders(db: Session, movie: Movie, config: dict) -> list[dict]`
  - `storage_locations.target_folder_specs_from_subtask(subtask) -> list[dict]`
  - `storage_scan.remote_entry_to_dict(entry, target_folder: str) -> dict`
  - `storage_scan.is_matching_video(movie: Movie, item: dict, config: dict) -> bool`
  - `storage_scan.scan_movie_storage_locations(movie: Movie, provider, config: dict, folders: list[dict], source: str) -> tuple[list[str], list[dict]]`

- [ ] **Step 1: Add storage location/scan regression**

Append to `backend/tests/test_content_movies_api.py`:

```python
def test_storage_scan_ignores_small_non_video_and_provider_errors() -> None:
    from shared.database.models.content import Movie
    from backend.app.modules.content.movies.storage_scan import is_matching_video, scan_movie_storage_locations

    movie = Movie(code="ABC-001", source_name="Movie")
    assert is_matching_video(movie, {"name": "ABC-001.txt", "path": "/Movies/ABC-001.txt", "size": 999999999, "is_dir": False}, {"video_extensions": [".mp4"], "minimum_video_size_mb": 100}) is False
    assert is_matching_video(movie, {"name": "ABC-001.mp4", "path": "/Movies/ABC-001.mp4", "size": 1, "is_dir": False}, {"video_extensions": [".mp4"], "minimum_video_size_mb": 100}) is False

    class Provider:
        def list_files(self, path):
            raise RuntimeError("remote down")

    checked, found = scan_movie_storage_locations(
        movie,
        Provider(),
        {"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        [{"target_folder": "/Movies/A/ABC-001", "storage_location": "A"}],
        "test",
    )
    assert checked == ["/Movies/A/ABC-001"]
    assert found == []
```

- [ ] **Step 2: Run new regression and verify it fails**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py::test_storage_scan_ignores_small_non_video_and_provider_errors -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `storage_locations.py`**

Move from `storage_status.py`:

```python
KNOWN_STORAGE_SUFFIXES
build_movie_storage_target_folders
target_folder_specs_from_subtask
_storage_locations_for_movie
```

Keep imports:

```python
from __future__ import annotations

import uuid
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie
```

- [ ] **Step 4: Create `storage_scan.py`**

Move from `storage_status.py`:

```python
_remote_entry_to_dict -> remote_entry_to_dict
_is_matching_video -> is_matching_video
```

Add:

```python
def scan_movie_storage_locations(movie: Movie, provider, config: dict, folders: list[dict], source: str) -> tuple[list[str], list[dict]]:
    checked_targets: list[str] = []
    found_locations: list[dict] = []
    for folder in folders:
        target_folder = str(folder["target_folder"])
        checked_targets.append(target_folder)
        try:
            entries = provider.list_files(target_folder)
        except Exception:
            entries = []
        for entry in entries:
            item = remote_entry_to_dict(entry, target_folder)
            if is_matching_video(movie, item, config):
                found_locations.append({
                    "path": item["path"],
                    "target_folder": target_folder,
                    "storage_location": str(folder.get("storage_location") or ""),
                    "file_name": item["name"],
                    "size": item["size"],
                    "exists": True,
                    "source": source,
                })
    return checked_targets, found_locations
```

- [ ] **Step 5: Rewire `storage_status.py`**

Import:

```python
from backend.app.modules.content.movies.storage_locations import build_movie_storage_target_folders, target_folder_specs_from_subtask
from backend.app.modules.content.movies.storage_scan import scan_movie_storage_locations
```

In `sync_movie_storage_status`, replace the manual provider loop with:

```python
checked_targets, found_locations = scan_movie_storage_locations(movie, provider, config, folders, source)
```

Keep `normalized_movie_storage_status`, `set_movie_storage_status`, `_dedupe_locations`, constants, and `MovieStorageSyncResult` in `storage_status.py`.

- [ ] **Step 6: Run content movie tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_content_movies_api.py tests/test_movie_delete_service.py -v
```

Expected: PASS.

- [ ] **Step 7: Verify moved scan/location helpers are gone from `storage_status.py`**

Run:

```bash
rg -n "def build_movie_storage_target_folders|def target_folder_specs_from_subtask|def _storage_locations_for_movie|def _remote_entry_to_dict|def _is_matching_video" backend/app/modules/content/movies/storage_status.py
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/content/movies/storage_locations.py backend/app/modules/content/movies/storage_scan.py backend/app/modules/content/movies/storage_status.py backend/tests/test_content_movies_api.py
git commit -m "refactor: split movie storage scan"
```

---

### Task 7: Split Movie List Page Actions And URL Effects

**Files:**
- Create: `frontend/src/pages/content/movies/hooks/useMovieListActions.tsx`
- Create: `frontend/src/pages/content/movies/hooks/useMovieUrlDetail.ts`
- Create: `frontend/src/pages/content/movies/utils/detailFilter.ts`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Modify: `frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts`
- Modify: `frontend/src/pages/content/movies/utils/sort.ts`
- Modify: `frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx`
- Modify: `frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx`

**Interfaces:**
- Produces:
  - `applyDetailFilterClick(args) -> void`
  - `useMovieUrlDetail(showDetail: (id: string) => void) -> void`
  - `useMovieListActions(args)` returns `confirmDeleteMovies`, `handleBatchDelete`, `handleBulkPush`, `handleDetailFilterClick`, `handleResetFilters`

- [ ] **Step 1: Add detail filter utility test**

Append to `frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx`:

```tsx
import { applyDetailFilterClick } from '../utils/detailFilter'

it('applies detail drawer filter values without duplicates', () => {
  const calls: Array<Record<string, unknown>> = []
  const pageCalls: number[] = []

  applyDetailFilterClick({
    field: 'director',
    value: 'Alice',
    form: { selectedDirectors: ['Bob'] },
    closeDetail: () => calls.push({ closed: true }),
    patchForm: (patch) => calls.push(patch),
    setPage: (page) => pageCalls.push(page),
  })

  expect(calls).toContainEqual({ closed: true })
  expect(calls).toContainEqual({ selectedDirectors: ['Bob', 'Alice'] })
  expect(pageCalls).toEqual([1])
})
```

- [ ] **Step 2: Run utility test and verify it fails**

Run:

```bash
cd frontend
npm test -- src/pages/content/movies/__tests__/movie-storage-sync.test.tsx --run
```

Expected: FAIL with missing `detailFilter`.

- [ ] **Step 3: Create `detailFilter.ts`**

Create `frontend/src/pages/content/movies/utils/detailFilter.ts`:

```ts
import { DEFAULT_MOVIE_PAGE } from '../constants'
import type { MovieFilterState } from './movieFilter'

const fieldMap: Record<string, keyof MovieFilterState> = {
  director: 'selectedDirectors',
  maker: 'selectedMakers',
  series: 'selectedSeries',
  actors: 'selectedActors',
  tags: 'selectedTags',
}

export function applyDetailFilterClick({
  closeDetail,
  field,
  form,
  patchForm,
  setPage,
  value,
}: {
  closeDetail: () => void
  field: string
  form: Partial<MovieFilterState>
  patchForm: (patch: Partial<MovieFilterState>) => void
  setPage: (page: number) => void
  value: string
}) {
  closeDetail()
  const stateKey = fieldMap[field]
  if (!stateKey) return
  const current = (form[stateKey] as string[]) || []
  if (!current.includes(value)) {
    patchForm({ [stateKey]: [...current, value] } as Partial<MovieFilterState>)
  }
  setPage(DEFAULT_MOVIE_PAGE)
}
```

- [ ] **Step 4: Create `useMovieUrlDetail.ts`**

Move URL `?id=` handling from `MovieListPage.tsx` to:

```ts
import { useEffect } from 'react'

export function useMovieUrlDetail(showDetail: (movieId: string) => void) {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const movieId = params.get('id')
    if (!movieId) return
    showDetail(movieId)
    const url = new URL(window.location.href)
    url.searchParams.delete('id')
    window.history.replaceState({}, '', url.toString())
  }, [showDetail])
}
```

- [ ] **Step 5: Create `useMovieListActions.tsx`**

Move delete confirmation, bulk push/delete, detail filter click, and reset filters from `MovieListPage.tsx` into `useMovieListActions.tsx`. Keep the current `Modal.confirm`, delete mode labels, warning text, `deleteMovies` call, success message, `list.reload()`, and selected-row clearing behavior.

Required signature:

```ts
export function useMovieListActions(args: {
  config: MovieFilterConfig | undefined
  detail: ReturnType<typeof useMovieDetail>
  filters: ReturnType<typeof useMovieFilters>
  list: ReturnType<typeof useMovieList>
  push: ReturnType<typeof useStoragePush>
}) {
  return { confirmDeleteMovies, handleBatchDelete, handleBulkPush, handleDetailFilterClick, handleResetFilters }
}
```

- [ ] **Step 6: Rewire `MovieListPage.tsx`**

Use:

```ts
useMovieUrlDetail(detail.showDetail)
useMovieListRealtime(list.updateMovie)
const actions = useMovieListActions({ config: configHook.config, detail, filters, list, push })
```

Replace local callbacks with `actions.*`. Import `parseSortDefault` from `./utils/sort` and delete local `parseSortDefault`.

- [ ] **Step 7: Run movie frontend tests**

Run:

```bash
cd frontend
npm test -- src/pages/content/movies/__tests__/movie-delete.test.tsx src/pages/content/movies/__tests__/movie-storage-sync.test.tsx --run
```

Expected: PASS.

- [ ] **Step 8: Verify page no longer owns moved side effects**

Run:

```bash
rg -n "Modal.confirm|window.location.search|subscribeRealtime|function parseSortDefault|fieldMap" frontend/src/pages/content/movies/MovieListPage.tsx
```

Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/hooks/useMovieListActions.tsx frontend/src/pages/content/movies/hooks/useMovieUrlDetail.ts frontend/src/pages/content/movies/hooks/useMovieListRealtime.ts frontend/src/pages/content/movies/utils/detailFilter.ts frontend/src/pages/content/movies/utils/sort.ts frontend/src/pages/content/movies/__tests__/movie-delete.test.tsx frontend/src/pages/content/movies/__tests__/movie-storage-sync.test.tsx
git commit -m "refactor: split movie list page actions"
```

---

### Task 8: Split Storage Subtask Detail And Init Pages

**Files:**
- Create: `frontend/src/pages/storage/tasks/hooks/useStorageSubTaskDetail.ts`
- Create: `frontend/src/pages/storage/tasks/hooks/useStorageSubTaskRealtime.ts`
- Create: `frontend/src/pages/storage/tasks/utils/subtaskStatus.ts`
- Create: `frontend/src/pages/storage/tasks/components/SubtaskInfoCard.tsx`
- Create: `frontend/src/pages/storage/tasks/components/SubtaskFilesCard.tsx`
- Modify: `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`
- Create: `frontend/src/pages/init/hooks/useInitConnectionTests.ts`
- Create: `frontend/src/pages/init/hooks/useInitSubmit.ts`
- Create: `frontend/src/pages/init/components/PostgresConfigSection.tsx`
- Create: `frontend/src/pages/init/components/RedisConfigSection.tsx`
- Create: `frontend/src/pages/init/utils/initParams.ts`
- Create: `frontend/src/pages/init/__tests__/init-page.test.tsx`
- Modify: `frontend/src/pages/init/InitPage.tsx`

**Interfaces:**
- Produces:
  - `useStorageSubTaskDetail(id: string | undefined)`
  - `useStorageSubTaskRealtime(args) -> void`
  - `statusLabels`, `levelColors`, `stepOrder`, `stepLabels`, `logsForStep`, `stepColor`, `formatTime`
  - `getPgTestParams(values: InitConfigRequest) -> PostgresTestParams`
  - `getRedisTestParams(values: InitConfigRequest) -> RedisTestParams`
  - `useInitConnectionTests(form)`
  - `useInitSubmit()`

- [ ] **Step 1: Move storage subtask utilities**

Create `frontend/src/pages/storage/tasks/utils/subtaskStatus.ts` by moving these definitions from `StorageSubTaskDetailPage.tsx`:

```ts
statusLabels
levelColors
stepOrder
stepLabels
logsForStep
stepColor
formatTime
```

Update existing `SubtaskStepTimeline` and `SubtaskLogList` imports to use this utility file where applicable.

- [ ] **Step 2: Extract storage subtask hooks**

Create `useStorageSubTaskDetail.ts` with current `subtask`, `logs`, `loading`, `fetchSubtask`, `fetchLogs`, and reset-on-id-change behavior.

Create `useStorageSubTaskRealtime.ts` with subscriptions:

```ts
storage.sub.updated
storage.sub.log.appended
system.resync_required
```

Preserve current event filters: subtask payload ID must match `id`; log event `resource_id` must match `id`.

- [ ] **Step 3: Extract storage subtask cards**

Create:

```text
frontend/src/pages/storage/tasks/components/SubtaskInfoCard.tsx
frontend/src/pages/storage/tasks/components/SubtaskFilesCard.tsx
```

Move the basic information, target locations, moved files, and skipped files card JSX from `StorageSubTaskDetailPage.tsx`. Keep card titles, labels, empty states, JSON display, and styles unchanged.

- [ ] **Step 4: Rewire `StorageSubTaskDetailPage.tsx`**

The page should compose:

```tsx
const detail = useStorageSubTaskDetail(id)
useStorageSubTaskRealtime({
  fetchLogs: detail.fetchLogs,
  fetchSubtask: detail.fetchSubtask,
  id,
  setLogs: detail.setLogs,
  setSubtask: detail.setSubtask,
})
```

Render `SubtaskInfoCard`, `SubtaskFilesCard`, `SubtaskStepTimeline`, and `SubtaskLogList`.

- [ ] **Step 5: Create init params utility**

Create `frontend/src/pages/init/utils/initParams.ts`:

```ts
import type { InitConfigRequest, PostgresTestParams, RedisTestParams } from '@/api/init/types'

export function getPgTestParams(values: InitConfigRequest): PostgresTestParams {
  return {
    host: values.databaseHost,
    port: values.databasePort,
    database: values.databaseName,
    user: values.databaseUser,
    password: values.databasePassword,
    connect_timeout: values.postgresConnectTimeout,
  }
}

export function getRedisTestParams(values: InitConfigRequest): RedisTestParams {
  return {
    host: values.redisHost,
    port: values.redisPort,
    password: values.redisPassword,
    socket_timeout: values.redisSocketTimeout,
    connect_timeout: values.redisConnectTimeout,
  }
}
```

- [ ] **Step 6: Extract init hooks and sections**

Create `useInitConnectionTests.ts` with `pgTesting`, `redisTesting`, `pgResult`, `redisResult`, `handleTestPg`, and `handleTestRedis`.

Create `useInitSubmit.ts` with save-before-test workflow. Preserve current behavior:

- run PostgreSQL and Redis tests in parallel;
- show joined error messages when either fails;
- call `saveInitConfig(values)` only when both pass;
- show success message;
- redirect to `/login` after 1500 ms.

Create `PostgresConfigSection.tsx` and `RedisConfigSection.tsx` by moving current form sections and test bars. Keep labels, initial field names, validation rules, placeholders, and button text unchanged.

- [ ] **Step 7: Add init page tests**

Create `frontend/src/pages/init/__tests__/init-page.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { getPgTestParams, getRedisTestParams } from '../utils/initParams'

describe('init params', () => {
  it('maps form values to postgres and redis test payloads', () => {
    const values = {
      databaseHost: 'localhost',
      databasePort: 5432,
      databaseName: 'mediaforge',
      databaseUser: 'admin',
      databasePassword: 'secret',
      postgresConnectTimeout: 5,
      postgresPoolSize: 5,
      postgresMaxOverflow: 10,
      postgresMaxRetries: 3,
      postgresRetryDelay: 2,
      redisHost: '127.0.0.1',
      redisPort: 6379,
      redisPassword: '',
      redisSocketTimeout: 5,
      redisConnectTimeout: 6,
      redisMaxConnections: 10,
    }

    expect(getPgTestParams(values)).toEqual({
      host: 'localhost',
      port: 5432,
      database: 'mediaforge',
      user: 'admin',
      password: 'secret',
      connect_timeout: 5,
    })
    expect(getRedisTestParams(values)).toEqual({
      host: '127.0.0.1',
      port: 6379,
      password: '',
      socket_timeout: 5,
      connect_timeout: 6,
    })
  })
})
```

- [ ] **Step 8: Run frontend focused tests**

Run:

```bash
cd frontend
npm test -- src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx src/pages/init/__tests__/init-page.test.tsx --run
```

Expected: PASS.

- [ ] **Step 9: Verify pages no longer own moved logic**

Run:

```bash
rg -n "connectRealtime|subscribeRealtime|const statusLabels|const levelColors|function logsForStep|function stepColor|function formatTime" frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx
rg -n "const getPgTestParams|const getRedisTestParams|const handleTestPg|const handleTestRedis|const handleFinish" frontend/src/pages/init/InitPage.tsx
```

Expected: no output.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx frontend/src/pages/storage/tasks/hooks/useStorageSubTaskDetail.ts frontend/src/pages/storage/tasks/hooks/useStorageSubTaskRealtime.ts frontend/src/pages/storage/tasks/utils/subtaskStatus.ts frontend/src/pages/storage/tasks/components/SubtaskInfoCard.tsx frontend/src/pages/storage/tasks/components/SubtaskFilesCard.tsx frontend/src/pages/init/InitPage.tsx frontend/src/pages/init/hooks/useInitConnectionTests.ts frontend/src/pages/init/hooks/useInitSubmit.ts frontend/src/pages/init/components/PostgresConfigSection.tsx frontend/src/pages/init/components/RedisConfigSection.tsx frontend/src/pages/init/utils/initParams.ts frontend/src/pages/init/__tests__/init-page.test.tsx frontend/src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx
git commit -m "refactor: split remaining heavy frontend pages"
```

---

### Task 9: Final Verification And Dead Code Audit

**Files:**
- Verify all files touched by Tasks 1-8.

**Interfaces:**
- Consumes all interfaces from previous tasks.
- Produces final confidence that graph filtering, backend boundaries, frontend boundaries, and dead-code cleanup policy are satisfied.

- [ ] **Step 1: Run graphify hotspot analyzer**

Run:

```bash
source .venv/bin/activate
python scripts/analyze_graphify_hotspots.py graphify-out/graph.json --top 20
```

Expected:
- stale graph warning is printed if graph was not regenerated;
- output excludes `clouddrive_pb2_grpc.py`;
- output excludes test files.

- [ ] **Step 2: Run backend focused tests**

Run:

```bash
source .venv/bin/activate
cd backend
python -m pytest tests/test_graphify_hotspots.py tests/test_crawler_worker_service.py tests/test_crawler_engine.py tests/test_storage_worker_pipeline.py tests/test_storage_worker_service.py tests/test_movie_persistence.py tests/test_content_movies_api.py tests/test_movie_delete_service.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused tests**

Run:

```bash
cd frontend
npm test -- src/pages/content/movies/__tests__/movie-delete.test.tsx src/pages/content/movies/__tests__/movie-storage-sync.test.tsx src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx src/pages/init/__tests__/init-page.test.tsx --run
```

Expected: PASS.

- [ ] **Step 4: Run frontend lint and build**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: both PASS.

- [ ] **Step 5: Run boundary checks**

Run:

```bash
rg -n "def on_|def db_check_callback|def log_callback|sync_movie_filters|count_run_detail_tasks|reset_unfinished_detail_tasks_to_pending" backend/app/modules/crawler/runtime/executor.py
rg -n "submit_offline_download|poll_downloaded_video_files|recover_existing_downloaded_video_files|find_existing_target_files|copy_existing_target_to_missing_targets|scan_found_files|classify_scanned_files|rename_selected_videos|move_renamed_videos|verify_moved_files" backend/app/modules/storage/worker/steps.py
rg -n "^def |^class " backend/app/modules/content/movies/persistence.py
rg -n "def build_movie_storage_target_folders|def target_folder_specs_from_subtask|def _storage_locations_for_movie|def _remote_entry_to_dict|def _is_matching_video" backend/app/modules/content/movies/storage_status.py
rg -n "Modal.confirm|window.location.search|subscribeRealtime|function parseSortDefault|fieldMap" frontend/src/pages/content/movies/MovieListPage.tsx
rg -n "connectRealtime|subscribeRealtime|const statusLabels|const levelColors|function logsForStep|function stepColor|function formatTime" frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx
rg -n "const getPgTestParams|const getRedisTestParams|const handleTestPg|const handleTestRedis|const handleFinish" frontend/src/pages/init/InitPage.tsx
```

Expected: no output, except import-only lines that are still required for compatibility. Remove unused imports before finishing.

- [ ] **Step 6: Ensure generated and analysis artifacts are not staged**

Run:

```bash
git status --short
```

Expected:
- no `graphify-out/` files staged or modified for commit;
- no generated protobuf/gRPC files staged;
- no unrelated untracked plan files staged.
