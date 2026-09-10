# Actress-Only Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove crawler task tags completely and make tags a normalized actress-only feature.

**Architecture:** Add `actress_tags` and `actress_tag_links` as the only tag tables for actress profiles. Remove task tag models, APIs, request fields, frontend controls, backup exports, and restore handling. Keep actress API response shape as `tags: string[]` while storing tags through per-user tag rows and links.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, pytest, React 19, TanStack Query, Ant Design, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-10-actress-only-tags-design.md`

## Global Constraints

- Do not preserve task tag filtering in the task list.
- Do not keep `/api/crawler/tasks/tags` as a compatibility endpoint.
- Do not add generic content tags that can attach to many entity types.
- Do not change movie tag storage or movie filter behavior.
- Do not add tag color, ordering, groups, or counts.
- Existing `actress_profiles.tags` values become actress tag rows and links.
- Existing task tags are copied to actresses whose `source_task_ids` contain the tagged task id.
- Task tags that cannot be associated with any actress are intentionally dropped.
- Serialization for actress API requests must only include tags owned by the current user.
- Keep movie tags and movie magnet tags unchanged.
- Preserve unrelated local changes, including the existing unstaged `scraper/spiders/javdb/javdb_spider.py` change.

---

## File Structure

- `shared/database/models/content.py`: add `ActressTag`, `actress_tag_links`, and relationship-backed `ActressProfile.tags`.
- `backend/app/models/crawl_task.py`: remove task tag association table, model, and relationship.
- `backend/alembic/versions/20260910_0002_normalize_actress_tags.py`: create normalized actress tag tables, migrate old data, and remove task tag tables / array column.
- `sql/20260910_normalize_actress_tags.sql`: mirror Alembic upgrade SQL.
- `backend/app/modules/content/actresses/tag_service.py`: isolate tag normalization, dictionary listing, row creation, and relationship replacement.
- `backend/app/modules/content/actresses/queries.py`: filter actress profiles by relationship tags and user ownership.
- `backend/app/modules/content/actresses/serializers.py`: serialize relationship tag names for the current user.
- `backend/app/modules/content/actresses/router.py`: add tag dictionary route and pass `current_user.id` into queries/serialization/update.
- `backend/app/modules/content/actresses/service.py`: remove task tag merging and call serializer with user-owned tags.
- `backend/app/schemas/crawl_task.py`: remove `tag_names`, `TaskTagRead`, and task response `tags`.
- `backend/app/modules/crawler/tasks/router.py`: remove `/tags` endpoint and `tag_names` query parameter.
- `backend/app/modules/crawler/tasks/service.py`: remove tag normalization, task tag creation, and tag filtering.
- `backend/app/repositories/crawl_task.py`: remove tag joins/filtering and tag helper methods.
- `backend/app/modules/crawler/tasks/serializers.py`: stop serializing task tags.
- `backend/app/modules/backup/exporters.py`: export actress tag tables and stop exporting task tag tables.
- `backend/app/modules/backup/restorers.py`: restore actress tag tables and ignore old task tag files.
- `frontend/src/api/crawler/crawlTask/index.ts`: remove `getCrawlTaskTags`.
- `frontend/src/api/crawler/crawlTask/types.ts`: remove `TaskTag`, `tag_names`, and task `tags`.
- `frontend/src/api/content/actresses/types.ts`: add `ActressTag`.
- `frontend/src/api/content/actresses/index.ts`: add `getActressTags`.
- `frontend/src/api/queryKeys.ts`: remove `crawlerTasks.tags`, add `actresses.tags`.
- `frontend/src/pages/crawler/tasks/**`: remove task tag UI and filtering state.
- `frontend/src/pages/content/actresses/**`: load actress tag options in list/detail and invalidate them after updates.
- `backend/tests/test_content_actresses_api.py`, `backend/tests/test_crawler_tasks_api.py`, backup tests, frontend Vitest tests: update coverage for the new model and removed task tag behavior.

---

### Task 1: Database Migration And ORM Model

**Files:**
- Modify: `shared/database/models/content.py`
- Modify: `backend/app/models/crawl_task.py`
- Create: `backend/alembic/versions/20260910_0002_normalize_actress_tags.py`
- Create: `sql/20260910_normalize_actress_tags.sql`
- Modify: `backend/tests/test_crawler_tasks_api.py`
- Modify: `backend/tests/test_content_actresses_api.py`

**Interfaces:**
- Produces: `ActressTag` ORM model with `id`, `owner_id`, `name`, timestamps.
- Produces: `actress_tag_links` SQLAlchemy table with `actress_profile_id`, `tag_id`.
- Produces: `ActressProfile.tags: Mapped[list[ActressTag]]`.
- Removes: `CrawlTaskTag`, `crawl_task_tag_links`, and `CrawlTask.tags`.

- [ ] **Step 1: Write failing metadata tests**

In `backend/tests/test_crawler_tasks_api.py`, replace the task tag metadata assertion with:

```python
def test_crawler_task_metadata_has_no_task_tag_tables() -> None:
    from shared.database.models.base import Base

    assert "crawl_task_tags" not in Base.metadata.tables
    assert "crawl_task_tag_links" not in Base.metadata.tables
```

In `backend/tests/test_content_actresses_api.py`, add:

```python
def test_actress_tag_metadata_contains_normalized_tables() -> None:
    from shared.database.models.base import Base

    assert "actress_tags" in Base.metadata.tables
    assert "actress_tag_links" in Base.metadata.tables
```

- [ ] **Step 2: Run metadata tests and verify they fail**

Run:

```bash
python -m pytest backend/tests/test_crawler_tasks_api.py::test_crawler_task_metadata_has_no_task_tag_tables backend/tests/test_content_actresses_api.py::test_actress_tag_metadata_contains_normalized_tables -v
```

Expected: fails because task tag tables still exist in metadata and actress tag tables do not.

- [ ] **Step 3: Update ORM models**

In `backend/app/models/crawl_task.py`:

- Remove imports of `Column` and `Table` if they become unused.
- Delete `crawl_task_tag_links`.
- Delete `CrawlTask.tags`.
- Delete `CrawlTaskTag`.

In `shared/database/models/content.py`:

- Import `Column`, `String`, and `Table` if needed.
- Add:

```python
actress_tag_links = Table(
    "actress_tag_links",
    Base.metadata,
    Column("actress_profile_id", ForeignKey("actress_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("actress_tags.id", ondelete="CASCADE"), primary_key=True),
    Index("idx_actress_tag_links_profile_id", "actress_profile_id"),
    Index("idx_actress_tag_links_tag_id", "tag_id"),
)
```

- Add:

```python
class ActressTag(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "actress_tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_actress_tags_owner_name"),
        Index("idx_actress_tags_owner_name", "owner_id", "name"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    profiles: Mapped[list["ActressProfile"]] = relationship(
        secondary=actress_tag_links,
        back_populates="tags",
        lazy="selectin",
    )
```

- In `ActressProfile.__table_args__`, remove `Index("idx_actress_profiles_tags_gin", "tags", postgresql_using="gin")`.
- Replace the `tags` array column with:

```python
tags: Mapped[list[ActressTag]] = relationship(
    secondary=actress_tag_links,
    back_populates="profiles",
    order_by="ActressTag.name",
    lazy="selectin",
)
```

- [ ] **Step 4: Create Alembic migration**

Create `backend/alembic/versions/20260910_0002_normalize_actress_tags.py`:

```python
"""normalize actress tags

Revision ID: 20260910_0002
Revises: 20260910_0001
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260910_0002"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actress_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_actress_tags_owner_name"),
    )
    op.create_index("idx_actress_tags_owner_name", "actress_tags", ["owner_id", "name"])
    op.create_index(op.f("ix_actress_tags_owner_id"), "actress_tags", ["owner_id"])

    op.create_table(
        "actress_tag_links",
        sa.Column("actress_profile_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["actress_profile_id"], ["actress_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["actress_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("actress_profile_id", "tag_id"),
    )
    op.create_index("idx_actress_tag_links_profile_id", "actress_tag_links", ["actress_profile_id"])
    op.create_index("idx_actress_tag_links_tag_id", "actress_tag_links", ["tag_id"])

    op.execute("""
        INSERT INTO actress_tags (id, owner_id, name, created_at)
        SELECT gen_random_uuid(), owners.owner_id, trimmed.name, now()
        FROM (
            SELECT DISTINCT ct.owner_id
            FROM crawl_tasks ct
            UNION
            SELECT DISTINCT ctt.owner_id
            FROM crawl_task_tags ctt
        ) AS owners
        CROSS JOIN LATERAL (
            SELECT DISTINCT btrim(tag_value) AS name
            FROM actress_profiles ap
            CROSS JOIN LATERAL unnest(ap.tags) AS tag_value
            WHERE btrim(tag_value) <> ''
        ) AS trimmed
        ON CONFLICT (owner_id, name) DO NOTHING
    """)

    op.execute("""
        INSERT INTO actress_tags (id, owner_id, name, created_at)
        SELECT gen_random_uuid(), ctt.owner_id, ctt.name, now()
        FROM crawl_task_tags ctt
        WHERE btrim(ctt.name) <> ''
        ON CONFLICT (owner_id, name) DO NOTHING
    """)

    op.execute("""
        INSERT INTO actress_tag_links (actress_profile_id, tag_id)
        SELECT DISTINCT ap.id, at.id
        FROM actress_profiles ap
        JOIN crawl_tasks ct ON ct.id = ANY(ap.source_task_ids)
        CROSS JOIN LATERAL unnest(ap.tags) AS tag_value
        JOIN actress_tags at
            ON at.owner_id = ct.owner_id
           AND at.name = btrim(tag_value)
        WHERE btrim(tag_value) <> ''
        ON CONFLICT DO NOTHING
    """)

    op.execute("""
        INSERT INTO actress_tag_links (actress_profile_id, tag_id)
        SELECT DISTINCT ap.id, at.id
        FROM crawl_task_tag_links ctl
        JOIN crawl_task_tags ctt ON ctt.id = ctl.tag_id
        JOIN crawl_tasks ct ON ct.id = ctl.task_id
        JOIN actress_profiles ap ON ctl.task_id = ANY(ap.source_task_ids)
        JOIN actress_tags at ON at.owner_id = ct.owner_id AND at.name = ctt.name
        ON CONFLICT DO NOTHING
    """)

    op.drop_index("idx_actress_profiles_tags_gin", table_name="actress_profiles")
    op.drop_column("actress_profiles", "tags")
    op.drop_index("idx_crawl_task_tag_links_tag_id", table_name="crawl_task_tag_links")
    op.drop_index("idx_crawl_task_tag_links_task_id", table_name="crawl_task_tag_links")
    op.drop_table("crawl_task_tag_links")
    op.drop_index(op.f("ix_crawl_task_tags_owner_id"), table_name="crawl_task_tags")
    op.drop_index("idx_crawl_task_tags_owner_name", table_name="crawl_task_tags")
    op.drop_table("crawl_task_tags")


def downgrade() -> None:
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
    op.add_column("actress_profiles", sa.Column("tags", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")))
    op.execute("""
        UPDATE actress_profiles ap
        SET tags = COALESCE(tag_rows.names, '{}'::text[])
        FROM (
            SELECT atl.actress_profile_id, array_agg(DISTINCT at.name ORDER BY at.name) AS names
            FROM actress_tag_links atl
            JOIN actress_tags at ON at.id = atl.tag_id
            GROUP BY atl.actress_profile_id
        ) AS tag_rows
        WHERE ap.id = tag_rows.actress_profile_id
    """)
    op.alter_column("actress_profiles", "tags", server_default=None)
    op.create_index("idx_actress_profiles_tags_gin", "actress_profiles", ["tags"], postgresql_using="gin")
    op.drop_index("idx_actress_tag_links_tag_id", table_name="actress_tag_links")
    op.drop_index("idx_actress_tag_links_profile_id", table_name="actress_tag_links")
    op.drop_table("actress_tag_links")
    op.drop_index(op.f("ix_actress_tags_owner_id"), table_name="actress_tags")
    op.drop_index("idx_actress_tags_owner_name", table_name="actress_tags")
    op.drop_table("actress_tags")
```

- [ ] **Step 5: Create SQL mirror**

Create `sql/20260910_normalize_actress_tags.sql` with the same upgrade SQL in Step 4, without Alembic Python wrappers. Include comments for the migration phases:

```sql
-- Create actress tag dictionary and links.
-- Copy existing actress_profiles.tags.
-- Copy matching task tags through actress_profiles.source_task_ids.
-- Drop old task tag tables and actress_profiles.tags.
```

- [ ] **Step 6: Run metadata tests and migration smoke check**

Run:

```bash
python -m pytest backend/tests/test_crawler_tasks_api.py::test_crawler_task_metadata_has_no_task_tag_tables backend/tests/test_content_actresses_api.py::test_actress_tag_metadata_contains_normalized_tables -v
```

Run an Alembic syntax check:

```bash
cd backend && alembic history
```

Expected: tests pass and Alembic loads the revision chain.

- [ ] **Step 7: Commit**

```bash
git add shared/database/models/content.py backend/app/models/crawl_task.py backend/alembic/versions/20260910_0002_normalize_actress_tags.py sql/20260910_normalize_actress_tags.sql backend/tests/test_crawler_tasks_api.py backend/tests/test_content_actresses_api.py
git commit -m "Normalize actress tag storage"
```

---

### Task 2: Actress Tag Service, API, Queries, And Serialization

**Files:**
- Create: `backend/app/modules/content/actresses/tag_service.py`
- Modify: `backend/app/modules/content/actresses/router.py`
- Modify: `backend/app/modules/content/actresses/queries.py`
- Modify: `backend/app/modules/content/actresses/serializers.py`
- Modify: `backend/app/modules/content/actresses/service.py`
- Modify: `backend/app/modules/content/actresses/schemas.py`
- Modify: `backend/tests/test_content_actresses_api.py`

**Interfaces:**
- Produces: `normalize_actress_tag_names(tag_names: list[str] | None) -> list[str]`.
- Produces: `list_actress_tags(db: Session, owner_id: uuid.UUID) -> list[ActressTag]`.
- Produces: `get_or_create_actress_tags(db: Session, owner_id: uuid.UUID, tag_names: list[str]) -> list[ActressTag]`.
- Produces: `replace_actress_tags(db: Session, profile: ActressProfile, owner_id: uuid.UUID, tag_names: list[str]) -> None`.
- Changes: `serialize_actress_profile(..., owner_id: uuid.UUID | None = None)` returns only owner-owned tag names.
- Changes: `list_actress_profiles(..., owner_id: uuid.UUID, tags: str | None)` filters through owner-owned normalized tags.

- [ ] **Step 1: Write failing actress API tests**

In `backend/tests/test_content_actresses_api.py`, update imports:

```python
from shared.database.models.content import ActressProfile, ActressTag, Movie
```

Replace array-style tag setup in `test_list_actresses_filters_by_tags` with helper-linked tags:

```python
def _link_actress_tags(db_session, owner_id, profile, names: list[str]) -> None:
    tags = []
    for name in names:
        tag = db_session.query(ActressTag).filter_by(owner_id=owner_id, name=name).first()
        if tag is None:
            tag = ActressTag(owner_id=owner_id, name=name)
            db_session.add(tag)
            db_session.flush()
        tags.append(tag)
    profile.tags = tags
```

Add tests:

```python
def test_list_actress_tags_returns_existing_user_tags(client, auth_headers, db_session, admin_user) -> None:
    db_session.add_all([
        ActressTag(owner_id=admin_user.id, name="企划"),
        ActressTag(owner_id=admin_user.id, name="清楚"),
    ])
    db_session.commit()

    response = client.get("/api/content/actresses/tags", headers=auth_headers)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["data"]] == ["企划", "清楚"]


def test_update_actress_tags_creates_dictionary_rows_and_links(client, auth_headers, db_session) -> None:
    profile = ActressProfile(
        display_name="Tag Editable",
        canonical_names=["Tag Editable"],
        source_url="https://db.avjoho.com/tag-editable/",
        image_url="https://example.test/tag-editable.jpg",
    )
    db_session.add(profile)
    db_session.commit()

    response = client.put(
        f"/api/content/actresses/{profile.id}/tags",
        json={"tags": ["新标签", "  新标签  ", "企划"]},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tags"] == ["企划", "新标签"]
    assert db_session.query(ActressTag).filter(ActressTag.name.in_(["新标签", "企划"])).count() == 2


def test_update_actress_tags_rejects_too_long_name(client, auth_headers, db_session) -> None:
    profile = ActressProfile(
        display_name="Tag Too Long",
        canonical_names=["Tag Too Long"],
        source_url="https://db.avjoho.com/tag-too-long/",
        image_url="https://example.test/tag-too-long.jpg",
    )
    db_session.add(profile)
    db_session.commit()

    response = client.put(
        f"/api/content/actresses/{profile.id}/tags",
        json={"tags": ["x" * 51]},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "标签长度不能超过 50 个字符" in response.json()["msg"]
```

Update fetch-from-task tag tests to expect no task-derived tags:

- `test_fetch_actress_from_actor_task_uses_javdb_aliases_to_match_avjoho`: expected profile tags `[]`.
- `test_fetch_existing_actress_only_merges_tags_and_source_links`: seed existing actress tags via `_link_actress_tags`, then assert unchanged `["旧标签"]`.
- `test_fetch_existing_actress_by_task_url_only_merges_tags_without_crawling`: assert message no longer says tag update; use `"女优资料已存在"` or the implemented message from Step 4.

- [ ] **Step 2: Run actress tests and verify failures**

Run:

```bash
python -m pytest backend/tests/test_content_actresses_api.py -v
```

Expected: failures from missing `ActressTag`, missing `/tags` route, array assumptions, and task-derived tag merging.

- [ ] **Step 3: Implement tag service**

Create `backend/app/modules/content/actresses/tag_service.py`:

```python
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import ActressProfile, ActressTag


def normalize_actress_tag_names(tag_names: list[str] | None) -> list[str]:
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


def list_actress_tags(db: Session, owner_id: uuid.UUID) -> list[ActressTag]:
    return list(db.scalars(
        select(ActressTag)
        .where(ActressTag.owner_id == owner_id)
        .order_by(ActressTag.name.asc())
    ))


def get_or_create_actress_tags(db: Session, owner_id: uuid.UUID, tag_names: list[str]) -> list[ActressTag]:
    normalized = normalize_actress_tag_names(tag_names)
    if not normalized:
        return []
    existing = list(db.scalars(
        select(ActressTag)
        .where(ActressTag.owner_id == owner_id, ActressTag.name.in_(normalized))
    ))
    by_name = {tag.name: tag for tag in existing}
    for name in normalized:
        if name not in by_name:
            tag = ActressTag(owner_id=owner_id, name=name)
            db.add(tag)
            db.flush()
            by_name[name] = tag
    return [by_name[name] for name in normalized]


def replace_actress_tags(db: Session, profile: ActressProfile, owner_id: uuid.UUID, tag_names: list[str]) -> None:
    new_tags = get_or_create_actress_tags(db, owner_id, tag_names)
    owner_tag_ids = {tag.id for tag in list_actress_tags(db, owner_id)}
    other_owner_tags = [tag for tag in profile.tags if tag.id not in owner_tag_ids]
    profile.tags = [*other_owner_tags, *new_tags]
```

- [ ] **Step 4: Update serializers and queries**

In `serializers.py`:

```python
def _profile_tag_names(profile: ActressProfile, owner_id: uuid.UUID | None) -> list[str]:
    tags = list(profile.tags or [])
    if owner_id is not None:
        tags = [tag for tag in tags if str(tag.owner_id) == str(owner_id)]
    return [tag.name for tag in sorted(tags, key=lambda item: item.name)]
```

Change `serialize_actress_profile` signature:

```python
def serialize_actress_profile(..., owner_id: uuid.UUID | None = None) -> dict:
```

Set:

```python
"tags": _profile_tag_names(profile, owner_id),
```

In `queries.py`, import `func` if needed and update `list_actress_profiles`:

```python
def list_actress_profiles(..., owner_id: uuid.UUID, tags: str | None = None) -> tuple[list[ActressProfile], int]:
```

Replace in-memory tag filtering with:

```python
expected_tags = set(_split_csv(tags))
if expected_tags:
    rows = [
        row for row in rows
        if expected_tags.issubset({tag.name for tag in (row.tags or []) if str(tag.owner_id) == str(owner_id)})
    ]
```

This keeps the current in-memory query style and avoids unrelated pagination refactors.

- [ ] **Step 5: Update actress router and service**

In `router.py`:

- Import `list_actress_tags`.
- Add route before `/{profile_id}`:

```python
@router.get("/tags")
def list_tags(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=[{"id": str(tag.id), "name": tag.name} for tag in list_actress_tags(db, current_user.id)])
```

- Pass `owner_id=current_user.id` to `list_actress_profiles`.
- Pass `owner_id=current_user.id` to every `serialize_actress_profile`.
- Change update call:

```python
return success(data=serialize_actress_profile(update_actress_tags(db, profile_id, current_user.id, body.tags), owner_id=current_user.id))
```

In `service.py`:

- Remove `_task_tag_names`, `_merge_existing_profile_tags`, and `tag_names` parameters.
- Import `replace_actress_tags`.
- Change `update_actress_tags` signature:

```python
def update_actress_tags(db: Session, profile_id: uuid.UUID, owner_id: uuid.UUID, tags: list[str]) -> ActressProfile:
```

- In it, call `replace_actress_tags(db, profile, owner_id, tags)`.
- In `fetch_actresses_from_task`, remove `selectinload(CrawlTask.tags)`.
- When existing profile by task URL is found, only ensure source links exist and return message `"女优资料已存在"`.
- In `_upsert_profile`, do not merge task tags.
- When serializing profiles from fetch, call `serialize_actress_profile(profile, owner_id=task.owner_id)` if the task owner is available.

- [ ] **Step 6: Run actress API tests**

Run:

```bash
python -m pytest backend/tests/test_content_actresses_api.py -v
```

Expected: all actress tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/content/actresses/tag_service.py backend/app/modules/content/actresses/router.py backend/app/modules/content/actresses/queries.py backend/app/modules/content/actresses/serializers.py backend/app/modules/content/actresses/service.py backend/app/modules/content/actresses/schemas.py backend/tests/test_content_actresses_api.py
git commit -m "Move tags to actress profiles"
```

---

### Task 3: Remove Task Tag Backend Behavior

**Files:**
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/router.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/serializers.py`
- Modify: `backend/tests/test_crawler_tasks_api.py`

**Interfaces:**
- Removes: `tag_names` from task list/create/update/batch create.
- Removes: `GET /api/crawler/tasks/tags`.
- Removes: task response `tags`.
- Keeps: task create/edit/list/run behavior unrelated to tags.

- [ ] **Step 1: Write failing task API tests**

In `backend/tests/test_crawler_tasks_api.py`:

- Update `test_crawler_task_list_returns_total_and_static_list_fields`:

```python
assert set(data["rows"][0]) == {"id", "name", "storage_location", "is_skip", "urls"}
assert "tags" not in data["rows"][0]
```

- Add:

```python
def test_task_tags_route_removed(client, auth_headers):
    response = client.get("/api/crawler/tasks/tags", headers=auth_headers)
    assert response.status_code == 404


def test_task_create_ignores_removed_tag_names_field(client, auth_headers):
    response = client.post(
        "/api/crawler/tasks",
        json={
            "name": "no-tag-task",
            "storage_location": "no-tag-task",
            "is_skip": False,
            "tag_names": ["旧字段"],
            "urls": [{"url": "https://javdb.com/actors/no-tag", "url_type": "actors"}],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert "tags" not in response.json()["data"]
```

If project Pydantic config rejects extra fields, change the expected status to 422 and document that removed fields are rejected. Prefer ignoring extra fields if current schemas already do so.

- [ ] **Step 2: Run focused task tests and verify failures**

Run:

```bash
python -m pytest backend/tests/test_crawler_tasks_api.py -v
```

Expected: failures from old `tags` response and existing `/tags` route.

- [ ] **Step 3: Update schemas**

In `backend/app/schemas/crawl_task.py`:

- Remove `tag_names` from `CrawlTaskCreate`.
- Remove `tag_names` from `CrawlTaskBatchCreate`.
- Remove `tag_names` from `CrawlTaskUpdate`.
- Delete `TaskTagRead`.
- Remove `tags` from `CrawlTaskRead`.
- Remove `tags` from `CrawlTaskListItem`.

- [ ] **Step 4: Update repository**

In `backend/app/repositories/crawl_task.py`:

- Remove `CrawlTaskTag` import.
- Remove `.options(selectinload(CrawlTask.tags))`.
- Remove `tag_names` parameters from `_owner_query`, `get_by_owner`, and `count_by_owner`.
- Delete `_apply_tag_filter`.
- Delete `get_tags_by_owner`, `get_or_create_tags`, and `replace_task_tags`.

- [ ] **Step 5: Update service and router**

In `backend/app/modules/crawler/tasks/router.py`:

- Remove `tag_names` query parameter from `list_tasks`.
- Delete `@router.get("/tags")`.

In `backend/app/modules/crawler/tasks/service.py`:

- Delete `normalize_tag_names`.
- Delete `list_task_tags`.
- Delete `_tags_for_names`.
- Remove validation blocks for `data.tag_names`.
- Remove `repo.replace_task_tags(...)` calls.
- Remove `tag_names` from `list_tasks` and repository calls.
- Change `data.model_dump(exclude_unset=True, exclude={"urls", "tag_names"})` to `exclude={"urls"}`.

In `backend/app/modules/crawler/tasks/serializers.py`:

- Remove `TaskTagRead` import.
- Remove `tags=[...]` from serialized task objects.

- [ ] **Step 6: Run backend task tests**

Run:

```bash
python -m pytest backend/tests/test_crawler_tasks_api.py -v
```

Expected: task API tests pass with no tag behavior.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/app/modules/crawler/tasks/service.py backend/app/repositories/crawl_task.py backend/app/modules/crawler/tasks/serializers.py backend/tests/test_crawler_tasks_api.py
git commit -m "Remove crawler task tags"
```

---

### Task 4: Backup And Restore Actress Tags

**Files:**
- Modify: `backend/app/modules/backup/exporters.py`
- Modify: `backend/app/modules/backup/restorers.py`
- Modify: backup tests under `backend/tests/` after locating exact filenames with `rg "backup" backend/tests -n`

**Interfaces:**
- Produces: backup entries `data/actress_tags.jsonl` and `data/actress_tag_links.jsonl`.
- Removes: backup entries `data/crawl_task_tags.jsonl` and `data/crawl_task_tag_links.jsonl`.
- Restore ignores old task tag archive files.

- [ ] **Step 1: Locate backup tests**

Run:

```bash
rg "backup|crawl_task_tags|crawl_task_tag_links|jsonl" backend/tests -n
```

Use the matching backup test file names in the next steps.

- [ ] **Step 2: Write failing backup tests**

In the backup export test file, seed an `ActressTag` linked to an `ActressProfile` and assert archive names include:

```python
assert "data/actress_tags.jsonl" in archive_names
assert "data/actress_tag_links.jsonl" in archive_names
assert "data/crawl_task_tags.jsonl" not in archive_names
assert "data/crawl_task_tag_links.jsonl" not in archive_names
```

In the restore test file, add an archive fixture that includes old task tag files and assert restore still succeeds while no task tag table is referenced. The test should assert restored actress tags from `data/actress_tags.jsonl` and `data/actress_tag_links.jsonl`.

- [ ] **Step 3: Run backup tests and verify failures**

Run:

```bash
python -m pytest backend/tests/test_backup_export_restore.py -v
```

Expected: failures from old export specs and missing restore handlers.

- [ ] **Step 4: Update exporters**

In `backend/app/modules/backup/exporters.py`:

- Remove imports of `CrawlTaskTag` and `crawl_task_tag_links`.
- Import `ActressProfile`, `ActressTag`, `actress_tag_links`, `Movie`, `MovieFilter`, `MovieMagnet`.
- Add an actress/content export spec, or extend the existing content exports:

```python
ACTRESS_EXPORTS = (
    (
        ActressTag,
        "data/actress_tags.jsonl",
        lambda stmt, owner_id: stmt.where(ActressTag.owner_id == owner_id),
    ),
    (
        actress_tag_links,
        "data/actress_tag_links.jsonl",
        lambda stmt, owner_id: stmt.where(
            actress_tag_links.c.tag_id.in_(
                select(ActressTag.id).where(ActressTag.owner_id == owner_id)
            )
        ),
    ),
)
```

- Include `ACTRESS_EXPORTS` in `_scope_entity_rows`, counts, and the database export group used by backup creation.
- Remove task tag specs from `TASK_EXPORTS`.

- [ ] **Step 5: Update restorers**

In `backend/app/modules/backup/restorers.py`:

- Remove imports of `CrawlTaskTag` and `crawl_task_tag_links`.
- Import `ActressTag`, `ActressProfile`, and `actress_tag_links`.
- Remove `_restore_task_tags` and `_restore_task_tag_links` calls from task restore.
- Remove task-tag deletion from `_clear_tasks_group`.
- Add `_restore_actress_tags(...) -> dict[uuid.UUID, uuid.UUID]`.
- Add `_restore_actress_tag_links(...) -> None`.
- Ensure overwrite mode deletes current user's actress tag links through owned tag ids, then deletes their `ActressTag` rows.
- In restore code, ignore archive names `data/crawl_task_tags.jsonl` and `data/crawl_task_tag_links.jsonl` by not reading them.

Use this link existence check:

```python
link_exists = db.scalar(
    select(actress_tag_links.c.actress_profile_id).where(
        actress_tag_links.c.actress_profile_id == resolved_profile_id,
        actress_tag_links.c.tag_id == resolved_tag_id,
    )
)
```

- [ ] **Step 6: Run backup tests**

Run:

```bash
python -m pytest backend/tests/test_backup_export_restore.py -v
```

Expected: backup tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/backup/exporters.py backend/app/modules/backup/restorers.py backend/tests/test_backup_export_restore.py
git commit -m "Back up actress tags"
```

---

### Task 5: Frontend Remove Task Tags And Add Actress Tag Options

**Files:**
- Modify: `frontend/src/api/crawler/crawlTask/index.ts`
- Modify: `frontend/src/api/crawler/crawlTask/types.ts`
- Modify: `frontend/src/api/content/actresses/index.ts`
- Modify: `frontend/src/api/content/actresses/types.ts`
- Modify: `frontend/src/api/queryKeys.ts`
- Delete: `frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
- Modify: `frontend/src/pages/content/actresses/ActressListPage.tsx`
- Modify: `frontend/src/pages/content/actresses/ActressDetailPage.tsx`
- Modify: affected frontend tests under `frontend/src/pages/crawler/tasks/__tests__`, `frontend/tests`, and `frontend/src/pages/content/actresses/__tests__`.

**Interfaces:**
- Produces: `getActressTags(): Promise<ActressTag[]>`.
- Produces: `ActressTag { id: string; name: string }`.
- Removes: `getCrawlTaskTags`, `TaskTag`, `tag_names`, task list tag filter, task tag selector UI.

- [ ] **Step 1: Write failing frontend tests**

Update actress page tests to mock `getActressTags`:

```ts
vi.mock('@/api/content/actresses', () => ({
  fetchActress: vi.fn(),
  fetchActresses: vi.fn(),
  getActressTags: vi.fn(),
  updateActressTags: vi.fn(),
}))
```

In `beforeEach`:

```ts
vi.mocked(getActressTags).mockResolvedValue([
  { id: 'tag-1', name: '清楚' },
  { id: 'tag-2', name: '企划' },
])
```

Add detail editor assertion:

```ts
it('offers existing actress tags in the detail tag editor', async () => {
  const user = userEvent.setup()
  vi.mocked(fetchActress).mockResolvedValue({ ...profile, recent_movies: [] })

  renderWithClient(<ActressDetailPage />)

  await user.click(await screen.findByRole('button', { name: '编辑标签' }))
  await user.click(screen.getByLabelText('编辑标签'))
  expect(await screen.findByText('企划')).toBeInTheDocument()
})
```

Update task form/list tests:

- Remove mocks for `getCrawlTaskTags`.
- Assert `screen.queryByLabelText('任务标签')` is not present in task form and batch drawer.
- Assert task list toolbar has no tag filter select.

- [ ] **Step 2: Run focused frontend tests and verify failures**

Run:

```bash
cd frontend && pnpm exec vitest run src/pages/content/actresses/__tests__/actress-pages.test.tsx src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: failures from missing `getActressTags` and old task tag UI/API.

- [ ] **Step 3: Update frontend API and query keys**

In `frontend/src/api/content/actresses/types.ts`:

```ts
export interface ActressTag {
  id: string
  name: string
}
```

In `frontend/src/api/content/actresses/index.ts`:

```ts
export type { ActressTag } from './types'

export function getActressTags(): Promise<ActressTag[]> {
  return request.get<ActressTag[]>(`${BASE_URL}/tags`)
}
```

In `frontend/src/api/queryKeys.ts`:

- Remove `crawlerTasks.tags`.
- Add:

```ts
tags: () => ['actresses', 'tags'] as const,
```

inside `actresses`.

In crawler task API/types:

- Remove `getCrawlTaskTags`.
- Delete `TaskTag`.
- Remove `tag_names` from create/update/batch payload types.
- Remove `tags` from `CrawlTask` and `CrawlTaskListItem`.
- Remove `tag_names` from `getCrawlTasks` params.

- [ ] **Step 4: Remove task tag UI**

Delete `frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx`.

In `TaskListPage.tsx`:

- Remove `getCrawlTaskTags` import and query.
- Remove `useSessionListState` for selected tag names.
- Remove `handleTagFilterChange`.
- Call `useTaskListData()` with no tagNames.
- Remove `tagOptions`, `selectedTagNames`, and `onTagFilterChange` props.
- Remove `tagOptions` props from `BatchTaskCreateDrawer`.

In `useTaskListData.tsx`:

- Remove `tagNames` argument and tag key from `searchKey`.
- Remove `tag_names` from list params.

In `TaskListCards.tsx`:

- Remove `TaskTag` type.
- Remove props `tagOptions`, `selectedTagNames`, `onTagFilterChange`.
- Delete `TaskTagTags`.
- Remove toolbar tag `Select`.
- Remove task card tag display row.

In `TaskFormPage.tsx`:

- Remove `getCrawlTaskTags`, `TaskTagSelect`, and tag query.
- Remove `tag_names` from loaded form values, initial values, and submit payload.
- Remove `<Form.Item name="tag_names" label="任务标签">`.

In `BatchTaskCreateDrawer.tsx`:

- Remove `TaskTag` and `TaskTagSelect`.
- Remove `tagOptions` and `tagOptionsLoading` props.
- Remove `tag_names` from form type, initial values, `setFieldsValue`, and submit payload.
- Remove `<Form.Item name="tag_names" label="任务标签">`.

- [ ] **Step 5: Add actress tag options**

In `ActressListPage.tsx`:

- Import `getActressTags`.
- Add:

```ts
const tagOptionsQuery = useQuery({
  queryKey: queryKeys.actresses.tags(),
  queryFn: getActressTags,
})
```

- On tag filter `Select`, add:

```tsx
loading={tagOptionsQuery.isLoading}
options={(tagOptionsQuery.data ?? []).map((tag) => ({ value: tag.name, label: tag.name }))}
```

In `ActressDetailPage.tsx`:

- Import `getActressTags`.
- Add the same query.
- In tag editor Select, add loading/options.
- After successful save, add:

```ts
queryClient.invalidateQueries({ queryKey: queryKeys.actresses.tags() })
```

- [ ] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend && pnpm exec vitest run src/pages/content/actresses/__tests__/actress-pages.test.tsx src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: focused frontend tests pass.

- [ ] **Step 7: Build frontend**

Run:

```bash
cd frontend && pnpm build
```

Expected: TypeScript and Vite build pass. Existing chunk-size warnings are acceptable.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/crawler/crawlTask/index.ts frontend/src/api/crawler/crawlTask/types.ts frontend/src/api/content/actresses/index.ts frontend/src/api/content/actresses/types.ts frontend/src/api/queryKeys.ts frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx frontend/src/pages/content/actresses/ActressListPage.tsx frontend/src/pages/content/actresses/ActressDetailPage.tsx frontend/src/pages/content/actresses/__tests__/actress-pages.test.tsx frontend/src/pages/crawler/tasks/__tests__ frontend/tests
git add -u frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx
git commit -m "Update frontend for actress-only tags"
```

---

### Task 6: Full Verification And Local Alembic Upgrade

**Files:**
- Modify only if verification finds issues in files touched by Tasks 1-5.

**Interfaces:**
- Produces: locally upgraded database using current data-folder config.
- Produces: final confidence that task tags are removed and actress tags work.

- [ ] **Step 1: Search for stale task tag references**

Run:

```bash
rg "crawl_task_tags|crawl_task_tag_links|CrawlTaskTag|TaskTag|tag_names|任务标签|getCrawlTaskTags|crawlerTasks\\.tags" backend shared frontend docs -n
```

Expected: only historical design/plan docs may contain old task tag strings. No source code or active tests should reference removed task tag code.

- [ ] **Step 2: Run backend focused tests**

Run:

```bash
python -m pytest backend/tests/test_content_actresses_api.py backend/tests/test_crawler_tasks_api.py -v
```

Expected: pass.

- [ ] **Step 3: Run scraper regression tests if task changes touched crawler run behavior**

Run:

```bash
python -m pytest scraper/tests -v
```

Expected: pass. If failures are from the unrelated unstaged `scraper/spiders/javdb/javdb_spider.py` change, document them and do not revert that file.

- [ ] **Step 4: Run frontend tests and build**

Run:

```bash
cd frontend && pnpm exec vitest run src/pages/content/actresses/__tests__/actress-pages.test.tsx src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
cd frontend && pnpm build
```

Expected: tests and build pass.

- [ ] **Step 5: Run Alembic upgrade locally**

Use the current repository runtime configuration, consistent with prior local migrations:

```bash
cd backend && alembic upgrade head
```

Expected: migration applies and current DB reaches head.

- [ ] **Step 6: Inspect git status**

Run:

```bash
git status --short
```

Expected: no unstaged files from this feature. The unrelated `scraper/spiders/javdb/javdb_spider.py` change may still be present and must remain uncommitted unless the user separately asks to include it.

- [ ] **Step 7: Final commit if verification fixes were needed**

If Step 1-5 required code/test fixes:

```bash
git add shared/database/models/content.py backend/app/models/crawl_task.py backend/alembic/versions/20260910_0002_normalize_actress_tags.py sql/20260910_normalize_actress_tags.sql backend/app/modules/content/actresses/tag_service.py backend/app/modules/content/actresses/router.py backend/app/modules/content/actresses/queries.py backend/app/modules/content/actresses/serializers.py backend/app/modules/content/actresses/service.py backend/app/modules/content/actresses/schemas.py backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/router.py backend/app/modules/crawler/tasks/service.py backend/app/repositories/crawl_task.py backend/app/modules/crawler/tasks/serializers.py backend/app/modules/backup/exporters.py backend/app/modules/backup/restorers.py backend/tests/test_content_actresses_api.py backend/tests/test_crawler_tasks_api.py backend/tests/test_backup_export_restore.py frontend/src/api/crawler/crawlTask/index.ts frontend/src/api/crawler/crawlTask/types.ts frontend/src/api/content/actresses/index.ts frontend/src/api/content/actresses/types.ts frontend/src/api/queryKeys.ts frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/TaskFormPage.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/components/BatchTaskCreateDrawer.tsx frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx frontend/src/pages/content/actresses/ActressListPage.tsx frontend/src/pages/content/actresses/ActressDetailPage.tsx frontend/src/pages/content/actresses/__tests__/actress-pages.test.tsx frontend/src/pages/crawler/tasks/__tests__/task-url-drawer.test.tsx frontend/src/pages/crawler/tasks/__tests__/batch-task-create-drawer.test.tsx frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx frontend/tests/task-list-query-state.ui.test.tsx frontend/tests/movie-task-jump.ui.test.tsx frontend/tests/crawler-run-controls.ui.test.tsx frontend/tests/task-form-restore.ui.test.tsx
git add -u frontend/src/pages/crawler/tasks/components/TaskTagSelect.tsx
git commit -m "Verify actress-only tags migration"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review

- Spec coverage: The plan covers normalized actress tag tables, migration from old actress array tags and matching task tags, removal of task tag API/UI/backend/backup, actress tag dictionary endpoint, frontend tag options, tests, SQL, and local Alembic upgrade.
- Placeholder scan: No task contains open-ended “TODO” placeholders; backup tests use the repository's existing `backend/tests/test_backup_export_restore.py`.
- Type consistency: The plan consistently uses `ActressTag`, `actress_tag_links`, `getActressTags`, `queryKeys.actresses.tags()`, and removes `TaskTag`, `tag_names`, `CrawlTaskTag`, and `crawl_task_tag_links`.
