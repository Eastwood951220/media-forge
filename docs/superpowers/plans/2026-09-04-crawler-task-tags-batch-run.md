# Crawler Task Tags And Batch Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable multi-tag metadata to crawler tasks, all-match tag filtering on the task list, and batch run submission for selected idle tasks.

**Architecture:** Store tags in normalized per-user tables and expose them through existing crawler task serializers. Task create/update/batch-create accept `tag_names`, list filtering happens in the repository before pagination, and batch run creates one crawler run per accepted task while returning per-task failures.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, pytest, React 19, Vite, TypeScript, Ant Design, TanStack Query, Zustand, Vitest, React Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-04-crawler-task-tags-batch-run-design.md`

## Global Constraints

- Do not create or use a Git worktree in this repository.
- Stage intended source files explicitly instead of using `git add .` or `git add -A`.
- Do not add global tag management screens.
- Do not add tag colors in this iteration.
- Do not support tag deletion or renaming in this iteration.
- Do not change crawler scheduling, queue capacity, or run execution semantics.
- Do not auto-select all filtered tasks across all pages; selection applies to currently loaded task cards.
- Do not merge selected tasks into one crawler run. Each selected task creates its own run.
- Save database-change SQL files under the repository root `sql/` directory.

---

## File Structure

- Modify `backend/app/models/crawl_task.py`: add `CrawlTaskTag`, association table, and `CrawlTask.tags` relationship.
- Create `backend/alembic/versions/20260904_0002_add_crawler_task_tags.py`: Alembic migration for tag tables and indexes.
- Create `sql/20260904_add_crawler_task_tags.sql`: standalone SQL for the same database tables and indexes.
- Modify `backend/app/schemas/crawl_task.py`: add tag schemas, `tag_names`, tag list responses, and batch-run schemas.
- Modify `backend/app/modules/crawler/tasks/serializers.py`: serialize task tags in detail/list payloads.
- Modify `backend/app/repositories/crawl_task.py`: eager-load tags, list/count all-match tag filtering, tag lookup, and tag-link replacement helpers.
- Modify `backend/app/modules/crawler/tasks/service.py`: normalize/get-or-create tags, attach tags on create/update/batch-create, expose tag dictionary, and add batch run.
- Modify `backend/app/modules/crawler/tasks/router.py`: add tags endpoint, list `tag_names` query params, and batch-run endpoint before UUID routes.
- Modify `backend/tests/test_crawler_tasks_api.py`: backend coverage for tag persistence, filtering, dictionary, batch-create tags, and batch-run.
- Modify `frontend/src/api/queryKeys.ts`: include task list `tag_names` and add task-tag dictionary key.
- Modify `frontend/src/api/crawler/crawlTask/types.ts`: add tag types, `tag_names` fields, and batch-run types.
- Modify `frontend/src/api/crawler/crawlTask/index.ts`: add tag dictionary and batch-run API functions.
- Create `frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx`: shared `Select mode="tags"` field for task form and batch-create drawer.
- Modify `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`: load tags, render tag field, submit `tag_names`, and hydrate edit tags.
- Modify `frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx`: add `tag_names` to the drawer.
- Modify `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`: include tag filters in query params and add batch-run helper.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`: own selected tag filters, selected task ids, batch-run modal state, and optimistic queued updates.
- Modify `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`: render tag filter, task tags, card checkboxes, selected count, and batch-run button.
- Modify or add frontend tests under `frontend/src/pages/crawler/tasks/__tests__/`: form tags, drawer tags, list filtering, tag rendering, selection, and batch-run.

---

### Task 1: Backend Tag Tables, Schemas, And Serialization

**Files:**
- Modify: `backend/app/models/crawl_task.py`
- Create: `backend/alembic/versions/20260904_0002_add_crawler_task_tags.py`
- Create: `sql/20260904_add_crawler_task_tags.sql`
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/serializers.py`
- Test: `backend/tests/test_crawler_tasks_api.py`

**Interfaces:**
- Produces: `CrawlTaskTag` ORM model.
- Produces: `crawl_task_tag_links` association table.
- Produces: `TaskTagRead` schema with `id: uuid.UUID` and `name: str`.
- Produces: `CrawlTaskCreate.tag_names: list[str] | None = None`.
- Produces: `CrawlTaskUpdate.tag_names: list[str] | None = None`.
- Produces: `CrawlTaskBatchCreate.tag_names: list[str] | None = None`.
- Produces: `CrawlTaskRead.tags: list[TaskTagRead]`.
- Produces: `CrawlTaskListItem.tags: list[TaskTagRead]`.

- [ ] **Step 1: Write failing model/schema tests**

Add these tests to `backend/tests/test_crawler_tasks_api.py`:

```python
def test_crawler_task_tag_tables_are_registered():
    from shared.database.models.base import Base

    assert "crawl_task_tags" in Base.metadata.tables
    assert "crawl_task_tag_links" in Base.metadata.tables


def test_crawler_task_schemas_accept_tag_names():
    from backend.app.schemas.crawl_task import CrawlTaskBatchCreate, CrawlTaskCreate, CrawlTaskUpdate

    create = CrawlTaskCreate(
        name="tag schema",
        storage_location="tag schema",
        tag_names=["VR", "演员"],
        urls=[{"url": "https://javdb.com/actors/schema", "url_type": "actors"}],
    )
    update = CrawlTaskUpdate(tag_names=[])
    batch = CrawlTaskBatchCreate(urls=["https://javdb.com/actors/schema"], tag_names=["VR"])

    assert create.tag_names == ["VR", "演员"]
    assert update.tag_names == []
    assert batch.tag_names == ["VR"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_crawler_task_tag_tables_are_registered tests/test_crawler_tasks_api.py::test_crawler_task_schemas_accept_tag_names -v
```

Expected: FAIL because tag tables and `tag_names` schemas do not exist.

- [ ] **Step 3: Add ORM model and relationship**

In `backend/app/models/crawl_task.py`, add imports:

```python
from sqlalchemy import Table, Column
```

Add the association table before `class CrawlTask`:

```python
crawl_task_tag_links = Table(
    "crawl_task_tag_links",
    Base.metadata,
    Column("task_id", ForeignKey("crawl_tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("crawl_task_tags.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("task_id", "tag_id", name="uq_crawl_task_tag_links_task_tag"),
    Index("idx_crawl_task_tag_links_task_id", "task_id"),
    Index("idx_crawl_task_tag_links_tag_id", "tag_id"),
)
```

Add a `tags` relationship to `CrawlTask`:

```python
    tags: Mapped[list["CrawlTaskTag"]] = relationship(
        secondary=crawl_task_tag_links,
        back_populates="tasks",
        order_by="CrawlTaskTag.name",
        lazy="selectin",
    )
```

Add the tag model after `CrawlTaskUrl`:

```python
class CrawlTaskTag(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_task_tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_crawl_task_tags_owner_name"),
        Index("idx_crawl_task_tags_owner_name", "owner_id", "name"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    tasks: Mapped[list[CrawlTask]] = relationship(
        secondary=crawl_task_tag_links,
        back_populates="tags",
        lazy="selectin",
    )
```

- [ ] **Step 4: Add Alembic migration and root SQL file**

Create `backend/alembic/versions/20260904_0002_add_crawler_task_tags.py`:

```python
"""add crawler task tags

Revision ID: 20260904_0002
Revises: 20260904_0001
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0002"
down_revision = "20260904_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_task_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_crawl_task_tags_owner_name"),
    )
    op.create_index("idx_crawl_task_tags_owner_name", "crawl_task_tags", ["owner_id", "name"])
    op.create_index(op.f("ix_crawl_task_tags_owner_id"), "crawl_task_tags", ["owner_id"])

    op.create_table(
        "crawl_task_tag_links",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["crawl_task_tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["crawl_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
        sa.UniqueConstraint("task_id", "tag_id", name="uq_crawl_task_tag_links_task_tag"),
    )
    op.create_index("idx_crawl_task_tag_links_task_id", "crawl_task_tag_links", ["task_id"])
    op.create_index("idx_crawl_task_tag_links_tag_id", "crawl_task_tag_links", ["tag_id"])


def downgrade() -> None:
    op.drop_index("idx_crawl_task_tag_links_tag_id", table_name="crawl_task_tag_links")
    op.drop_index("idx_crawl_task_tag_links_task_id", table_name="crawl_task_tag_links")
    op.drop_table("crawl_task_tag_links")
    op.drop_index(op.f("ix_crawl_task_tags_owner_id"), table_name="crawl_task_tags")
    op.drop_index("idx_crawl_task_tags_owner_name", table_name="crawl_task_tags")
    op.drop_table("crawl_task_tags")
```

Create `sql/20260904_add_crawler_task_tags.sql`:

```sql
CREATE TABLE crawl_task_tags (
    id UUID NOT NULL,
    owner_id UUID NOT NULL,
    name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_crawl_task_tags_owner_name UNIQUE (owner_id, name),
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX idx_crawl_task_tags_owner_name
    ON crawl_task_tags (owner_id, name);

CREATE INDEX ix_crawl_task_tags_owner_id
    ON crawl_task_tags (owner_id);

CREATE TABLE crawl_task_tag_links (
    task_id UUID NOT NULL,
    tag_id UUID NOT NULL,
    PRIMARY KEY (task_id, tag_id),
    CONSTRAINT uq_crawl_task_tag_links_task_tag UNIQUE (task_id, tag_id),
    FOREIGN KEY(task_id) REFERENCES crawl_tasks (id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES crawl_task_tags (id) ON DELETE CASCADE
);

CREATE INDEX idx_crawl_task_tag_links_task_id
    ON crawl_task_tag_links (task_id);

CREATE INDEX idx_crawl_task_tag_links_tag_id
    ON crawl_task_tag_links (tag_id);
```

- [ ] **Step 5: Add schemas and serializer fields**

In `backend/app/schemas/crawl_task.py`, add:

```python
class TaskTagRead(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}
```

Add `tag_names` to create/update/batch-create schemas:

```python
tag_names: list[str] | None = None
```

Add `tags` to `CrawlTaskRead` and `CrawlTaskListItem`:

```python
tags: list[TaskTagRead] = Field(default_factory=list)
```

In `backend/app/modules/crawler/tasks/serializers.py`, import `TaskTagRead` and include tags:

```python
tags=[TaskTagRead.model_validate(tag) for tag in task.tags]
```

Use that expression in both `serialize_task` and `serialize_task_list_item`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_crawler_task_tag_tables_are_registered tests/test_crawler_tasks_api.py::test_crawler_task_schemas_accept_tag_names -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add backend/app/models/crawl_task.py backend/alembic/versions/20260904_0002_add_crawler_task_tags.py sql/20260904_add_crawler_task_tags.sql backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/serializers.py backend/tests/test_crawler_tasks_api.py
git diff --cached --name-only
git commit -m "feat: add crawler task tag schema"
```

---

### Task 2: Backend Tag Persistence, Dictionary, And All-Match Filtering

**Files:**
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Test: `backend/tests/test_crawler_tasks_api.py`

**Interfaces:**
- Consumes: `CrawlTaskTag`, `TaskTagRead`, and `tag_names` schemas from Task 1.
- Produces: `normalize_tag_names(tag_names: list[str] | None) -> list[str]`.
- Produces: `CrawlerTaskRepository.get_or_create_tags(owner_id: uuid.UUID, tag_names: list[str]) -> list[CrawlTaskTag]`.
- Produces: `CrawlerTaskRepository.replace_task_tags(task: CrawlTask, tags: list[CrawlTaskTag]) -> None`.
- Produces: `CrawlerTaskRepository.get_tags_by_owner(owner_id: uuid.UUID) -> list[CrawlTaskTag]`.
- Produces: `CrawlerTaskService.list_task_tags(owner_id: uuid.UUID) -> list[dict]`.
- Updates: `CrawlerTaskService.list_tasks(..., tag_names: list[str] | None = None)`.

- [ ] **Step 1: Write failing backend tests for tag persistence and filtering**

Add these tests to `backend/tests/test_crawler_tasks_api.py`:

```python
def create_tagged_task(client, headers, name, tags):
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": name,
            "storage_location": name,
            "tag_names": tags,
            "is_skip": False,
            "urls": [{"url": f"https://javdb.com/actors/{name}", "url_type": "actors"}],
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_create_task_with_tags_returns_tags(client, auth_headers):
    task = create_tagged_task(client, auth_headers, "tagged-task", ["VR", " 演员 ", "VR", ""])

    assert [tag["name"] for tag in task["tags"]] == ["VR", "演员"]


def test_task_list_includes_tags(client, auth_headers):
    create_tagged_task(client, auth_headers, "listed-tagged-task", ["VR"])

    response = client.get("/api/crawler/tasks", headers=auth_headers)

    assert response.status_code == 200
    row = response.json()["data"]["rows"][0]
    assert row["name"] == "listed-tagged-task"
    assert row["tags"][0]["name"] == "VR"


def test_tag_dictionary_returns_current_user_tags(client, auth_headers, other_user):
    create_tagged_task(client, auth_headers, "dict-a", ["VR", "演员"])
    create_tagged_task(client, auth_headers, "dict-b", ["VR", "系列"])

    response = client.get("/api/crawler/tasks/tags", headers=auth_headers)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["data"]] == ["VR", "演员", "系列"]


def test_update_task_replaces_and_clears_tags(client, auth_headers):
    task = create_tagged_task(client, auth_headers, "replace-tags", ["VR", "演员"])

    replaced = client.put(
        f"/api/crawler/tasks/{task['id']}",
        json={
            "name": "replace-tags",
            "tag_names": ["系列"],
            "urls": [{"url": "https://javdb.com/actors/replace-tags", "url_type": "actors"}],
            "is_skip": False,
        },
        headers=auth_headers,
    )
    assert replaced.status_code == 200
    assert [tag["name"] for tag in replaced.json()["data"]["tags"]] == ["系列"]

    cleared = client.put(
        f"/api/crawler/tasks/{task['id']}",
        json={"tag_names": []},
        headers=auth_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["tags"] == []


def test_update_task_omitting_tag_names_keeps_existing_tags(client, auth_headers):
    task = create_tagged_task(client, auth_headers, "keep-tags", ["VR"])

    response = client.put(
        f"/api/crawler/tasks/{task['id']}",
        json={"name": "keep-tags-renamed"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [tag["name"] for tag in response.json()["data"]["tags"]] == ["VR"]


def test_task_list_filters_by_all_selected_tags(client, auth_headers):
    create_tagged_task(client, auth_headers, "vr-actor", ["VR", "演员"])
    create_tagged_task(client, auth_headers, "vr-only", ["VR"])
    create_tagged_task(client, auth_headers, "actor-only", ["演员"])

    response = client.get(
        "/api/crawler/tasks?tag_names=VR&tag_names=演员",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["rows"][0]["name"] == "vr-actor"


def test_create_task_rejects_too_long_tag_name(client, auth_headers):
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "long-tag",
            "storage_location": "long-tag",
            "tag_names": ["标" * 51],
            "is_skip": False,
            "urls": [{"url": "https://javdb.com/actors/long-tag", "url_type": "actors"}],
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "标签长度不能超过 50 个字符" in response.json()["msg"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_create_task_with_tags_returns_tags tests/test_crawler_tasks_api.py::test_task_list_includes_tags tests/test_crawler_tasks_api.py::test_tag_dictionary_returns_current_user_tags tests/test_crawler_tasks_api.py::test_update_task_replaces_and_clears_tags tests/test_crawler_tasks_api.py::test_update_task_omitting_tag_names_keeps_existing_tags tests/test_crawler_tasks_api.py::test_task_list_filters_by_all_selected_tags tests/test_crawler_tasks_api.py::test_create_task_rejects_too_long_tag_name -v
```

Expected: FAIL because tag persistence, dictionary, and filtering do not exist.

- [ ] **Step 3: Add repository tag helpers and filtered queries**

In `backend/app/repositories/crawl_task.py`, import:

```python
from backend.app.models.crawl_task import CrawlTask, CrawlTaskTag, CrawlTaskUrl
```

Update `_owner_query` signature:

```python
def _owner_query(
    self,
    owner_id: uuid.UUID,
    keyword: str | None = None,
    tag_names: list[str] | None = None,
):
```

Add `.options(selectinload(CrawlTask.tags))` beside the existing URL loader.

Add all-match filtering:

```python
normalized_tags = [name.strip() for name in tag_names or [] if name.strip()]
if normalized_tags:
    tag_count = len(set(normalized_tags))
    matching_task_ids = (
        self.session.query(CrawlTask.id)
        .join(CrawlTask.tags)
        .filter(CrawlTask.owner_id == owner_id, CrawlTaskTag.name.in_(set(normalized_tags)))
        .group_by(CrawlTask.id)
        .having(func.count(func.distinct(CrawlTaskTag.name)) == tag_count)
        .subquery()
    )
    query = query.filter(CrawlTask.id.in_(self.session.query(matching_task_ids.c.id)))
```

Update `get_by_owner` and `count_by_owner` to accept and forward `tag_names`.

Add helpers:

```python
def get_tags_by_owner(self, owner_id: uuid.UUID) -> list[CrawlTaskTag]:
    return (
        self.session.query(CrawlTaskTag)
        .filter(CrawlTaskTag.owner_id == owner_id)
        .order_by(CrawlTaskTag.name.asc())
        .all()
    )

def get_or_create_tags(self, owner_id: uuid.UUID, tag_names: list[str]) -> list[CrawlTaskTag]:
    if not tag_names:
        return []
    existing = (
        self.session.query(CrawlTaskTag)
        .filter(CrawlTaskTag.owner_id == owner_id, CrawlTaskTag.name.in_(tag_names))
        .all()
    )
    by_name = {tag.name: tag for tag in existing}
    for name in tag_names:
        if name not in by_name:
            tag = CrawlTaskTag(owner_id=owner_id, name=name)
            self.session.add(tag)
            self.session.flush()
            by_name[name] = tag
    return [by_name[name] for name in tag_names]

def replace_task_tags(self, task: CrawlTask, tags: list[CrawlTaskTag]) -> None:
    task.tags = tags
```

- [ ] **Step 4: Add service normalization and tag save behavior**

In `backend/app/modules/crawler/tasks/service.py`, add:

```python
def normalize_tag_names(tag_names: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in tag_names or []:
        name = raw_name.strip()
        if not name or name in seen:
            continue
        if len(name) > 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标签长度不能超过 50 个字符")
        seen.add(name)
        normalized.append(name)
    return normalized
```

Add service helpers:

```python
def _tags_for_names(self, owner_id: uuid.UUID, tag_names: list[str] | None):
    return self.repo.get_or_create_tags(owner_id, normalize_tag_names(tag_names))

def list_task_tags(self, owner_id: uuid.UUID) -> list[dict[str, str]]:
    return [{"id": str(tag.id), "name": tag.name} for tag in self.repo.get_tags_by_owner(owner_id)]
```

Update `list_tasks` to accept `tag_names` and pass them to repository calls.

In `create_task`, after `created = self.repo.create_with_urls(...)`, add:

```python
if data.tag_names is not None:
    self.repo.replace_task_tags(created, self._tags_for_names(owner_id, data.tag_names))
    self.db.commit()
    self.db.refresh(created)
    created = self.repo.get_owned(created.id, owner_id) or created
```

In `update_task`, after URL replacement and before `self.repo.update(task)`, add:

```python
if data.tag_names is not None:
    self.repo.replace_task_tags(task, self._tags_for_names(owner_id, data.tag_names))
```

In `batch_create_tasks`, after each successful `create_with_urls`, attach tags if `data.tag_names is not None` using the same helper and commit/refresh before serialization.

- [ ] **Step 5: Add router params and tag endpoint**

In `backend/app/modules/crawler/tasks/router.py`, add `list[str] | None` query support:

```python
tag_names: list[str] | None = Query(default=None),
```

Pass `tag_names=tag_names` to `service.list_tasks`.

Add this route before UUID routes:

```python
@router.get("/tags")
def list_task_tags(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.list_task_tags(current_user.id))
```

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_create_task_with_tags_returns_tags tests/test_crawler_tasks_api.py::test_task_list_includes_tags tests/test_crawler_tasks_api.py::test_tag_dictionary_returns_current_user_tags tests/test_crawler_tasks_api.py::test_update_task_replaces_and_clears_tags tests/test_crawler_tasks_api.py::test_update_task_omitting_tag_names_keeps_existing_tags tests/test_crawler_tasks_api.py::test_task_list_filters_by_all_selected_tags tests/test_crawler_tasks_api.py::test_create_task_rejects_too_long_tag_name -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/app/repositories/crawl_task.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_tasks_api.py
git diff --cached --name-only
git commit -m "feat: persist and filter crawler task tags"
```

---

### Task 3: Backend Batch Run API

**Files:**
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Test: `backend/tests/test_crawler_tasks_api.py`

**Interfaces:**
- Produces: `CrawlTaskBatchRunCreate` with `task_ids: list[uuid.UUID]` and `crawl_mode: Literal["incremental", "full"]`.
- Produces: `CrawlTaskBatchRunAcceptedItem` with `task_id: uuid.UUID` and `run_id: uuid.UUID`.
- Produces: `CrawlTaskBatchRunFailedItem` with `task_id: uuid.UUID` and `reason: str`.
- Produces: `CrawlTaskBatchRunResult` with `accepted`, `failed`, `accepted_count`, and `failed_count`.
- Produces: `CrawlerTaskService.batch_run_tasks(data: CrawlTaskBatchRunCreate, owner_id: uuid.UUID) -> dict`.
- Produces: `POST /api/crawler/tasks/batch-run`.

- [ ] **Step 1: Write failing batch-run tests**

Add these tests to `backend/tests/test_crawler_tasks_api.py`:

```python
def test_batch_run_creates_one_run_per_idle_task(client, auth_headers, monkeypatch):
    from backend.app.modules.crawler.tasks import service as task_service

    task_a = create_tagged_task(client, auth_headers, "batch-run-a", ["VR"])
    task_b = create_tagged_task(client, auth_headers, "batch-run-b", ["VR"])

    class FakeRun:
        def __init__(self, run_id):
            self.id = run_id

    created_modes = []

    class FakeRunService:
        def __init__(self, db, runtime_state):
            pass

        def create_run(self, task, crawl_mode):
            created_modes.append((task.name, crawl_mode))
            return FakeRun(f"run-{task.name}")

    monkeypatch.setattr(task_service, "CrawlerRunService", FakeRunService)
    monkeypatch.setattr(task_service, "get_runtime_state", lambda: object())

    response = client.post(
        "/api/crawler/tasks/batch-run",
        json={"task_ids": [task_a["id"], task_b["id"]], "crawl_mode": "incremental"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["accepted_count"] == 2
    assert data["failed_count"] == 0
    assert [item["task_id"] for item in data["accepted"]] == [task_a["id"], task_b["id"]]
    assert created_modes == [("batch-run-a", "incremental"), ("batch-run-b", "incremental")]


def test_batch_run_returns_per_task_failures(client, auth_headers, monkeypatch):
    from backend.app.modules.crawler.tasks import service as task_service

    runnable = create_tagged_task(client, auth_headers, "batch-run-ok", ["VR"])
    skipped = client.post(
        "/api/crawler/tasks",
        json={
            "name": "batch-run-skipped",
            "storage_location": "batch-run-skipped",
            "tag_names": ["VR"],
            "is_skip": True,
            "urls": [{"url": "https://javdb.com/actors/batch-run-skipped", "url_type": "actors"}],
        },
        headers=auth_headers,
    ).json()["data"]

    class FakeRun:
        id = "run-ok"

    class FakeRunService:
        def __init__(self, db, runtime_state):
            pass

        def create_run(self, task, crawl_mode):
            return FakeRun()

    monkeypatch.setattr(task_service, "CrawlerRunService", FakeRunService)
    monkeypatch.setattr(task_service, "get_runtime_state", lambda: object())

    response = client.post(
        "/api/crawler/tasks/batch-run",
        json={
            "task_ids": [
                runnable["id"],
                skipped["id"],
                "00000000-0000-0000-0000-000000000000",
                runnable["id"],
            ],
            "crawl_mode": "full",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["accepted_count"] == 1
    assert data["failed"] == [
        {"task_id": skipped["id"], "reason": "禁用任务不能执行"},
        {"task_id": "00000000-0000-0000-0000-000000000000", "reason": "Task not found"},
    ]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_batch_run_creates_one_run_per_idle_task tests/test_crawler_tasks_api.py::test_batch_run_returns_per_task_failures -v
```

Expected: FAIL because schemas, service, and route do not exist.

- [ ] **Step 3: Add batch-run schemas**

In `backend/app/schemas/crawl_task.py`, add:

```python
class CrawlTaskBatchRunCreate(BaseModel):
    task_ids: list[uuid.UUID] = Field(..., min_length=1)
    crawl_mode: Literal["incremental", "full"]


class CrawlTaskBatchRunAcceptedItem(BaseModel):
    task_id: uuid.UUID
    run_id: uuid.UUID | str


class CrawlTaskBatchRunFailedItem(BaseModel):
    task_id: uuid.UUID
    reason: str


class CrawlTaskBatchRunResult(BaseModel):
    accepted: list[CrawlTaskBatchRunAcceptedItem]
    failed: list[CrawlTaskBatchRunFailedItem]
    accepted_count: int
    failed_count: int
```

- [ ] **Step 4: Add service method**

In `backend/app/modules/crawler/tasks/service.py`, import the new schemas and add:

```python
def _unique_task_ids(self, task_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    unique_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for task_id in task_ids:
        if task_id in seen:
            continue
        seen.add(task_id)
        unique_ids.append(task_id)
    return unique_ids

def batch_run_tasks(self, data: CrawlTaskBatchRunCreate, owner_id: uuid.UUID) -> dict:
    accepted: list[CrawlTaskBatchRunAcceptedItem] = []
    failed: list[CrawlTaskBatchRunFailedItem] = []

    for task_id in self._unique_task_ids(list(data.task_ids)):
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            failed.append(CrawlTaskBatchRunFailedItem(task_id=task_id, reason="Task not found"))
            continue
        if task.is_skip:
            failed.append(CrawlTaskBatchRunFailedItem(task_id=task_id, reason="禁用任务不能执行"))
            continue
        try:
            run = CrawlerRunService(self.db, get_runtime_state()).create_run(task, data.crawl_mode)
            accepted.append(CrawlTaskBatchRunAcceptedItem(task_id=task_id, run_id=run.id))
        except Exception as exc:
            self.db.rollback()
            logger.exception("Create crawler batch run failed for task %s", task_id)
            failed.append(CrawlTaskBatchRunFailedItem(task_id=task_id, reason=f"任务运行时不可用: {exc}"))

    return CrawlTaskBatchRunResult(
        accepted=accepted,
        failed=failed,
        accepted_count=len(accepted),
        failed_count=len(failed),
    ).model_dump(mode="json")
```

- [ ] **Step 5: Add route before UUID routes**

In `backend/app/modules/crawler/tasks/router.py`, import `CrawlTaskBatchRunCreate` and add:

```python
@router.post("/batch-run", status_code=status.HTTP_201_CREATED)
def batch_run_tasks(
    data: CrawlTaskBatchRunCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    service = CrawlerTaskService(db)
    return success(data=service.batch_run_tasks(data, current_user.id))
```

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py::test_batch_run_creates_one_run_per_idle_task tests/test_crawler_tasks_api.py::test_batch_run_returns_per_task_failures -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/service.py backend/app/modules/crawler/tasks/router.py backend/tests/test_crawler_tasks_api.py
git diff --cached --name-only
git commit -m "feat: add crawler task batch run api"
```

---

### Task 4: Frontend Task Tag APIs And Form Inputs

**Files:**
- Modify: `frontend/src/api/queryKeys.ts`
- Modify: `frontend/src/api/crawler/crawlTask/types.ts`
- Modify: `frontend/src/api/crawler/crawlTask/index.ts`
- Create: `frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx`

**Interfaces:**
- Produces: `TaskTag` frontend type with `id: string` and `name: string`.
- Produces: `CrawlTask.tags: TaskTag[]`.
- Produces: `CrawlTaskCreateParams.tag_names?: string[]`.
- Produces: `CrawlTaskUpdateParams.tag_names?: string[]`.
- Produces: `BatchCrawlTaskCreateParams.tag_names?: string[]`.
- Produces: `getCrawlTaskTags(): Promise<TaskTag[]>`.
- Produces: `TaskTagSelect` controlled by an Ant Design `Form.Item`.

- [ ] **Step 1: Write failing frontend tests for form and drawer tag submit**

In `frontend/src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx`, update the crawl-task API mock:

```ts
getCrawlTaskTags: vi.fn(),
```

Import it:

```ts
import { getCrawlTaskTags } from '@/api/crawler/crawlTask'
```

In `beforeEach`, add:

```ts
vi.mocked(getCrawlTaskTags).mockResolvedValue([{ id: 'tag-vr', name: 'VR' }] as never)
```

Add this test:

```tsx
it('submits selected and custom tag names during task create', async () => {
  paramsMock = {}
  render(<TaskFormPage />, { wrapper })

  await userEvent.type(screen.getByLabelText('任务名称'), 'Tagged Task')
  await userEvent.type(screen.getByLabelText('网盘路径'), 'Tagged Task')
  await userEvent.click(screen.getByLabelText('任务标签'))
  await userEvent.click(await screen.findByText('VR'))
  await userEvent.type(screen.getByLabelText('任务标签'), '自定义{enter}')
  await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/tagged-create')
  fireEvent.click(await screen.findByText('创 建'))

  await waitFor(() => {
    expect(createCrawlTask).toHaveBeenCalledWith(expect.objectContaining({
      tag_names: ['VR', '自定义'],
    }))
  })
})
```

In `frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx`, add a test:

```tsx
it('submits tag names with batch create values', async () => {
  render(
    <BatchTaskCreateDrawer
      open
      submitting={false}
      failedUrls={[]}
      tagOptions={[{ id: 'tag-vr', name: 'VR' }]}
      onCancel={vi.fn()}
      onSubmit={onSubmit}
    />,
    { wrapper },
  )

  await userEvent.type(screen.getByLabelText('URL 列表'), 'https://javdb.com/actors/a')
  await userEvent.click(screen.getByLabelText('任务标签'))
  await userEvent.click(await screen.findByText('VR'))
  await userEvent.type(screen.getByLabelText('任务标签'), '自定义{enter}')
  fireEvent.click(screen.getByRole('button', { name: '保 存' }))

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      tag_names: ['VR', '自定义'],
    }))
  })
})
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx
```

Expected: FAIL because task tag API/types/components do not exist.

- [ ] **Step 3: Add frontend types and API functions**

In `frontend/src/api/crawler/crawlTask/types.ts`, add:

```ts
export interface TaskTag {
  id: string
  name: string
}
```

Add `tags: TaskTag[]` to `CrawlTask` and `CrawlTaskListItem`.

Add `tag_names?: string[]` to `CrawlTaskCreateParams`, `CrawlTaskUpdateParams`, and `BatchCrawlTaskCreateParams`.

In `frontend/src/api/queryKeys.ts`, add:

```ts
tags: () => ['crawlerTasks', 'tags'] as const,
```

under `crawlerTasks`.

In `frontend/src/api/crawler/crawlTask/index.ts`, add:

```ts
export function getCrawlTaskTags(): Promise<TaskTag[]> {
  return request.get<TaskTag[]>(`${BASE_URL}/tags`)
}
```

- [ ] **Step 4: Add shared `TaskTagSelect` component**

Create `frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx`:

```tsx
import { Select } from 'antd'
import type { TaskTag } from '@/api/crawler/crawlTask/types'

interface TaskTagSelectProps {
  options: TaskTag[]
  loading?: boolean
  placeholder?: string
}

export default function TaskTagSelect({
  options,
  loading = false,
  placeholder = '选择或输入标签',
}: TaskTagSelectProps) {
  return (
    <Select
      mode="tags"
      allowClear
      loading={loading}
      placeholder={placeholder}
      options={options.map((tag) => ({ value: tag.name, label: tag.name }))}
    />
  )
}
```

- [ ] **Step 5: Wire tags into `TaskFormPage`**

In `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`, import `useQuery`, `getCrawlTaskTags`, `queryKeys`, and `TaskTagSelect`.

Add:

```ts
const tagOptionsQuery = useQuery({
  queryKey: queryKeys.crawlerTasks.tags(),
  queryFn: getCrawlTaskTags,
})
```

When loading edit task values, add:

```ts
tag_names: task.tags?.map((tag) => tag.name) ?? [],
```

In `payload`, add:

```ts
tag_names: values.tag_names ?? [],
```

Render near the name/storage fields:

```tsx
<Form.Item name="tag_names" label="任务标签">
  <TaskTagSelect options={tagOptionsQuery.data ?? []} loading={tagOptionsQuery.isLoading} />
</Form.Item>
```

Add `tag_names: []` to form initial values.

- [ ] **Step 6: Wire tags into `BatchTaskCreateDrawer`**

Extend `BatchTaskCreateFormValues` with:

```ts
tag_names: string[]
```

Extend props:

```ts
tagOptions: TaskTag[]
tagOptionsLoading?: boolean
```

Add `tag_names` to internal form values and initial values. Render:

```tsx
<Form.Item name="tag_names" label="任务标签">
  <TaskTagSelect options={tagOptions} loading={tagOptionsLoading} />
</Form.Item>
```

Submit:

```ts
tag_names: values.tag_names ?? [],
```

- [ ] **Step 7: Run focused frontend tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add frontend/src/api/queryKeys.ts frontend/src/api/crawler/crawlTask/types.ts frontend/src/api/crawler/crawlTask/index.ts frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx frontend/src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx
git diff --cached --name-only
git commit -m "feat: add crawler task tag inputs"
```

---

### Task 5: Frontend Tag Filtering And Card Display

**Files:**
- Modify: `frontend/src/api/queryKeys.ts`
- Modify: `frontend/src/api/crawler/crawlTask/index.ts`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`

**Interfaces:**
- Consumes: `TaskTag` and `getCrawlTaskTags` from Task 4.
- Produces: `getCrawlTasks` accepts `tag_names?: string[]`.
- Produces: `useTaskListData({ tagNames }: { tagNames: string[] })`.
- Produces: `TaskListCards` props for `tagOptions`, `selectedTagNames`, and `onTagFilterChange`.

- [ ] **Step 1: Write failing tests for card tag display and filtering**

In `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`, update `baseTask`:

```ts
tags: [{ id: 'tag-vr', name: 'VR' }, { id: 'tag-actor', name: '演员' }],
```

Add a render expectation in the first test:

```ts
expect(screen.getByText('VR')).toBeInTheDocument()
expect(screen.getByText('演员')).toBeInTheDocument()
```

Add this test:

```tsx
it('calls tag filter change from the toolbar', async () => {
  const onTagFilterChange = vi.fn()
  render(
    <TaskListCards
      tasks={[baseTask as never]}
      loading={false}
      total={1}
      runtimeByTaskId={{ 'task-1': { task_id: 'task-1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2026-09-04T00:00:00Z', last_run_at: null } } as never}
      runtimeReady={true}
      tagOptions={[{ id: 'tag-vr', name: 'VR' }]}
      selectedTagNames={[]}
      onTagFilterChange={onTagFilterChange}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleSkip={vi.fn()}
      onRun={vi.fn()}
      onStop={vi.fn()}
      onRestart={vi.fn()}
      onUrlRun={vi.fn()}
      onTemporaryTaskClick={vi.fn()}
      onBatchTaskClick={vi.fn()}
      selectedTaskIds={[]}
      onSelectedTaskIdsChange={vi.fn()}
      onBatchRunClick={vi.fn()}
      batchRunLoading={false}
      current={1}
      pageSize={20}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />,
  )

  await userEvent.click(screen.getByLabelText('标签筛选'))
  await userEvent.click(await screen.findByText('VR'))

  expect(onTagFilterChange).toHaveBeenCalledWith(['VR'])
})
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: FAIL because tag display/filter props are not implemented.

- [ ] **Step 3: Add `tag_names` to API query types**

In `frontend/src/api/crawler/crawlTask/index.ts`, change `getCrawlTasks` params to:

```ts
params: {
  page: number
  size: number
  keyword?: string
  tag_names?: string[]
}
```

In `frontend/src/api/queryKeys.ts`, change crawler task list params similarly:

```ts
list: (params: { page: number; size: number; keyword?: string; tag_names?: string[] }) =>
  ['crawlerTasks', params] as const,
```

- [ ] **Step 4: Thread tag filters through `useTaskListData`**

Change signature:

```ts
export function useTaskListData({ tagNames = [] }: { tagNames?: string[] } = {}) {
```

Update `listParams`:

```ts
const listParams = useMemo(
  () => ({
    page: current,
    size: pageSize,
    ...(tagNames.length > 0 ? { tag_names: tagNames } : {}),
  }),
  [current, pageSize, tagNames],
)
```

- [ ] **Step 5: Add filter state and tag options in `TaskListPage`**

In `frontend/src/pages/crawler/tasks/TaskListPage.tsx`, use `useQuery`:

```ts
const [selectedTagNames, setSelectedTagNames] = useState<string[]>([])
const tagOptionsQuery = useQuery({
  queryKey: queryKeys.crawlerTasks.tags(),
  queryFn: getCrawlTaskTags,
})
```

Pass `useTaskListData({ tagNames: selectedTagNames })`.

When tag filters change:

```ts
const handleTagFilterChange = useCallback((nextTags: string[]) => {
  setSelectedTagNames(nextTags)
  setCurrent(1)
  setSelectedTaskIds([])
}, [setCurrent])
```

- [ ] **Step 6: Render tag filter and card tags**

In `TaskListCards`, import `Checkbox`, `Select` if needed. Add props:

```ts
tagOptions: TaskTag[]
selectedTagNames: string[]
onTagFilterChange: (tagNames: string[]) => void
```

Render in toolbar:

```tsx
<Select
  aria-label="标签筛选"
  mode="multiple"
  allowClear
  placeholder="标签筛选"
  value={selectedTagNames}
  options={tagOptions.map((tag) => ({ value: tag.name, label: tag.name }))}
  onChange={onTagFilterChange}
  className={styles.taskTagFilter}
/>
```

Add `getTaskTags(task)` and render a metadata row:

```tsx
<div className={styles.taskMetaRow}>
  <span className={styles.taskMetaLabel}>任务标签</span>
  <TaskTagTags tags={task.tags ?? []} />
</div>
```

`TaskTagTags` mirrors `UrlNameTags`: show up to three tags, then a `+N` popover.

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add frontend/src/api/queryKeys.ts frontend/src/api/crawler/crawlTask/index.ts frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
git diff --cached --name-only
git commit -m "feat: filter crawler tasks by tags"
```

---

### Task 6: Frontend Selection And Batch Run

**Files:**
- Modify: `frontend/src/api/crawler/crawlTask/types.ts`
- Modify: `frontend/src/api/crawler/crawlTask/index.ts`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`

**Interfaces:**
- Consumes: `POST /api/crawler/tasks/batch-run` from Task 3.
- Produces: `batchRunCrawlTasks(data: BatchCrawlTaskRunParams): Promise<BatchCrawlTaskRunResult>`.
- Produces: `BatchCrawlTaskRunParams`, `BatchCrawlTaskRunAcceptedItem`, `BatchCrawlTaskRunFailedItem`, `BatchCrawlTaskRunResult`.
- Produces: `TaskListCards` props for `selectedTaskIds`, `onSelectedTaskIdsChange`, `onBatchRunClick`, and `batchRunLoading`.

- [ ] **Step 1: Write failing frontend tests for selection and batch run button**

In `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`, add:

```tsx
it('tracks card selection and enables batch run button', async () => {
  const onSelectedTaskIdsChange = vi.fn()
  const onBatchRunClick = vi.fn()
  render(
    <TaskListCards
      tasks={[baseTask as never]}
      loading={false}
      total={1}
      runtimeByTaskId={{ 'task-1': { task_id: 'task-1', runtime_status: 'idle', latest_run_id: null, state_updated_at: '2026-09-04T00:00:00Z', last_run_at: null } } as never}
      runtimeReady={true}
      tagOptions={[]}
      selectedTagNames={[]}
      onTagFilterChange={vi.fn()}
      selectedTaskIds={[]}
      onSelectedTaskIdsChange={onSelectedTaskIdsChange}
      onBatchRunClick={onBatchRunClick}
      batchRunLoading={false}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleSkip={vi.fn()}
      onRun={vi.fn()}
      onStop={vi.fn()}
      onRestart={vi.fn()}
      onUrlRun={vi.fn()}
      onTemporaryTaskClick={vi.fn()}
      onBatchTaskClick={vi.fn()}
      current={1}
      pageSize={20}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
    />,
  )

  expect(screen.getByRole('button', { name: /批量爬取/ })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: /选择 Aligned Task/ }))
  expect(onSelectedTaskIdsChange).toHaveBeenCalledWith(['task-1'])
})
```

Add a second test with `selectedTaskIds={['task-1']}` and assert clicking `批量爬取` calls `onBatchRunClick`.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: FAIL because selection and batch-run controls are missing.

- [ ] **Step 3: Add frontend batch-run API types and function**

In `frontend/src/api/crawler/crawlTask/types.ts`, add:

```ts
export interface BatchCrawlTaskRunParams {
  task_ids: string[]
  crawl_mode: 'incremental' | 'full'
}

export interface BatchCrawlTaskRunAcceptedItem {
  task_id: string
  run_id: string
}

export interface BatchCrawlTaskRunFailedItem {
  task_id: string
  reason: string
}

export interface BatchCrawlTaskRunResult {
  accepted: BatchCrawlTaskRunAcceptedItem[]
  failed: BatchCrawlTaskRunFailedItem[]
  accepted_count: number
  failed_count: number
}
```

In `frontend/src/api/crawler/crawlTask/index.ts`, add:

```ts
export function batchRunCrawlTasks(
  data: BatchCrawlTaskRunParams,
): Promise<BatchCrawlTaskRunResult> {
  return request.post<BatchCrawlTaskRunResult>(`${BASE_URL}/batch-run`, data)
}
```

- [ ] **Step 4: Add selection UI to `TaskListCards`**

Add props:

```ts
selectedTaskIds: string[]
onSelectedTaskIdsChange: (ids: string[]) => void
onBatchRunClick: () => void
batchRunLoading: boolean
```

For each card, compute:

```ts
const isSelectable = runtimeReady && runtimeStatus === 'idle' && !task.is_skip
```

Render a checkbox near the card title:

```tsx
<Checkbox
  aria-label={`选择 ${task.name}`}
  checked={selectedTaskIds.includes(task.id)}
  disabled={!isSelectable}
  onChange={(event) => {
    const checked = event.target.checked
    onSelectedTaskIdsChange(
      checked
        ? [...selectedTaskIds, task.id]
        : selectedTaskIds.filter((id) => id !== task.id),
    )
  }}
/>
```

Render toolbar selected count and batch-run button:

```tsx
<Typography.Text type="secondary">已选 {selectedTaskIds.length} 个</Typography.Text>
<Button
  disabled={selectedTaskIds.length === 0}
  loading={batchRunLoading}
  onClick={onBatchRunClick}
>
  批量爬取
</Button>
```

- [ ] **Step 5: Add batch-run state and modal behavior in `TaskListPage`**

In `TaskListPage`, add:

```ts
const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([])
const [batchRunSubmitting, setBatchRunSubmitting] = useState(false)
```

Import `Modal` from `antd` and `batchRunCrawlTasks`.

Add:

```ts
const markBatchRunsQueued = useCallback((accepted: BatchCrawlTaskRunAcceptedItem[]) => {
  const now = new Date().toISOString()
  for (const item of accepted) {
    useCrawlerRuntimeStore.getState().upsertTaskRuntime({
      task_id: item.task_id,
      runtime_status: 'queued',
      latest_run_id: item.run_id,
      state_updated_at: now,
      last_run_at: now,
    })
  }
}, [])
```

Add confirm function:

```ts
const openBatchRunConfirm = useCallback(() => {
  let crawlMode: CrawlMode = 'incremental'
  Modal.confirm({
    title: '批量爬取',
    content: (
      <Select<CrawlMode>
        aria-label="爬取模式"
        defaultValue="incremental"
        options={[
          { value: 'incremental', label: '增量爬取' },
          { value: 'full', label: '全量爬取' },
        ]}
        onChange={(value) => {
          crawlMode = value
        }}
        style={{ width: '100%' }}
      />
    ),
    okText: '开始',
    cancelText: '取消',
    onOk: async () => {
      setBatchRunSubmitting(true)
      try {
        const result = await batchRunCrawlTasks({ task_ids: selectedTaskIds, crawl_mode: crawlMode })
        markBatchRunsQueued(result.accepted)
        await invalidateCrawlerRunLists(queryClient)
        setSelectedTaskIds([])
        if (result.failed_count > 0) {
          await message.warning(`已提交 ${result.accepted_count} 个任务，${result.failed_count} 个失败`)
        } else {
          await message.success(`已提交 ${result.accepted_count} 个任务`)
        }
      } catch (error) {
        await message.error(error instanceof Error ? error.message : '批量爬取失败')
      } finally {
        setBatchRunSubmitting(false)
      }
    },
  })
}, [markBatchRunsQueued, message, queryClient, selectedTaskIds])
```

Clear selection on filter/page changes:

```ts
const handlePageChange = useCallback((page: number) => {
  setSelectedTaskIds([])
  setCurrent(page)
}, [setCurrent])
```

Use similar wrappers for page size and tag filter changes.

- [ ] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add frontend/src/api/crawler/crawlTask/types.ts frontend/src/api/crawler/crawlTask/index.ts frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
git diff --cached --name-only
git commit -m "feat: batch run selected crawler tasks"
```

---

### Task 7: Final Verification

**Files:**
- Modify only files needed for compile/test fixes discovered by verification.
- Do not edit generated build output.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: verified backend and frontend behavior for crawler task tags and batch run.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd backend && python -m pytest tests/test_crawler_tasks_api.py tests/test_crawl_tasks_api.py tests/test_crawler_task_url_subset_run.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused task tests**

Run:

```bash
cd frontend && pnpm test -- src/pages/crawler/tasks
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && pnpm build
```

Expected: PASS.

- [ ] **Step 4: Inspect Git state**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intentional source, test, migration, SQL, spec, or plan files are present.

- [ ] **Step 5: Commit verification fixes if any**

If verification required code or test fixes, stage exact files and commit them:

```bash
git add <exact files changed by verification fixes>
git diff --cached --name-only
git commit -m "test: verify crawler task tags and batch run"
```

If no files changed during final verification, skip this commit.
