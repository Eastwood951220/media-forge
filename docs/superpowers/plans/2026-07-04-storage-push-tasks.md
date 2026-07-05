# Storage Push Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Redis-backed CloudDrive2 storage push main tasks and subtasks, with movie-list push actions, realtime status updates, magnet fallback, and storage task pages.

**Architecture:** Backend adds PostgreSQL main/subtask models, a storage task API, Redis runtime state, and a CloudDrive2 worker that reuses the original Jav Scrapling pipeline concepts while fitting Media Forge's current module layout. Frontend adds storage task APIs/pages and connects movie list, storage task list, task detail, and subtask detail to the existing `/api/events/stream` realtime channel.

**Tech Stack:** Python 3.12+, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Redis 8, Pytest, React 19, TypeScript 6, Vite 8, Ant Design 6, TanStack Router 1.x, Vitest 3.

## Global Constraints

- Keep scope anchored to migrating, preserving, improving, or integrating existing Jav Scrapling storage behavior.
- Do not add unrelated media sources, storage providers, product modules, or speculative features.
- All storage work is dispatched through Redis; PostgreSQL is the source of truth for persisted task state.
- Every single or batch push creates a main task.
- Every selected movie creates exactly one subtask, including skipped subtasks.
- Main task alias defaults to `云存储_YYYYMMDDHHMMSS_<unique_sequence>`.
- Subtask download path is `download_root_folder/storage_<subtask_id>`.
- Stop does not interrupt the currently executing subtask.
- `single` mode stores one final copy; single-row push lets the user choose a target `storage_location`, batch defaults to each movie's first usable location.
- `multiple` mode requires every usable `storage_location` from `source_task_ids` to contain final files.
- Use CloudDrive2 `GetSearchResults(SearchRequest)` and `GetOriginalPath(FileRequest)` for existing-file recovery, then fall back to recursive `GetSubFiles`.
- Filename suffixes: tags containing `字幕`, `中文字幕`, `中字`, or `中文` add `-C`; tags containing `破解`, `无码`, or `无码破解` add `-U`; both add `-UC`.
- Multi-file videos use `-CD1`, `-CD2`, `-CD3`.
- Realtime updates use `/api/events/stream`.

---

## File Structure

Backend model and migration:

- Create `backend/app/models/storage_task.py`: SQLAlchemy `StorageMainTask` and `StorageSubTask`.
- Modify `backend/app/models/__init__.py`: export storage task models.
- Create `backend/alembic/versions/20260704_0001_add_storage_tasks.py`: tables, indexes, config field migration.
- Modify `backend/app/modules/storage/config/schemas.py`: add `magnet_max_attempts_per_subtask`.
- Create `backend/tests/test_storage_task_models.py`: model, migration-facing behavior, config default tests.

Backend CloudDrive2 and pure policies:

- Modify `shared/integrations/storage_providers/clouddrive2/client.py`: add `search_files` and `get_original_path`.
- Modify `shared/integrations/storage_providers/clouddrive2/gateway.py`: expose gateway methods and protocol signatures.
- Create `backend/app/modules/storage/tasks/policies.py`: alias, target locations, magnet ordering, filename naming, disc parsing, final folder derivation.
- Create `backend/tests/test_storage_task_policies.py`: pure policy tests.
- Create `backend/tests/test_clouddrive_search_gateway.py`: fake client tests for search and original path mapping.

Backend task API:

- Create `backend/app/modules/storage/tasks/__init__.py`: package marker.
- Create `backend/app/modules/storage/tasks/schemas.py`: Pydantic request/response types.
- Create `backend/app/modules/storage/tasks/repository.py`: query/update helpers for main and subtask models.
- Create `backend/app/modules/storage/tasks/service.py`: task creation, skip classification, count recomputation, stop/restart.
- Create `backend/app/modules/storage/tasks/router.py`: authenticated REST endpoints.
- Modify `backend/app/core/dependencies.py`: dependency factory for storage task service.
- Modify `backend/app/main.py`: include storage task router and startup cleanup.
- Create `backend/tests/test_storage_tasks_api.py`: API and service tests.

Backend runtime, events, and worker:

- Create `backend/app/modules/storage/runtime/__init__.py`: package marker.
- Create `backend/app/modules/storage/runtime/redis_state.py`: Redis queue/current/stop state.
- Create `backend/app/modules/storage/tasks/events.py`: realtime event publishers.
- Create `backend/app/modules/storage/tasks/logs.py`: JSONL task log writer/reader.
- Create `backend/app/modules/storage/worker/__init__.py`: package marker.
- Create `backend/app/modules/storage/worker/context.py`: worker context and fakeable provider interface use.
- Create `backend/app/modules/storage/worker/file_finder.py`: existing-file recovery with search and recursive fallback.
- Create `backend/app/modules/storage/worker/steps.py`: pipeline step functions.
- Create `backend/app/modules/storage/worker/runner.py`: main-task worker loop, subtask execution, startup cleanup.
- Create `backend/tests/test_storage_runtime_redis.py`: Redis runtime tests.
- Create `backend/tests/test_storage_worker_pipeline.py`: fake provider pipeline tests.
- Create `backend/tests/test_storage_realtime_events.py`: event publishing tests.

Frontend APIs and realtime types:

- Create `frontend/src/api/storage/storageTasks/types.ts`: task API types.
- Create `frontend/src/api/storage/storageTasks/index.ts`: request functions.
- Modify `frontend/src/realtime/types.ts`: storage realtime event payloads and names.
- Modify `frontend/src/realtime/eventSourceClient.ts`: register storage events.
- Modify `frontend/src/api/movie/types.ts`: add storage push-related shape where missing.
- Create `frontend/src/pages/content/movies/hooks/useStoragePush.ts`: push modal and submit state.
- Modify `frontend/src/pages/content/movies/MovieListPage.tsx`: wire row and bulk push.
- Modify `frontend/src/pages/content/movies/components/MovieTable.tsx`: add push actions and live storage status.
- Create `frontend/src/pages/content/movies/components/StoragePushModal.tsx`: single/batch confirmation modal.

Frontend storage task pages:

- Create `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`.
- Create `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`.
- Create `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`.
- Create `frontend/src/pages/storage/tasks/StorageTasks.module.less`.
- Modify `frontend/src/routes/index.tsx`: add storage task routes.
- Modify `frontend/src/layout/Sidebar/index.tsx`: add `存储任务` menu item.

Tests:

- Create `frontend/src/pages/content/movies/__tests__/storage-push-modal.test.tsx`.
- Create `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`.
- Create `frontend/src/realtime/__tests__/storage-realtime-events.test.ts`.

---

### Task 1: Storage Task Models, Migration, and Config Field

**Files:**
- Create: `backend/app/models/storage_task.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260704_0001_add_storage_tasks.py`
- Modify: `backend/app/modules/storage/config/schemas.py`
- Create: `backend/tests/test_storage_task_models.py`

**Interfaces:**
- Produces: `StorageMainTask`, `StorageSubTask`.
- Produces: `StorageConfig.magnet_max_attempts_per_subtask: int`.
- Later tasks import models from `backend.app.models.storage_task`.

- [ ] **Step 1: Write the failing model and config tests**

Create `backend/tests/test_storage_task_models.py`:

```python
import uuid

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.config.schemas import StorageConfig


def test_storage_config_has_magnet_attempt_limit() -> None:
    config = StorageConfig()
    assert config.magnet_max_attempts_per_subtask == 3


def test_storage_main_task_defaults() -> None:
    task = StorageMainTask(
        alias="云存储_20260704112233_0001",
        display_name="云存储_20260704112233_0001",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        created_by=uuid.uuid4(),
    )

    assert task.success_count == 0
    assert task.failed_count == 0
    assert task.skipped_count == 0
    assert task.config_snapshot == {}


def test_storage_sub_task_json_defaults() -> None:
    subtask = StorageSubTask(
        main_task_id=uuid.uuid4(),
        movie_id=uuid.uuid4(),
        movie_code="ABC-123",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="multiple",
    )

    assert subtask.target_locations == []
    assert subtask.target_paths == []
    assert subtask.magnet_attempts == []
    assert subtask.result == {}
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_task_models.py -v
```

Expected: FAIL because `backend.app.models.storage_task` does not exist.

- [ ] **Step 3: Create SQLAlchemy models**

Create `backend/app/models/storage_task.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class StorageMainTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "storage_main_tasks"
    __table_args__ = (
        Index("idx_storage_main_status_created", "status", "created_at"),
        Index("idx_storage_main_created_by_status", "created_by", "status"),
    )

    alias: Mapped[str] = mapped_column(String(240), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_snapshot: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtasks: Mapped[list["StorageSubTask"]] = relationship(
        back_populates="main_task",
        cascade="all, delete-orphan",
        order_by="StorageSubTask.created_at",
        lazy="selectin",
    )


class StorageSubTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "storage_sub_tasks"
    __table_args__ = (
        Index("idx_storage_sub_main_status", "main_task_id", "status"),
        Index("idx_storage_sub_movie_status", "movie_id", "status"),
        Index("idx_storage_sub_created", "created_at"),
    )

    main_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("storage_main_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    movie_code: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    movie_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(50), nullable=False, default="prepare")
    storage_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_storage_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_locations: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    download_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_paths: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    magnet_attempts: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    current_magnet_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    current_magnet_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    renamed_files: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    moved_files: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    skipped_files: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    result: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    skip_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    main_task: Mapped[StorageMainTask] = relationship(back_populates="subtasks")
```

- [ ] **Step 4: Export models**

Modify `backend/app/models/__init__.py` to import and export:

```python
from backend.app.models.storage_task import StorageMainTask, StorageSubTask
```

Add `"StorageMainTask"` and `"StorageSubTask"` to `__all__`.

- [ ] **Step 5: Add config field**

In `backend/app/modules/storage/config/schemas.py`, add to `StorageConfig`:

```python
    magnet_max_attempts_per_subtask: int = Field(default=3, ge=1)
```

Add to `StorageConfigUpdate`:

```python
    magnet_max_attempts_per_subtask: int | None = Field(default=None, ge=1)
```

- [ ] **Step 6: Add Alembic migration**

Create `backend/alembic/versions/20260704_0001_add_storage_tasks.py`:

```python
"""add storage tasks

Revision ID: 20260704_0001
Revises: 20260703_0003
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql
from alembic import op

revision: str = "20260704_0001"
down_revision: str | None = "20260703_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = sa.JSON() if bind.dialect.name == "sqlite" else sa.dialects.postgresql.JSONB()
    json_empty = sa.text("'{}'") if bind.dialect.name == "sqlite" else sa.text("'{}'::jsonb")
    json_list = sa.text("'[]'") if bind.dialect.name == "sqlite" else sa.text("'[]'::jsonb")

    op.create_table(
        "storage_main_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=240), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("storage_mode", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_snapshot", json_type, nullable=False, server_default=json_empty),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_storage_main_status_created", "storage_main_tasks", ["status", "created_at"])
    op.create_index("idx_storage_main_created_by_status", "storage_main_tasks", ["created_by", "status"])

    op.create_table(
        "storage_sub_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("main_task_id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("movie_code", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("movie_title", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("step", sa.String(length=50), nullable=False, server_default="prepare"),
        sa.Column("storage_mode", sa.String(length=30), nullable=False),
        sa.Column("selected_storage_location", sa.Text(), nullable=True),
        sa.Column("target_locations", json_type, nullable=False, server_default=json_list),
        sa.Column("download_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_paths", json_type, nullable=False, server_default=json_list),
        sa.Column("magnet_attempts", json_type, nullable=False, server_default=json_list),
        sa.Column("current_magnet_id", sa.Uuid(), nullable=True),
        sa.Column("current_magnet_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("renamed_files", json_type, nullable=False, server_default=json_list),
        sa.Column("moved_files", json_type, nullable=False, server_default=json_list),
        sa.Column("skipped_files", json_type, nullable=False, server_default=json_list),
        sa.Column("result", json_type, nullable=False, server_default=json_empty),
        sa.Column("skip_reason", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["main_task_id"], ["storage_main_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_storage_sub_main_status", "storage_sub_tasks", ["main_task_id", "status"])
    op.create_index("idx_storage_sub_movie_status", "storage_sub_tasks", ["movie_id", "status"])
    op.create_index("idx_storage_sub_created", "storage_sub_tasks", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_storage_sub_created", table_name="storage_sub_tasks")
    op.drop_index("idx_storage_sub_movie_status", table_name="storage_sub_tasks")
    op.drop_index("idx_storage_sub_main_status", table_name="storage_sub_tasks")
    op.drop_table("storage_sub_tasks")
    op.drop_index("idx_storage_main_created_by_status", table_name="storage_main_tasks")
    op.drop_index("idx_storage_main_status_created", table_name="storage_main_tasks")
    op.drop_table("storage_main_tasks")
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_task_models.py backend/tests/test_storage_config_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/storage_task.py backend/app/models/__init__.py backend/alembic/versions/20260704_0001_add_storage_tasks.py backend/app/modules/storage/config/schemas.py backend/tests/test_storage_task_models.py
git commit -m "feat: add storage task models"
```

---

### Task 2: CloudDrive2 Search Gateway and Pure Storage Policies

**Files:**
- Modify: `shared/integrations/storage_providers/clouddrive2/client.py`
- Modify: `shared/integrations/storage_providers/clouddrive2/gateway.py`
- Create: `backend/app/modules/storage/tasks/policies.py`
- Create: `backend/tests/test_storage_task_policies.py`
- Create: `backend/tests/test_clouddrive_search_gateway.py`

**Interfaces:**
- Produces: `CloudDrive2Gateway.search_files(search_term: str, path: str = "/", force_refresh: bool = False, fuzzy_match: bool = False) -> list[RemoteFile]`.
- Produces: `CloudDrive2Gateway.get_original_path(path: str) -> str`.
- Produces: `generate_default_alias(now: datetime, sequence: int) -> str`.
- Produces: `order_magnet_candidates(magnets: list[dict], max_attempts: int) -> list[dict]`.
- Produces: `build_video_filename(movie_code: str, original_name: str, tags: list[str], index: int, total: int) -> str`.
- Produces: `code_folder_from_filename(filename: str) -> str`.

- [ ] **Step 1: Write failing policy tests**

Create `backend/tests/test_storage_task_policies.py`:

```python
from datetime import datetime

from backend.app.modules.storage.tasks.policies import (
    build_video_filename,
    code_folder_from_filename,
    generate_default_alias,
    order_magnet_candidates,
)


def test_generate_default_alias() -> None:
    alias = generate_default_alias(datetime(2026, 7, 4, 11, 22, 33), 7)
    assert alias == "云存储_20260704112233_0007"


def test_order_magnet_candidates_selected_first_then_weight() -> None:
    magnets = [
        {"id": "low", "weight": 1, "selected": False},
        {"id": "selected", "weight": 2, "selected": True},
        {"id": "high", "weight": 99, "selected": False},
    ]

    assert [m["id"] for m in order_magnet_candidates(magnets, max_attempts=3)] == [
        "selected",
        "high",
        "low",
    ]


def test_order_magnet_candidates_limits_attempts() -> None:
    magnets = [
        {"id": "selected", "weight": 1, "selected": True},
        {"id": "high", "weight": 99, "selected": False},
        {"id": "middle", "weight": 50, "selected": False},
    ]

    assert [m["id"] for m in order_magnet_candidates(magnets, max_attempts=2)] == [
        "selected",
        "high",
    ]


def test_build_video_filename_uppercase_suffix_and_disc() -> None:
    filename = build_video_filename(
        movie_code="abc-123",
        original_name="XXX.part2.mp4",
        tags=["中文字幕", "无码破解"],
        index=1,
        total=3,
    )

    assert filename == "ABC-123-UC-CD2.mp4"
    assert code_folder_from_filename(filename) == "ABC-123-UC"


def test_build_video_filename_single_chinese() -> None:
    assert build_video_filename("abc-123", "movie.mkv", ["中字"], 0, 1) == "ABC-123-C.mkv"
```

- [ ] **Step 2: Write failing CloudDrive2 gateway tests**

Create `backend/tests/test_clouddrive_search_gateway.py`:

```python
from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway


class FakeClient:
    def __init__(self) -> None:
        self.search_calls = []
        self.original_path_calls = []

    def search_files(self, search_term: str, path: str = "/", force_refresh: bool = False, fuzzy_match: bool = False):
        self.search_calls.append((search_term, path, force_refresh, fuzzy_match))
        return []

    def get_original_path(self, path: str):
        self.original_path_calls.append(path)

        class Result:
            result = "/Movies/ABC-123/ABC-123-C.mp4"

        return Result()


def test_gateway_search_files_delegates_to_client() -> None:
    client = FakeClient()
    gateway = CloudDrive2Gateway(client)

    assert gateway.search_files("ABC-123", "/Downloads", True, True) == []
    assert client.search_calls == [("ABC-123", "/Downloads", True, True)]


def test_gateway_get_original_path_returns_string_result() -> None:
    client = FakeClient()
    gateway = CloudDrive2Gateway(client)

    assert gateway.get_original_path("/Search/ABC-123-C.mp4") == "/Movies/ABC-123/ABC-123-C.mp4"
```

- [ ] **Step 3: Run focused tests and verify failure**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_task_policies.py backend/tests/test_clouddrive_search_gateway.py -v
```

Expected: FAIL because policy module and gateway methods do not exist.

- [ ] **Step 4: Implement pure policy functions**

Create `backend/app/modules/storage/tasks/policies.py` with these functions:

```python
from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

CHINESE_TAG_KEYWORDS = ("字幕", "中文字幕", "中字", "中文")
UNCENSORED_TAG_KEYWORDS = ("破解", "无码", "无码破解")


def generate_default_alias(now: datetime, sequence: int) -> str:
    return f"云存储_{now.strftime('%Y%m%d%H%M%S')}_{sequence:04d}"


def order_magnet_candidates(magnets: list[dict], max_attempts: int) -> list[dict]:
    selected = [m for m in magnets if m.get("selected")]
    selected_first = selected[:1]
    selected_ids = {m.get("id") for m in selected_first}
    remaining = [m for m in magnets if m.get("id") not in selected_ids]
    remaining.sort(key=lambda item: int(item.get("weight") or 0), reverse=True)
    return [*selected_first, *remaining][:max_attempts]


def derive_code_suffix(tags: list[str]) -> str:
    has_chinese = any(keyword in tag for tag in tags for keyword in CHINESE_TAG_KEYWORDS)
    has_uncensored = any(keyword in tag for tag in tags for keyword in UNCENSORED_TAG_KEYWORDS)
    if has_chinese and has_uncensored:
        return "-UC"
    if has_chinese:
        return "-C"
    if has_uncensored:
        return "-U"
    return ""


def infer_disc_number(original_name: str, index: int) -> int:
    stem = PurePosixPath(original_name).stem
    match = re.search(r"(?:part|cd|disc)[_.\\-\\s]?0*(\\d+)", stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    letter = re.search(r"(?:^|[_.\\-\\s])([ABC])(?:$|[_.\\-\\s])", stem, re.IGNORECASE)
    if letter:
        return ord(letter.group(1).upper()) - ord("A") + 1
    return index + 1


def build_video_filename(movie_code: str, original_name: str, tags: list[str], index: int, total: int) -> str:
    ext = PurePosixPath(original_name).suffix
    base = f"{movie_code.upper()}{derive_code_suffix(tags)}"
    if total <= 1:
        return f"{base}{ext}"
    return f"{base}-CD{infer_disc_number(original_name, index)}{ext}"


def code_folder_from_filename(filename: str) -> str:
    stem = PurePosixPath(filename).stem
    return re.sub(r"-CD\\d+$", "", stem, flags=re.IGNORECASE)
```

- [ ] **Step 5: Add client methods**

In `shared/integrations/storage_providers/clouddrive2/client.py`, add methods using the generated proto names already present in the repo:

```python
    def search_files(self, search_term: str, path: str = "/", force_refresh: bool = False, fuzzy_match: bool = False):
        request = clouddrive_pb2.SearchRequest(
            searchFor=search_term,
            path=path,
            forceRefresh=force_refresh,
            fuzzyMatch=fuzzy_match,
        )
        metadata = self._create_authorized_metadata()
        files = []
        for response in self.stub.GetSearchResults(request, metadata=metadata):
            files.extend(response.subFiles)
        return files

    def get_original_path(self, path: str):
        request = clouddrive_pb2.FileRequest(path=path)
        metadata = self._create_authorized_metadata()
        return self.stub.GetOriginalPath(request, metadata=metadata)
```

- [ ] **Step 6: Add gateway protocol and implementation methods**

In `shared/integrations/storage_providers/clouddrive2/gateway.py`, add to `StorageProvider`:

```python
    def search_files(
        self,
        search_term: str,
        path: str = "/",
        force_refresh: bool = False,
        fuzzy_match: bool = False,
    ) -> list[RemoteFile]:
        raise NotImplementedError

    def get_original_path(self, path: str) -> str:
        raise NotImplementedError
```

Add to `CloudDrive2Gateway`:

```python
    def search_files(
        self,
        search_term: str,
        path: str = "/",
        force_refresh: bool = False,
        fuzzy_match: bool = False,
    ) -> list[RemoteFile]:
        return [
            map_remote_file(file_obj)
            for file_obj in self.client.search_files(search_term, path, force_refresh, fuzzy_match)
        ]

    def get_original_path(self, path: str) -> str:
        result = self.client.get_original_path(path)
        return str(getattr(result, "result", "") or "")
```

- [ ] **Step 7: Run focused tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_task_policies.py backend/tests/test_clouddrive_search_gateway.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add shared/integrations/storage_providers/clouddrive2/client.py shared/integrations/storage_providers/clouddrive2/gateway.py backend/app/modules/storage/tasks/policies.py backend/tests/test_storage_task_policies.py backend/tests/test_clouddrive_search_gateway.py
git commit -m "feat: add storage task policies"
```

---

### Task 3: Storage Task Creation API

**Files:**
- Create: `backend/app/modules/storage/tasks/__init__.py`
- Create: `backend/app/modules/storage/tasks/schemas.py`
- Create: `backend/app/modules/storage/tasks/repository.py`
- Create: `backend/app/modules/storage/tasks/service.py`
- Create: `backend/app/modules/storage/tasks/router.py`
- Modify: `backend/app/core/dependencies.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_storage_tasks_api.py`

**Interfaces:**
- Consumes: `StorageMainTask`, `StorageSubTask`, `StorageConfig`, `generate_default_alias`, `order_magnet_candidates`.
- Produces: `StorageTaskService.create_single_push(body: StorageSinglePushRequest, user_id: uuid.UUID) -> StorageMainTask`.
- Produces: `StorageTaskService.create_batch_push(body: StorageBatchPushRequest, user_id: uuid.UUID) -> StorageMainTask`.
- Produces: REST endpoints under `/api/storage/tasks`.

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_storage_tasks_api.py` with tests that use the existing `client`, `auth_headers`, and database fixtures from `backend/tests/conftest.py`:

```python
import uuid

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie, MovieMagnet


def _movie_with_source_and_magnet(db, owner_id, *, code="abc-123", location="A"):
    crawl_task = CrawlTask(name=f"task-{code}", storage_location=location, owner_id=owner_id)
    movie = Movie(code=code, source_name=f"title-{code}", source_task_ids=[crawl_task.id])
    magnet = MovieMagnet(
        movie=movie,
        magnet_url=f"magnet:?xt=urn:btih:{uuid.uuid4().hex}",
        dedupe_key=uuid.uuid4().hex,
        name=f"{code}.mp4",
        tags=["中字"],
        weight=50,
        selected=True,
    )
    db.add_all([crawl_task, movie, magnet])
    db.flush()
    movie.source_task_ids = [crawl_task.id]
    db.commit()
    return movie


def test_single_push_creates_main_and_subtask(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id)

    response = client.post(
        "/api/storage/tasks/push",
        json={
            "movie_id": str(movie.id),
            "storage_mode": "single",
            "selected_storage_location": "A",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source"] == "single"
    assert payload["storage_mode"] == "single"
    assert payload["total_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["alias"].startswith("云存储_")


def test_batch_push_creates_skipped_subtask_for_missing_magnet(client, db_session, auth_headers, test_user):
    crawl_task = CrawlTask(name="task-empty", storage_location="A", owner_id=test_user.id)
    movie = Movie(code="abc-999", source_name="empty", source_task_ids=[])
    db_session.add_all([crawl_task, movie])
    db_session.flush()
    movie.source_task_ids = [crawl_task.id]
    db_session.commit()

    response = client.post(
        "/api/storage/tasks/batch",
        json={"movie_ids": [str(movie.id)], "storage_mode": "single"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_count"] == 1
    assert payload["skipped_count"] == 1
```

- [ ] **Step 2: Run tests and verify failure**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_tasks_api.py -v
```

Expected: FAIL because the storage task routes do not exist.

- [ ] **Step 3: Create schemas**

Create `backend/app/modules/storage/tasks/schemas.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StorageSinglePushRequest(BaseModel):
    movie_id: UUID
    alias: str | None = Field(default=None, max_length=240)
    storage_mode: str = "single"
    selected_storage_location: str | None = Field(default=None, max_length=500)


class StorageBatchPushRequest(BaseModel):
    movie_ids: list[UUID]
    alias: str | None = Field(default=None, max_length=240)
    storage_mode: str = "single"


class StorageMainTaskResponse(BaseModel):
    id: str
    alias: str
    display_name: str
    source: str
    storage_mode: str
    status: str
    total_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
```

- [ ] **Step 4: Create repository helpers**

Create `backend/app/modules/storage/tasks/repository.py` with:

```python
from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask


class StorageTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_main(self, task_id: uuid.UUID) -> StorageMainTask | None:
        return self.db.get(StorageMainTask, task_id)

    def count_today_main_tasks(self) -> int:
        return int(self.db.query(func.count(StorageMainTask.id)).scalar() or 0)

    def recompute_counts(self, main_task: StorageMainTask) -> None:
        subtasks = list(main_task.subtasks or [])
        main_task.total_count = len(subtasks)
        main_task.success_count = sum(1 for task in subtasks if task.status == "completed")
        main_task.failed_count = sum(1 for task in subtasks if task.status == "failed")
        main_task.skipped_count = sum(1 for task in subtasks if task.status == "skipped")
```

- [ ] **Step 5: Create service with creation and skip classification**

Create `backend/app/modules/storage/tasks/service.py` implementing these public methods and helpers:

```python
class StorageTaskService:
    def __init__(self, db: Session, config_service: StorageConfigService, runtime: StorageRuntimeState | None = None) -> None:
        self.db = db
        self.config_service = config_service
        self.runtime = runtime
        self.repository = StorageTaskRepository(db)

    def create_single_push(self, body: StorageSinglePushRequest, user_id: uuid.UUID) -> StorageMainTask:
        return self._create_main_task(
            movie_ids=[body.movie_id],
            user_id=user_id,
            source="single",
            alias=body.alias,
            storage_mode=body.storage_mode,
            selected_storage_location=body.selected_storage_location,
        )

    def create_batch_push(self, body: StorageBatchPushRequest, user_id: uuid.UUID) -> StorageMainTask:
        return self._create_main_task(
            movie_ids=body.movie_ids,
            user_id=user_id,
            source="batch",
            alias=body.alias,
            storage_mode=body.storage_mode,
            selected_storage_location=None,
        )

    def stop_main_task(self, task_id: uuid.UUID) -> StorageMainTask:
        task = self.repository.get_main(task_id)
        if task is None:
            raise ValueError("存储任务不存在")
        if task.status not in {"queued", "running", "stopping"}:
            raise ValueError("当前状态不能停止")
        task.status = "stopping"
        if self.runtime is not None:
            self.runtime.request_stop(str(task.id))
        self.db.commit()
        self.db.refresh(task)
        return task

    def restart_main_task(self, task_id: uuid.UUID) -> StorageMainTask:
        task = self.repository.get_main(task_id)
        if task is None:
            raise ValueError("存储任务不存在")
        if task.status not in {"stopped", "failed"}:
            raise ValueError("只能重启已停止或失败的存储任务")
        for subtask in task.subtasks:
            if subtask.status in {"queued", "failed", "running"}:
                subtask.status = "queued"
                subtask.step = "prepare"
                subtask.error_message = None
                subtask.started_at = None
                subtask.finished_at = None
        task.status = "queued"
        task.started_at = None
        task.finished_at = None
        task.error_message = None
        self.repository.recompute_counts(task)
        if self.runtime is not None:
            self.runtime.clear_stop(str(task.id))
            self.runtime.enqueue_main_task(str(task.id))
        self.db.commit()
        self.db.refresh(task)
        return task
```

The creation implementation must:

- reject `storage_mode` outside `single` and `multiple` with `ValueError("storage_mode must be single or multiple")`;
- create a default alias with `generate_default_alias(datetime.now(), repository.count_today_main_tasks() + 1)`;
- load movies with `selectinload(Movie.magnets)`;
- resolve source task locations from `CrawlTask.storage_location`;
- for single batch push choose first usable location;
- for single row push honor `selected_storage_location` if it is in usable locations;
- create skipped subtasks for missing movie, marked movie, missing magnets, or missing locations;
- update `movie.storage_summary` with `last_main_task_id`, `last_sub_task_id`, `last_status`, `storage_mode`, and `updated_at`;
- enqueue the main task through runtime when runtime is provided and at least one subtask is queued.

- [ ] **Step 6: Create router and dependencies**

Create `backend/app/modules/storage/tasks/router.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.dependencies import CurrentUser, get_storage_task_service
from backend.app.modules.storage.tasks.schemas import StorageBatchPushRequest, StorageSinglePushRequest
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/tasks", tags=["storage-tasks"])


@router.post("/push")
def create_single_storage_push(body: StorageSinglePushRequest, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.create_single_push(body, current_user.id)
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/batch")
def create_batch_storage_push(body: StorageBatchPushRequest, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.create_batch_push(body, current_user.id)
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

In `backend/app/core/dependencies.py`, add:

```python
def get_storage_task_service(db: DbSession) -> StorageTaskService:
    return StorageTaskService(db=db, config_service=get_storage_config_service())
```

In `backend/app/main.py`, include the new router.

- [ ] **Step 7: Run focused API tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/storage/tasks backend/app/core/dependencies.py backend/app/main.py backend/tests/test_storage_tasks_api.py
git commit -m "feat: add storage task creation api"
```

---

### Task 4: Redis Runtime, Realtime Events, Logs, Stop, and Restart

**Files:**
- Create: `backend/app/modules/storage/runtime/__init__.py`
- Create: `backend/app/modules/storage/runtime/redis_state.py`
- Create: `backend/app/modules/storage/tasks/events.py`
- Create: `backend/app/modules/storage/tasks/logs.py`
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/app/modules/storage/tasks/router.py`
- Modify: `backend/app/core/dependencies.py`
- Create: `backend/tests/test_storage_runtime_redis.py`
- Create: `backend/tests/test_storage_realtime_events.py`

**Interfaces:**
- Produces: `StorageRuntimeState.enqueue_main_task(task_id: str) -> None`.
- Produces: `StorageRuntimeState.claim_next_main_task() -> str | None`.
- Produces: `StorageRuntimeState.request_stop(task_id: str) -> None`.
- Produces: `publish_storage_main_updated(db: Session, main_task: StorageMainTask) -> None`.
- Produces: `write_storage_subtask_log(subtask_id: str, level: str, message: str, context: dict | None = None) -> dict`.

- [ ] **Step 1: Write failing Redis runtime tests**

Create `backend/tests/test_storage_runtime_redis.py`:

```python
from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState


class FakeRedis:
    def __init__(self) -> None:
        self.lists = {}
        self.values = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lpop(self, key):
        values = self.lists.get(key, [])
        return values.pop(0) if values else None

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.lists.pop(key, None)


def test_storage_runtime_queue_and_stop() -> None:
    runtime = StorageRuntimeState(FakeRedis())
    runtime.enqueue_main_task("main-1")

    assert runtime.claim_next_main_task() == "main-1"
    assert runtime.claim_next_main_task() is None

    runtime.request_stop("main-1")
    assert runtime.should_stop("main-1") is True
    runtime.clear_stop("main-1")
    assert runtime.should_stop("main-1") is False
```

- [ ] **Step 2: Write failing event/log tests**

Create `backend/tests/test_storage_realtime_events.py`:

```python
from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs, write_storage_subtask_log


def test_storage_subtask_log_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    entry = write_storage_subtask_log("sub-1", "INFO", "hello", {"step": "prepare"})

    assert entry["message"] == "hello"
    assert read_storage_subtask_logs("sub-1")[0]["context"] == {"step": "prepare"}
```

- [ ] **Step 3: Run tests and verify failure**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_runtime_redis.py backend/tests/test_storage_realtime_events.py -v
```

Expected: FAIL because runtime/log modules do not exist.

- [ ] **Step 4: Implement Redis runtime**

Create `backend/app/modules/storage/runtime/redis_state.py`:

```python
class StorageRuntimeState:
    QUEUE_KEY = "storage:main_queue"
    CURRENT_KEY = "storage:current_main_task"
    STOP_PREFIX = "storage:stop:"

    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    def enqueue_main_task(self, task_id: str) -> None:
        self.redis.rpush(self.QUEUE_KEY, task_id)

    def claim_next_main_task(self) -> str | None:
        value = self.redis.lpop(self.QUEUE_KEY)
        if value is None:
            return None
        task_id = str(value)
        self.redis.set(self.CURRENT_KEY, task_id)
        return task_id

    def set_current_main_task(self, task_id: str | None) -> None:
        if task_id is None:
            self.redis.delete(self.CURRENT_KEY)
        else:
            self.redis.set(self.CURRENT_KEY, task_id)

    def request_stop(self, task_id: str) -> None:
        self.redis.set(f"{self.STOP_PREFIX}{task_id}", "1")

    def should_stop(self, task_id: str) -> bool:
        return self.redis.get(f"{self.STOP_PREFIX}{task_id}") == "1"

    def clear_stop(self, task_id: str) -> None:
        self.redis.delete(f"{self.STOP_PREFIX}{task_id}")

    def cleanup_runtime(self) -> None:
        self.redis.delete(self.QUEUE_KEY, self.CURRENT_KEY)
```

- [ ] **Step 5: Implement JSONL logs**

Create `backend/app/modules/storage/tasks/logs.py` with a path rooted under `APP_DATA_DIR` when set, otherwise `data/logs/storage/tasks`:

```python
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def _log_path(subtask_id: str) -> Path:
    root = Path(os.getenv("APP_DATA_DIR", "data")) / "logs/storage/tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{subtask_id}.jsonl"


def write_storage_subtask_log(subtask_id: str, level: str, message: str, context: dict | None = None) -> dict:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "context": context or {},
    }
    with _log_path(subtask_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_storage_subtask_logs(subtask_id: str) -> list[dict]:
    path = _log_path(subtask_id)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 6: Implement event publishers**

Create `backend/app/modules/storage/tasks/events.py`:

```python
from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.schemas import make_realtime_event
from shared.database.models.content import Movie


def publish_storage_main_updated(main_task: StorageMainTask) -> None:
    event_bus.publish(make_realtime_event(
        event="storage.main.updated",
        scope="storage.main",
        owner_id=str(main_task.created_by),
        resource_id=str(main_task.id),
        payload={
            "id": str(main_task.id),
            "status": main_task.status,
            "total_count": main_task.total_count,
            "success_count": main_task.success_count,
            "failed_count": main_task.failed_count,
            "skipped_count": main_task.skipped_count,
        },
    ))


def publish_storage_sub_updated(owner_id: str, subtask: StorageSubTask) -> None:
    event_bus.publish(make_realtime_event(
        event="storage.sub.updated",
        scope="storage.sub",
        owner_id=owner_id,
        resource_id=str(subtask.id),
        payload={
            "id": str(subtask.id),
            "main_task_id": str(subtask.main_task_id),
            "movie_id": str(subtask.movie_id),
            "status": subtask.status,
            "step": subtask.step,
            "error_message": subtask.error_message,
        },
    ))


def publish_movie_storage_updated(db: Session, owner_id: str, movie_id) -> None:
    movie = db.get(Movie, movie_id)
    if movie is None:
        return
    event_bus.publish(make_realtime_event(
        event="movie.storage.updated",
        scope="movie",
        owner_id=owner_id,
        resource_id=str(movie.id),
        payload={"movie_id": str(movie.id), "storage_summary": movie.storage_summary or {}},
    ))
```

- [ ] **Step 7: Wire stop/restart endpoints**

In `StorageTaskService.stop_main_task`, implement:

- load main task or raise `ValueError("存储任务不存在")`;
- allow statuses `queued`, `running`, `stopping`;
- set status `stopping`;
- call `runtime.request_stop(str(task.id))`;
- commit and publish `storage.main.updated`.

In `restart_main_task`, implement:

- allow statuses `stopped`, `failed`;
- reset failed and queued subtasks to `queued`, `step="prepare"`, clear runtime fields;
- keep completed and skipped;
- set main status `queued`;
- recompute counts;
- clear stop and enqueue.

Add routes:

```python
@router.post("/{main_task_id}/stop")
def stop_storage_main_task(main_task_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.stop_main_task(main_task_id)
        if task.created_by != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.post("/{main_task_id}/restart")
def restart_storage_main_task(main_task_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.restart_main_task(main_task_id)
        if task.created_by != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

- [ ] **Step 8: Run focused tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_runtime_redis.py backend/tests/test_storage_realtime_events.py backend/tests/test_storage_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/runtime backend/app/modules/storage/tasks/events.py backend/app/modules/storage/tasks/logs.py backend/app/modules/storage/tasks/service.py backend/app/modules/storage/tasks/router.py backend/app/core/dependencies.py backend/tests/test_storage_runtime_redis.py backend/tests/test_storage_realtime_events.py
git commit -m "feat: add storage task runtime controls"
```

---

### Task 5: Worker File Finder and Pipeline Steps

**Files:**
- Create: `backend/app/modules/storage/worker/__init__.py`
- Create: `backend/app/modules/storage/worker/context.py`
- Create: `backend/app/modules/storage/worker/file_finder.py`
- Create: `backend/app/modules/storage/worker/steps.py`
- Create: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Consumes: `StorageSubTask`, `StorageConfig`, `CloudDrive2Gateway`.
- Produces: `find_existing_video_files(provider, search_terms: list[str], search_paths: list[str], config: dict) -> list[dict]`.
- Produces: `execute_subtask_pipeline(context: StorageWorkerContext) -> StorageSubTask`.

- [ ] **Step 1: Write failing worker tests**

Create `backend/tests/test_storage_worker_pipeline.py` with fake provider tests:

```python
from dataclasses import dataclass

from backend.app.modules.storage.worker.file_finder import find_existing_video_files
from backend.app.modules.storage.worker.steps import select_main_videos


@dataclass
class FakeRemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False
    is_search_result: bool = False


class FakeProvider:
    def __init__(self) -> None:
        self.search_calls = []
        self.original_paths = {"/Search/ABC-123-C.mp4": "/Movies/A/ABC-123-C.mp4"}

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        self.search_calls.append((term, path))
        return [FakeRemoteFile("ABC-123-C.mp4", "/Search/ABC-123-C.mp4", 500 * 1024 * 1024, False, True)]

    def get_original_path(self, path):
        return self.original_paths[path]

    def list_files(self, path, force_refresh=False):
        return []


def test_find_existing_video_files_uses_search_and_original_path() -> None:
    provider = FakeProvider()

    files = find_existing_video_files(
        provider,
        search_terms=["ABC-123"],
        search_paths=["/Downloads"],
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert files[0]["path"] == "/Movies/A/ABC-123-C.mp4"
    assert provider.search_calls == [("ABC-123", "/Downloads")]


def test_select_main_videos_requires_video_extension_and_min_size() -> None:
    files = [
        {"name": "small.mp4", "path": "/a/small.mp4", "size": 20 * 1024 * 1024},
        {"name": "main.mkv", "path": "/a/main.mkv", "size": 900 * 1024 * 1024},
    ]

    selected = select_main_videos(files, {"video_extensions": [".mp4", ".mkv"], "minimum_video_size_mb": 100})

    assert selected == [{"name": "main.mkv", "path": "/a/main.mkv", "size": 900 * 1024 * 1024}]
```

- [ ] **Step 2: Run tests and verify failure**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py -v
```

Expected: FAIL because worker modules do not exist.

- [ ] **Step 3: Implement file finder**

Create `backend/app/modules/storage/worker/file_finder.py`:

```python
from __future__ import annotations

from pathlib import PurePosixPath


def _file_to_dict(provider, file_obj) -> dict:
    path = getattr(file_obj, "full_path", "") or getattr(file_obj, "fullPathName", "")
    if getattr(file_obj, "is_search_result", False) or getattr(file_obj, "isSearchResult", False):
        original = provider.get_original_path(path)
        if original:
            path = original
    return {
        "name": getattr(file_obj, "name", "") or PurePosixPath(path).name,
        "path": path,
        "size": int(getattr(file_obj, "size", 0) or 0),
        "is_dir": bool(getattr(file_obj, "is_directory", False) or getattr(file_obj, "isDirectory", False)),
    }


def _is_usable_video(file_dict: dict, config: dict) -> bool:
    ext = PurePosixPath(file_dict["name"]).suffix.lower()
    min_bytes = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    return ext in set(config.get("video_extensions", [])) and int(file_dict.get("size") or 0) >= min_bytes


def _recursive_list(provider, path: str, config: dict) -> list[dict]:
    found = []
    for entry in provider.list_files(path):
        item = _file_to_dict(provider, entry)
        if item["is_dir"]:
            found.extend(_recursive_list(provider, item["path"], config))
        elif _is_usable_video(item, config):
            found.append(item)
    return found


def find_existing_video_files(provider, search_terms: list[str], search_paths: list[str], config: dict) -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    for path in search_paths:
        for term in search_terms:
            try:
                search_results = provider.search_files(term, path)
            except Exception:
                search_results = []
            for file_obj in search_results:
                item = _file_to_dict(provider, file_obj)
                if not item["is_dir"] and _is_usable_video(item, config) and item["path"] not in seen:
                    seen.add(item["path"])
                    results.append(item)
        if results:
            return results
    for path in search_paths:
        try:
            for item in _recursive_list(provider, path, config):
                if item["path"] not in seen:
                    seen.add(item["path"])
                    results.append(item)
        except Exception:
            continue
        if results:
            return results
    return results
```

- [ ] **Step 4: Implement worker context and steps**

Create `backend/app/modules/storage/worker/context.py`:

```python
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask


@dataclass
class StorageWorkerContext:
    db: Session
    main_task: StorageMainTask
    subtask: StorageSubTask
    config: dict
    provider: object
```

Create `backend/app/modules/storage/worker/steps.py` with pure helpers:

```python
from pathlib import PurePosixPath


def select_main_videos(files: list[dict], config: dict) -> list[dict]:
    extensions = {ext.lower() for ext in config.get("video_extensions", [])}
    minimum_size = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    videos = [
        file
        for file in files
        if PurePosixPath(file["name"]).suffix.lower() in extensions
        and int(file.get("size") or 0) >= minimum_size
    ]
    return sorted(videos, key=lambda file: (str(file["name"]).lower(), str(file["path"]).lower()))
```

Then add pipeline functions in the same file:

- `ensure_directory_chain(provider, folder_path: str) -> None`
- `target_files_exist(provider, target_folder: str, filenames: list[str]) -> bool`
- `execute_current_magnet_attempt(context: StorageWorkerContext, magnet: dict) -> bool`
- `execute_subtask_pipeline(context: StorageWorkerContext) -> StorageSubTask`

Use the following state contract:

- return `True` from `execute_current_magnet_attempt` only after verification passes;
- return `False` for a failed magnet attempt so the caller tries the next candidate;
- raise only for programming/configuration errors such as missing movie code.

- [ ] **Step 5: Run focused tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_task_policies.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/storage/worker backend/tests/test_storage_worker_pipeline.py
git commit -m "feat: add storage worker pipeline helpers"
```

---

### Task 6: Worker Runner and Startup Cleanup

**Files:**
- Create: `backend/app/modules/storage/worker/runner.py`
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_storage_worker_service.py`

**Interfaces:**
- Consumes: `StorageRuntimeState.claim_next_main_task()`.
- Consumes: `execute_subtask_pipeline(context)`.
- Produces: `cleanup_interrupted_storage_tasks(db: Session, runtime: StorageRuntimeState) -> int`.
- Produces: `StorageTaskService._ensure_worker_started() -> None`.

- [ ] **Step 1: Write failing worker service tests**

Create `backend/tests/test_storage_worker_service.py`:

```python
from datetime import datetime

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.worker.runner import cleanup_interrupted_storage_tasks
from shared.database.models.content import Movie


class FakeRuntime:
    def __init__(self) -> None:
        self.cleaned = False

    def cleanup_runtime(self) -> None:
        self.cleaned = True


def test_cleanup_interrupted_storage_tasks_marks_running_stopped(db_session, test_user):
    movie = Movie(code="ABC-123", source_name="Title")
    db_session.add(movie)
    db_session.flush()

    main = StorageMainTask(
        alias="a",
        display_name="a",
        source="single",
        storage_mode="single",
        status="running",
        total_count=1,
        created_by=test_user.id,
        started_at=datetime.now(),
    )
    sub = StorageSubTask(
        main_task=main,
        movie_id=movie.id,
        movie_code="ABC-123",
        movie_title="Title",
        status="running",
        step="cloud_download",
        storage_mode="single",
    )
    db_session.add_all([main, sub])
    db_session.commit()

    runtime = FakeRuntime()
    stopped = cleanup_interrupted_storage_tasks(db_session, runtime)

    assert stopped == 1
    assert runtime.cleaned is True
    assert main.status == "stopped"
    assert sub.status == "queued"
    assert sub.step == "prepare"
```

- [ ] **Step 2: Run test and verify failure**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py -v
```

Expected: FAIL because `worker.runner` does not exist.

- [ ] **Step 3: Implement worker runner**

Create `backend/app/modules/storage/worker/runner.py` with:

```python
import logging
import threading
import uuid
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.worker.context import StorageWorkerContext
from backend.app.modules.storage.worker.steps import execute_subtask_pipeline
from shared.database.session import get_session_factory

logger = logging.getLogger(__name__)
_worker_lock = threading.Lock()
_worker_running = False


def cleanup_interrupted_storage_tasks(db: Session, runtime) -> int:
    runtime.cleanup_runtime()
    rows = db.query(StorageMainTask).filter(StorageMainTask.status.in_(["queued", "running", "stopping"])).all()
    now = datetime.now()
    for main in rows:
        main.status = "stopped"
        main.finished_at = main.finished_at or now
        main.error_message = "服务重启，存储任务已停止，需手动重启"
        for subtask in main.subtasks:
            if subtask.status == "running":
                subtask.status = "queued"
                subtask.step = "prepare"
                subtask.error_message = None
    db.commit()
    return len(rows)


def ensure_storage_worker_started(runtime, provider_factory, config_service) -> None:
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
        thread = threading.Thread(
            target=_worker_loop,
            args=(get_session_factory(), runtime, provider_factory, config_service),
            daemon=True,
            name="storage-worker",
        )
        thread.start()


def _worker_loop(db_factory: sessionmaker, runtime, provider_factory, config_service) -> None:
    global _worker_running
    try:
        while True:
            task_id = runtime.claim_next_main_task()
            if task_id is None:
                break
            process_main_task(db_factory, runtime, provider_factory, config_service, task_id)
    finally:
        with _worker_lock:
            _worker_running = False
```

Add `process_main_task(db_factory, runtime, provider_factory, config_service, task_id: str) -> bool` to:

- set main status `running`;
- iterate queued subtasks in created order;
- skip starting the next subtask when runtime stop flag is set;
- create CloudDrive2 client/gateway from config snapshot;
- execute the subtask pipeline;
- recompute counts;
- mark main `completed`, `failed`, or `stopped`.

- [ ] **Step 4: Wire service to start worker**

In `StorageTaskService.create_single_push` and `create_batch_push`, after enqueueing a main task, call:

```python
ensure_storage_worker_started(self.runtime, self.config_service.provider_factory, self.config_service)
```

Make constructor dependencies explicit so tests can pass fake runtime/provider factory.

- [ ] **Step 5: Add startup cleanup**

In `backend/app/main.py`, inside lifespan after crawler cleanup, call:

```python
from backend.app.modules.storage.worker.runner import cleanup_interrupted_storage_tasks
from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState

storage_stopped = cleanup_interrupted_storage_tasks(session, StorageRuntimeState(get_redis()))
```

Log the stopped count when nonzero.

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_service.py backend/tests/test_storage_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/storage/worker/runner.py backend/app/modules/storage/tasks/service.py backend/app/main.py backend/tests/test_storage_worker_service.py
git commit -m "feat: run storage tasks from redis"
```

---

### Task 7: Frontend Storage Task API, Realtime Types, and Movie Push Modal

**Files:**
- Create: `frontend/src/api/storage/storageTasks/types.ts`
- Create: `frontend/src/api/storage/storageTasks/index.ts`
- Modify: `frontend/src/realtime/types.ts`
- Modify: `frontend/src/realtime/eventSourceClient.ts`
- Create: `frontend/src/pages/content/movies/hooks/useStoragePush.ts`
- Create: `frontend/src/pages/content/movies/components/StoragePushModal.tsx`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`
- Create: `frontend/src/pages/content/movies/__tests__/storage-push-modal.test.tsx`
- Create: `frontend/src/realtime/__tests__/storage-realtime-events.test.ts`

**Interfaces:**
- Consumes: `POST /api/storage/tasks/push`, `POST /api/storage/tasks/batch`.
- Produces: `createStoragePush`, `createBatchStoragePush`.
- Produces: `useStoragePush({ selectedRowKeys, movies, reload, updateMovie })`.

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/src/realtime/__tests__/storage-realtime-events.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import type { RealtimeEventName } from '@/realtime/types'

describe('storage realtime event names', () => {
  it('includes storage and movie storage events', () => {
    const events: RealtimeEventName[] = [
      'storage.main.updated',
      'storage.sub.updated',
      'storage.sub.log.appended',
      'storage.queue.updated',
      'movie.storage.updated',
    ]

    expect(events).toHaveLength(5)
  })
})
```

Create `frontend/src/pages/content/movies/__tests__/storage-push-modal.test.tsx` with a render test for `StoragePushModal`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import StoragePushModal from '../components/StoragePushModal'

describe('StoragePushModal', () => {
  it('shows single mode target folder choices', () => {
    render(
      <StoragePushModal
        open
        mode="single"
        movies={[{
          _id: 'm1',
          id: 'm1',
          code: 'ABC-123',
          source_name: 'Movie',
          source_task_ids: ['task-1'],
          storage_locations: ['A', 'B'],
        } as never]}
        selectedRowKeys={[]}
        loading={false}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    expect(screen.getByText('推送存储')).toBeInTheDocument()
    expect(screen.getByText('存储模式')).toBeInTheDocument()
    expect(screen.getByText('目标文件夹')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run frontend tests and verify failure**

```bash
cd frontend
npm test -- storage-realtime-events storage-push-modal
```

Expected: FAIL because types and modal do not exist.

- [ ] **Step 3: Add storage task API types**

Create `frontend/src/api/storage/storageTasks/types.ts`:

```typescript
export type StorageMode = 'single' | 'multiple'
export type StorageMainTaskStatus = 'queued' | 'running' | 'stopping' | 'stopped' | 'completed' | 'failed'

export interface StorageMainTask {
  id: string
  alias: string
  display_name: string
  source: 'single' | 'batch'
  storage_mode: StorageMode
  status: StorageMainTaskStatus
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
}

export interface StorageSinglePushPayload {
  movie_id: string
  alias?: string
  storage_mode: StorageMode
  selected_storage_location?: string
}

export interface StorageBatchPushPayload {
  movie_ids: string[]
  alias?: string
  storage_mode: StorageMode
}
```

Create `frontend/src/api/storage/storageTasks/index.ts`:

```typescript
import request from '@/request'
import type { StorageBatchPushPayload, StorageMainTask, StorageSinglePushPayload } from './types'

export function createStoragePush(payload: StorageSinglePushPayload) {
  return request.post<StorageMainTask>('/storage/tasks/push', payload)
}

export function createBatchStoragePush(payload: StorageBatchPushPayload) {
  return request.post<StorageMainTask>('/storage/tasks/batch', payload)
}
```

- [ ] **Step 4: Extend realtime types and client events**

In `frontend/src/realtime/types.ts`, add storage payload interfaces and event names:

```typescript
export type StorageMainUpdatedPayload = StorageMainTask
export type StorageSubUpdatedPayload = {
  id: string
  main_task_id: string
  movie_id: string
  status: string
  step: string
  error_message?: string | null
}
export type MovieStorageUpdatedPayload = {
  movie_id: string
  storage_summary: Record<string, unknown>
}
```

Add union members:

```typescript
  | 'storage.main.updated'
  | 'storage.sub.updated'
  | 'storage.sub.log.appended'
  | 'storage.queue.updated'
  | 'movie.storage.updated'
```

In `frontend/src/realtime/eventSourceClient.ts`, add these event names to `EVENT_NAMES`.

- [ ] **Step 5: Implement modal and hook**

Create `frontend/src/pages/content/movies/components/StoragePushModal.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { Form, Input, Modal, Select } from 'antd'
import type { StorageMode } from '@/api/storage/storageTasks/types'

type PushMovie = {
  _id: string
  code?: string
  source_name?: string
  storage_locations?: string[]
}

type Props = {
  open: boolean
  mode: 'single' | 'batch'
  movies: PushMovie[]
  selectedRowKeys: React.Key[]
  loading: boolean
  onCancel: () => void
  onSubmit: (values: { alias?: string; storageMode: StorageMode; selectedStorageLocation?: string }) => void
}

function StoragePushModal({ open, mode, movies, selectedRowKeys, loading, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<{ alias?: string; selectedStorageLocation?: string }>()
  const [storageMode, setStorageMode] = useState<StorageMode>('single')
  const firstMovie = movies[0]
  const locationOptions = useMemo(
    () => (firstMovie?.storage_locations ?? []).map((value) => ({ value, label: value })),
    [firstMovie],
  )

  return (
    <Modal
      title={mode === 'single' ? '推送存储' : '批量推送存储'}
      open={open}
      confirmLoading={loading}
      onCancel={onCancel}
      onOk={() => onSubmit({
        alias: form.getFieldValue('alias'),
        storageMode,
        selectedStorageLocation: form.getFieldValue('selectedStorageLocation'),
      })}
    >
      <Form form={form} layout="vertical" initialValues={{ selectedStorageLocation: locationOptions[0]?.value }}>
        <Form.Item label="别名" name="alias">
          <Input />
        </Form.Item>
        <Form.Item label="存储模式">
          <Select
            value={storageMode}
            onChange={setStorageMode}
            options={[
              { value: 'single', label: '单个' },
              { value: 'multiple', label: '多个' },
            ]}
          />
        </Form.Item>
        {mode === 'single' && storageMode === 'single' && (
          <Form.Item label="目标文件夹" name="selectedStorageLocation">
            <Select
              options={locationOptions}
            />
          </Form.Item>
        )}
        <div>{mode === 'batch' ? `已选择 ${selectedRowKeys.length} 条` : firstMovie?.code}</div>
      </Form>
    </Modal>
  )
}

export default StoragePushModal
```

- [ ] **Step 6: Wire movie list actions**

Create `useStoragePush.ts` to manage modal state and call `createStoragePush` or `createBatchStoragePush`. Modify `MovieListPage.tsx` and `MovieTable.tsx` so:

- row action opens the modal with one movie;
- bulk action opens batch modal with selected row keys;
- `movie.storage.updated` updates the matching row's `storage_summary`;
- successful submit closes modal and refreshes list.

- [ ] **Step 7: Run frontend tests**

```bash
cd frontend
npm test -- storage-realtime-events storage-push-modal
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/storage/storageTasks frontend/src/realtime frontend/src/pages/content/movies
git commit -m "feat: add movie storage push ui"
```

---

### Task 8: Storage Task List, Detail, and Subtask Pages

**Files:**
- Create: `frontend/src/pages/storage/tasks/StorageTaskListPage.tsx`
- Create: `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`
- Create: `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`
- Create: `frontend/src/pages/storage/tasks/StorageTasks.module.less`
- Modify: `frontend/src/api/storage/storageTasks/types.ts`
- Modify: `frontend/src/api/storage/storageTasks/index.ts`
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/layout/Sidebar/index.tsx`
- Create: `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

**Interfaces:**
- Consumes: storage task list/detail/subtask/log/stop/restart endpoints.
- Produces routes: `/storage/tasks`, `/storage/tasks/$id`, `/storage/tasks/subtasks/$id`.

- [ ] **Step 1: Write failing route/page tests**

Create `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StorageTaskListPage from '../StorageTaskListPage'

describe('StorageTaskListPage', () => {
  it('renders storage task list heading and actions', () => {
    render(<StorageTaskListPage />)

    expect(screen.getByText('存储任务')).toBeInTheDocument()
    expect(screen.getByText('刷新')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test and verify failure**

```bash
cd frontend
npm test -- storage-task-pages
```

Expected: FAIL because page does not exist.

- [ ] **Step 3: Extend API functions**

Add to `frontend/src/api/storage/storageTasks/index.ts`:

```typescript
export function listStorageMainTasks(params: Record<string, unknown>) {
  return request.get<{ rows: StorageMainTask[]; total: number }>('/storage/tasks', { params })
}

export function getStorageMainTask(id: string) {
  return request.get<StorageMainTask>(`/storage/tasks/${id}`)
}

export function stopStorageMainTask(id: string) {
  return request.post<StorageMainTask>(`/storage/tasks/${id}/stop`)
}

export function restartStorageMainTask(id: string) {
  return request.post<StorageMainTask>(`/storage/tasks/${id}/restart`)
}
```

Add subtask and log types before implementing detail pages.

- [ ] **Step 4: Create task pages**

Implement pages with existing `BaseListPage` and Ant Design `Descriptions`, `Table`, `Tag`, and `Button`:

- list page columns: alias, status, storage mode, total, success, failed, skipped, created time, actions;
- detail page: summary descriptions and subtask table;
- subtask detail: movie code, status, step, target locations, magnet attempts, moved files, logs.

Subscribe to realtime events using `connectRealtime()` and `subscribeRealtime()` in `useEffect`, and refetch on `system.resync_required`.

- [ ] **Step 5: Add routes and sidebar**

In `frontend/src/routes/index.tsx`, import the pages and add routes:

```typescript
const storageTasksRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/storage/tasks',
  component: StorageTaskListPage,
})
```

Add detail and subtask routes. Add them to `routeTree`.

In `Sidebar/index.tsx`, add:

```tsx
{
  key: '/storage/tasks',
  icon: <HistoryOutlined />,
  label: '存储任务',
}
```

Update selected key handling for `/storage/tasks`.

- [ ] **Step 6: Run frontend tests and build**

```bash
cd frontend
npm test -- storage-task-pages
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/storage/tasks frontend/src/api/storage/storageTasks frontend/src/routes/index.tsx frontend/src/layout/Sidebar/index.tsx
git commit -m "feat: add storage task pages"
```

---

### Task 9: Backend List, Detail, Subtask, Logs, and Full API Coverage

**Files:**
- Modify: `backend/app/modules/storage/tasks/schemas.py`
- Modify: `backend/app/modules/storage/tasks/repository.py`
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/app/modules/storage/tasks/router.py`
- Modify: `backend/tests/test_storage_tasks_api.py`

**Interfaces:**
- Produces: `GET /api/storage/tasks`.
- Produces: `GET /api/storage/tasks/{main_task_id}`.
- Produces: `GET /api/storage/tasks/{main_task_id}/subtasks`.
- Produces: `GET /api/storage/tasks/subtasks/{subtask_id}`.
- Produces: `GET /api/storage/tasks/subtasks/{subtask_id}/logs`.

- [ ] **Step 1: Add failing list/detail tests**

Append to `backend/tests/test_storage_tasks_api.py`:

```python
def test_list_and_detail_storage_tasks(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id, code="abc-321")
    created = client.post(
        "/api/storage/tasks/push",
        json={"movie_id": str(movie.id), "storage_mode": "single", "selected_storage_location": "A"},
        headers=auth_headers,
    ).json()["data"]

    listing = client.get("/api/storage/tasks", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] >= 1

    detail = client.get(f"/api/storage/tasks/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == created["id"]

    subtasks = client.get(f"/api/storage/tasks/{created['id']}/subtasks", headers=auth_headers)
    assert subtasks.status_code == 200
    assert subtasks.json()["data"]["total"] == 1
```

- [ ] **Step 2: Run test and verify failure**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_tasks_api.py::test_list_and_detail_storage_tasks -v
```

Expected: FAIL because list/detail endpoints do not exist.

- [ ] **Step 3: Implement response schemas and serializers**

Add `StorageSubTaskResponse`, `StorageTaskLogResponse`, and serializer methods in service:

```python
def to_main_response(self, task: StorageMainTask) -> dict:
    return StorageMainTaskResponse.model_validate(task, from_attributes=True).model_dump(mode="json")

def to_subtask_response(self, task: StorageSubTask) -> dict:
    return StorageSubTaskResponse.model_validate(task, from_attributes=True).model_dump(mode="json")
```

Return IDs as strings and datetimes as ISO-compatible values through Pydantic models.

- [ ] **Step 4: Implement repository queries**

Add:

```python
def list_main_tasks(self, *, page: int, limit: int, status: str | None, keyword: str | None) -> tuple[list[StorageMainTask], int]:
    query = self.db.query(StorageMainTask)
    if status:
        query = query.filter(StorageMainTask.status == status)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(StorageMainTask.alias.ilike(pattern))
    total = query.count()
    rows = query.order_by(StorageMainTask.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return rows, total

def list_subtasks(self, main_task_id: uuid.UUID, *, page: int, limit: int) -> tuple[list[StorageSubTask], int]:
    query = self.db.query(StorageSubTask).filter(StorageSubTask.main_task_id == main_task_id)
    total = query.count()
    rows = query.order_by(StorageSubTask.created_at.asc()).offset((page - 1) * limit).limit(limit).all()
    return rows, total

def get_subtask(self, subtask_id: uuid.UUID) -> StorageSubTask | None:
    return self.db.get(StorageSubTask, subtask_id)
```

- [ ] **Step 5: Implement router endpoints**

Use `success(data=service.to_main_response(task))` for single resources and `success(data={"rows": rows, "total": total})` for paginated resources. Return `HTTPException(status_code=404, detail="Task not found")` for missing main records and `HTTPException(status_code=404, detail="Subtask not found")` for missing subtask records.

- [ ] **Step 6: Run full storage backend tests**

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_task_models.py backend/tests/test_storage_task_policies.py backend/tests/test_storage_tasks_api.py backend/tests/test_storage_runtime_redis.py backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_service.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/storage/tasks backend/tests/test_storage_tasks_api.py
git commit -m "feat: expose storage task details"
```

---

### Task 10: Final Verification and Integration Cleanup

**Files:**
- Modify only files touched by earlier tasks when verification reveals concrete failures.
- No new feature files unless a failing test demonstrates a missing integration point.

**Interfaces:**
- Consumes all prior tasks.
- Produces a working storage push feature with backend and frontend verification.

- [ ] **Step 1: Run backend storage-focused test suite**

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_storage_config_api.py \
  backend/tests/test_storage_task_models.py \
  backend/tests/test_storage_task_policies.py \
  backend/tests/test_clouddrive_search_gateway.py \
  backend/tests/test_storage_tasks_api.py \
  backend/tests/test_storage_runtime_redis.py \
  backend/tests/test_storage_worker_pipeline.py \
  backend/tests/test_storage_worker_service.py \
  backend/tests/test_storage_realtime_events.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run broader backend regression tests around touched systems**

```bash
source .venv/bin/activate
python -m pytest \
  backend/tests/test_content_movies_api.py \
  backend/tests/test_realtime_events.py \
  backend/tests/test_crawler_runtime_redis.py \
  backend/tests/test_crawler_runs_api.py \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend tests for storage and realtime**

```bash
cd frontend
npm test -- storage
npm test -- realtime
```

Expected: PASS.

- [ ] **Step 4: Run frontend lint and build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 5: Manual smoke test with dev servers**

Start backend:

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

Start frontend in another terminal:

```bash
cd frontend
npm run dev
```

Verify in the browser:

- movie list shows row push and batch push controls;
- single push modal defaults storage mode to `单个`;
- single push modal shows target folder dropdown;
- batch push creates one main task and one subtask per selected movie;
- `/storage/tasks` shows the new main task;
- stop changes a running main task to `stopping`;
- realtime updates change movie row storage status and task counters.

- [ ] **Step 6: Commit verification fixes**

If verification required code changes:

```bash
git status --short
git add backend frontend shared
git commit -m "fix: stabilize storage push integration"
```

If no changes were required, do not create an empty commit.
