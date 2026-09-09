# Actress Profile Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one-click actress profile fetching from JavDB actor tasks through avjoho, plus card-based actress list and standalone detail pages with recent local movies.

**Architecture:** Add an `ActressProfile` content model and content/actresses backend module beside content/movies. Keep parsing isolated in small parser modules, keep fetching/upsert orchestration in a service, and expose typed frontend APIs consumed by new card-list/detail pages and the existing crawler task list action.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, Scrapling parser adaptors, React 19, Vite, TypeScript, Ant Design, TanStack Router, TanStack Query, Vitest, React Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-09-actress-profile-content-design.md`

## Global Constraints

- Do not create or use a Git worktree for this repository; work in the current checkout.
- Stage intended source files explicitly instead of using `git add .` or `git add -A`.
- Create commits grouped by functional change.
- First version supports only JavDB actor task URLs and avjoho profile pages.
- The task-card action is available only when a task has at least one `actors` task URL.
- Automatic matching uses JavDB primary names, JavDB aliases, task URL `url_name`, and task name.
- Manual avjoho URLs must be HTTP(S) URLs on `db.avjoho.com`.
- Actress list uses cards, not a table.
- Actress list page sizes must be multiples of 8: default `24`, options `8`, `16`, `24`, `40`.
- Actress detail is a standalone route at `/content/actresses/$id`, not a drawer.
- Detail `最近影片` shows 10 local movies matched through associated `source_task_ids` and `source_task_url_ids`, sorted by `release_date` descending with missing dates last; do not match recent movies by actress names.
- Store remote image URLs; do not add storage integration for actress images.

---

## File Structure

Backend/shared files:

- Modify `shared/database/models/content.py`: add `ActressProfile`.
- Create `sql/20260909_add_actress_profiles.sql`: create `actress_profiles` and its indexes.
- Create `backend/alembic/versions/20260909_0001_add_actress_profiles.py`: matching Alembic migration for `actress_profiles`.
- Modify `backend/tests/test_content_models_metadata.py`: assert the table is registered.
- Modify `scraper/spiders/javdb/javdb_parser.py`: add actor metadata parser while keeping `parse_page_section_name` stable.
- Modify or create `scraper/tests/test_javdb_actor_metadata.py`: parser tests for JavDB actor names and aliases.
- Create `backend/app/modules/content/actresses/avjoho_parser.py`: parse avjoho HTML into a normalized payload.
- Create `backend/tests/test_avjoho_parser.py`: parser tests using the pasted sample structure.
- Create `backend/app/modules/content/actresses/schemas.py`: request/response Pydantic schemas.
- Create `backend/app/modules/content/actresses/serializers.py`: model-to-dict helpers.
- Create `backend/app/modules/content/actresses/queries.py`: list/search/get/recent movies-by-task queries.
- Create `backend/app/modules/content/actresses/service.py`: fetch-from-task, candidate matching, validation, upsert.
- Create `backend/app/modules/content/actresses/router.py`: content actress endpoints.
- Modify `backend/app/main.py`: include actress router.
- Create `backend/tests/test_content_actresses_api.py`: API and service integration coverage.

Frontend files:

- Create `frontend/src/api/content/actresses/types.ts`: actress and fetch result types.
- Create `frontend/src/api/content/actresses/index.ts`: API wrappers.
- Modify `frontend/src/api/queryKeys.ts`: add actress query keys.
- Create `frontend/src/pages/content/actresses/ActressListPage.tsx`: card list page.
- Create `frontend/src/pages/content/actresses/ActressDetailPage.tsx`: standalone detail page.
- Create `frontend/src/pages/content/actresses/ActressPages.module.less`: list/detail styles.
- Create `frontend/src/pages/content/actresses/__tests__/actress-pages.test.tsx`: list/detail route-level tests.
- Modify `frontend/src/routes/index.tsx`: register list/detail routes.
- Modify `frontend/src/routes/tags.ts`: add route tag metadata.
- Modify `frontend/src/layout/Sidebar/index.tsx`: add sidebar item and selection handling.
- Modify `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`: add fetch action for actor tasks.
- Modify `frontend/src/pages/crawler/tasks/TaskListPage.tsx`: call fetch API, handle manual URL modal, invalidate actress queries.
- Modify `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`: action visibility and click tests.

---

### Task 1: Actress Profile Model and SQL Table Script

**Files:**
- Modify: `shared/database/models/content.py`
- Create: `sql/20260909_add_actress_profiles.sql`
- Create: `backend/alembic/versions/20260909_0001_add_actress_profiles.py`
- Modify: `backend/tests/test_content_models_metadata.py`

**Interfaces:**
- Produces: SQLAlchemy model `ActressProfile`.
- Produces: SQL script and Alembic migration for table `actress_profiles` with stable column names consumed by later backend tasks.

- [ ] **Step 1: Write the failing model metadata test**

Add `actress_profiles` to the expected table set in `backend/tests/test_content_models_metadata.py`:

```python
def test_crawler_run_and_content_tables_registered() -> None:
    expected = {
        "crawl_runs",
        "crawl_run_detail_tasks",
        "movies",
        "movie_magnets",
        "movie_filters",
        "actress_profiles",
    }
    assert expected.issubset(set(Base.metadata.tables))
```

- [ ] **Step 2: Run the metadata test to verify it fails**

Run: `python -m pytest backend/tests/test_content_models_metadata.py -v`

Expected: FAIL because `actress_profiles` is missing from `Base.metadata.tables`.

- [ ] **Step 3: Add the SQLAlchemy model**

In `shared/database/models/content.py`, import `DateTime` and add this model after `MovieFilter`:

```python
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, Uuid
```

```python
class ActressProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "actress_profiles"
    __table_args__ = (
        Index("idx_actress_profiles_display_name", "display_name"),
        Index("idx_actress_profiles_source_url", "source_url"),
        Index("idx_actress_profiles_source_task_ids_gin", "source_task_ids", postgresql_using="gin"),
        Index("idx_actress_profiles_aliases_gin", "aliases", postgresql_using="gin"),
        Index("idx_actress_profiles_canonical_names_gin", "canonical_names", postgresql_using="gin"),
        UniqueConstraint("source_url", name="uq_actress_profiles_source_url"),
    )

    display_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reading: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aliases: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    canonical_names: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_site: Mapped[str] = mapped_column(Text, nullable=False, default="avjoho")
    source_task_ids: Mapped[list[uuid.UUID]] = mapped_column(CompatibleARRAY(Uuid), nullable=False, default=list)
    source_task_url_ids: Mapped[list[uuid.UUID]] = mapped_column(CompatibleARRAY(Uuid), nullable=False, default=list)
    image_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    debut_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bust_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waist_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hip_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cup: Mapped[str] = mapped_column(Text, nullable=False, default="")
    birthplace: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blood_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hobbies: Mapped[str] = mapped_column(Text, nullable=False, default="")
    biography: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exclusive_maker: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sns_links: Mapped[list[dict]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    representative_works: Mapped[list[dict]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    similar_actresses: Mapped[list[dict]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    raw_profile: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Also import `datetime`:

```python
from datetime import date, datetime
```

- [ ] **Step 4: Add the SQL table script**

Create `sql/20260909_add_actress_profiles.sql`:

```sql
CREATE TABLE actress_profiles (
    id UUID NOT NULL,
    display_name TEXT NOT NULL,
    reading TEXT NOT NULL,
    aliases TEXT[] NOT NULL,
    canonical_names TEXT[] NOT NULL,
    source_url TEXT NOT NULL,
    source_site TEXT NOT NULL,
    source_task_ids UUID[] NOT NULL,
    source_task_url_ids UUID[] NOT NULL,
    image_url TEXT NOT NULL,
    debut_date DATE,
    birth_date DATE,
    height_cm INTEGER,
    bust_cm INTEGER,
    waist_cm INTEGER,
    hip_cm INTEGER,
    cup TEXT NOT NULL,
    birthplace TEXT NOT NULL,
    blood_type TEXT NOT NULL,
    hobbies TEXT NOT NULL,
    biography TEXT NOT NULL,
    exclusive_maker TEXT NOT NULL,
    sns_links JSONB NOT NULL,
    representative_works JSONB NOT NULL,
    similar_actresses JSONB NOT NULL,
    raw_profile JSONB NOT NULL,
    last_fetched_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_actress_profiles_source_url UNIQUE (source_url)
);

CREATE INDEX idx_actress_profiles_display_name
    ON actress_profiles (display_name);

CREATE INDEX idx_actress_profiles_source_url
    ON actress_profiles (source_url);

CREATE INDEX idx_actress_profiles_source_task_ids_gin
    ON actress_profiles USING gin (source_task_ids);

CREATE INDEX idx_actress_profiles_aliases_gin
    ON actress_profiles USING gin (aliases);

CREATE INDEX idx_actress_profiles_canonical_names_gin
    ON actress_profiles USING gin (canonical_names);
```

- [ ] **Step 5: Run the metadata test**

- [ ] **Step 5: Add the matching Alembic migration**

Create `backend/alembic/versions/20260909_0001_add_actress_profiles.py`:

```python
"""add actress profiles

Revision ID: 20260909_0001
Revises: 20260904_0003
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260909_0001"
down_revision = "20260904_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actress_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("reading", sa.Text(), nullable=False),
        sa.Column("aliases", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("canonical_names", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_site", sa.Text(), nullable=False),
        sa.Column("source_task_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("source_task_url_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("debut_date", sa.Date(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("bust_cm", sa.Integer(), nullable=True),
        sa.Column("waist_cm", sa.Integer(), nullable=True),
        sa.Column("hip_cm", sa.Integer(), nullable=True),
        sa.Column("cup", sa.Text(), nullable=False),
        sa.Column("birthplace", sa.Text(), nullable=False),
        sa.Column("blood_type", sa.Text(), nullable=False),
        sa.Column("hobbies", sa.Text(), nullable=False),
        sa.Column("biography", sa.Text(), nullable=False),
        sa.Column("exclusive_maker", sa.Text(), nullable=False),
        sa.Column("sns_links", sa.JSON(), nullable=False),
        sa.Column("representative_works", sa.JSON(), nullable=False),
        sa.Column("similar_actresses", sa.JSON(), nullable=False),
        sa.Column("raw_profile", sa.JSON(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url", name="uq_actress_profiles_source_url"),
    )
    op.create_index("idx_actress_profiles_display_name", "actress_profiles", ["display_name"])
    op.create_index("idx_actress_profiles_source_url", "actress_profiles", ["source_url"])
    op.create_index("idx_actress_profiles_source_task_ids_gin", "actress_profiles", ["source_task_ids"], postgresql_using="gin")
    op.create_index("idx_actress_profiles_aliases_gin", "actress_profiles", ["aliases"], postgresql_using="gin")
    op.create_index("idx_actress_profiles_canonical_names_gin", "actress_profiles", ["canonical_names"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("idx_actress_profiles_canonical_names_gin", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_aliases_gin", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_source_task_ids_gin", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_source_url", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_display_name", table_name="actress_profiles")
    op.drop_table("actress_profiles")
```

- [ ] **Step 6: Run the metadata test**

Run: `python -m pytest backend/tests/test_content_models_metadata.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/database/models/content.py sql/20260909_add_actress_profiles.sql backend/alembic/versions/20260909_0001_add_actress_profiles.py backend/tests/test_content_models_metadata.py
git diff --cached --name-only
git commit -m "Add actress profile model"
```

---

### Task 2: JavDB Actor Metadata Parser

**Files:**
- Modify: `scraper/spiders/javdb/javdb_parser.py`
- Create: `scraper/tests/test_javdb_actor_metadata.py`

**Interfaces:**
- Produces: `parse_actor_section_metadata(page) -> dict[str, list[str]]`.
- Produces payload: `{"primary_names": list[str], "aliases": list[str]}`.
- Consumed by Task 4 service candidate extraction.

- [ ] **Step 1: Write failing parser tests**

Create `scraper/tests/test_javdb_actor_metadata.py`:

```python
from scrapling.parser import Adaptor

from scraper.spiders.javdb.javdb_parser import parse_actor_section_metadata


def page(html: str) -> Adaptor:
    return Adaptor(html)


def test_parse_actor_section_metadata_extracts_alias() -> None:
    parsed = parse_actor_section_metadata(page("""
    <div class="column section-title">
      <h2 class="title is-4 has-text-justified">
        <span class="actor-section-name">咲乃柑菜</span>
        <br>
        <span class="section-meta">蘭華</span>
        <br>
        <span class="section-meta">339 部影片</span>
      </h2>
    </div>
    """))

    assert parsed == {"primary_names": ["咲乃柑菜"], "aliases": ["蘭華"]}


def test_parse_actor_section_metadata_splits_primary_names_and_aliases() -> None:
    parsed = parse_actor_section_metadata(page("""
    <div class="column section-title">
      <h2 class="title is-4 has-text-justified">
        <span class="actor-section-name">蓮實克蕾兒, 蓮実クレア</span>
        <br>
        <span class="section-meta">安達亜美, 新田絢, 蓮見クレア, 神楽坂唯, 蓮美クレア, 莲実クレア</span>
        <br>
        <span class="section-meta">1928 部影片</span>
      </h2>
    </div>
    """))

    assert parsed["primary_names"] == ["蓮實克蕾兒", "蓮実クレア"]
    assert parsed["aliases"] == ["安達亜美", "新田絢", "蓮見クレア", "神楽坂唯", "蓮美クレア", "莲実クレア"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest scraper/tests/test_javdb_actor_metadata.py -v`

Expected: FAIL because `parse_actor_section_metadata` does not exist.

- [ ] **Step 3: Implement metadata parsing**

Add helpers near `parse_page_section_name` in `scraper/spiders/javdb/javdb_parser.py`:

```python
MOVIE_COUNT_RE = re.compile(r"^\d+\s*部影片$")


def _split_comma_names(value: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        name = clean_text(part)
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def parse_actor_section_metadata(page) -> dict[str, list[str]]:
    primary_names: list[str] = []
    aliases: list[str] = []
    seen_primary: set[str] = set()
    seen_aliases: set[str] = set()

    for raw in _all_text(page, ".actor-section-name::text"):
        for name in _split_comma_names(raw):
            if name not in seen_primary:
                seen_primary.add(name)
                primary_names.append(name)

    for raw in _all_text(page, ".section-title .section-meta::text"):
        if MOVIE_COUNT_RE.match(raw):
            continue
        for name in _split_comma_names(raw):
            if name not in seen_aliases and name not in seen_primary:
                seen_aliases.add(name)
                aliases.append(name)

    return {"primary_names": primary_names, "aliases": aliases}
```

- [ ] **Step 4: Run parser tests**

Run: `python -m pytest scraper/tests/test_javdb_actor_metadata.py scraper/tests/test_javdb_parser_detail_title.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scraper/spiders/javdb/javdb_parser.py scraper/tests/test_javdb_actor_metadata.py
git diff --cached --name-only
git commit -m "Parse JavDB actor aliases"
```

---

### Task 3: Avjoho Profile Parser

**Files:**
- Create: `backend/app/modules/content/actresses/__init__.py`
- Create: `backend/app/modules/content/actresses/avjoho_parser.py`
- Create: `backend/tests/test_avjoho_parser.py`

**Interfaces:**
- Produces dataclass `AvjohoProfilePayload`.
- Produces function `parse_avjoho_profile(html: str, source_url: str) -> AvjohoProfilePayload | None`.
- Consumed by Task 4 service upsert.

- [ ] **Step 1: Write failing avjoho parser tests**

Create `backend/tests/test_avjoho_parser.py` using a compact sample based on the pasted HTML:

```python
from backend.app.modules.content.actresses.avjoho_parser import parse_avjoho_profile


SAMPLE = """
<div id="main">
  <h1 class="entry-title">宮上唯依花（みやうえゆいか）</h1>
  <div id="the-content" class="entry-content">
    <div class="database">
      <div class="gazou"><a href="https://example.test/work"><img src="https://pics.dmm.co.jp/digital/video/1dldss00528/1dldss00528ps.jpg" alt="宮上唯依花"></a></div>
      <div class="profile"><table><tbody>
        <tr><th>デビュー</th><td>2026年9月3日</td></tr>
        <tr><th>生年月日</th><td>1977年12月1日</td></tr>
        <tr><th>身長</th><td>163cm</td></tr>
        <tr><th>スリーサイズ</th><td>B90cm W62cm H93cm</td></tr>
        <tr><th>カップ</th><td>E</td></tr>
      </tbody></table></div>
      <div class="birthplace"><table><tbody><tr><th>出身地</th><td>京都府</td></tr></tbody></table></div>
      <div class="blood-type"><table><tbody><tr><th>血液型</th><td>A型</td></tr></tbody></table></div>
      <div class="shumi-tokugi"><table><tbody><tr><th>趣味・特技</th><td>神社・美術館巡り<br>ヨガ</td></tr></tbody></table></div>
      <div class="profile2">2026年にDAHLIAから48歳としてデビュー。</div>
      <div class="name"><table><tbody><tr><th>別名</th><td>–</td></tr></tbody></table></div>
      <div class="maker"><table><tbody><tr><th>専属メーカー</th><td>DAHLIA ※デビュー</td></tr></tbody></table></div>
      <div class="sns"><table><tbody><tr><th>X（旧Twitter）</th><td><a href="https://x.com/MiyaueYuika">@MiyaueYuika</a></td></tr></tbody></table></div>
      <h2>主な出演作品</h2>
      <p><span class="gazou-large"><a href="https://example.test/work"><img src="https://pics.dmm.co.jp/digital/video/1dldss00528/1dldss00528pl.jpg" alt="作品画像"></a></span><br>
      <span class="text-link"><a href="https://example.test/work">宮上唯依花 Debut</a></span></p>
    </div>
    <div class="yarpp-thumbnails-horizontal">
      <a class="yarpp-thumbnail" href="https://db.avjoho.com/example/" title="永峰椿（ながみねつばき）">
        <img src="https://db.avjoho.com/wp-content/uploads/sample.jpg" alt="永峰椿">
        <span class="yarpp-thumbnail-title">永峰椿（ながみねつばき）</span>
      </a>
    </div>
  </div>
</div>
"""


def test_parse_avjoho_profile_extracts_profile_fields() -> None:
    profile = parse_avjoho_profile(SAMPLE, "https://db.avjoho.com/宮上唯依花/")

    assert profile is not None
    assert profile.display_name == "宮上唯依花"
    assert profile.reading == "みやうえゆいか"
    assert profile.image_url.endswith("1dldss00528ps.jpg")
    assert profile.debut_date.isoformat() == "2026-09-03"
    assert profile.birth_date.isoformat() == "1977-12-01"
    assert profile.height_cm == 163
    assert profile.bust_cm == 90
    assert profile.waist_cm == 62
    assert profile.hip_cm == 93
    assert profile.cup == "E"
    assert profile.birthplace == "京都府"
    assert profile.blood_type == "A型"
    assert "ヨガ" in profile.hobbies
    assert profile.exclusive_maker == "DAHLIA ※デビュー"
    assert profile.sns_links == [{"label": "X（旧Twitter）", "url": "https://x.com/MiyaueYuika", "text": "@MiyaueYuika"}]
    assert profile.representative_works[0]["title"] == "宮上唯依花 Debut"
    assert profile.similar_actresses[0]["name"] == "永峰椿（ながみねつばき）"
```

- [ ] **Step 2: Run the parser test to verify it fails**

Run: `python -m pytest backend/tests/test_avjoho_parser.py -v`

Expected: FAIL because the parser module does not exist.

- [ ] **Step 3: Implement the parser**

Create `backend/app/modules/content/actresses/avjoho_parser.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from scrapling.parser import Adaptor

from scraper.core.utils import clean_text


@dataclass
class AvjohoProfilePayload:
    display_name: str
    reading: str
    source_url: str
    image_url: str = ""
    aliases: list[str] = field(default_factory=list)
    debut_date: date | None = None
    birth_date: date | None = None
    height_cm: int | None = None
    bust_cm: int | None = None
    waist_cm: int | None = None
    hip_cm: int | None = None
    cup: str = ""
    birthplace: str = ""
    blood_type: str = ""
    hobbies: str = ""
    biography: str = ""
    exclusive_maker: str = ""
    sns_links: list[dict] = field(default_factory=list)
    representative_works: list[dict] = field(default_factory=list)
    similar_actresses: list[dict] = field(default_factory=list)
    raw_profile: dict = field(default_factory=dict)
```

Add helper functions in the same file with these exact names and behavior:

- `_first_text(page: Adaptor, selector: str) -> str`: return the first cleaned text for the selector, or `""`.
- `_first_attr(page: Adaptor, selector: str) -> str`: return the first cleaned attribute value for the selector, or `""`.
- `_parse_japanese_date(value: str) -> date | None`: parse `YYYY年M月D日` into `date(year, month, day)`, or return `None`.
- `_parse_int_cm(value: str) -> int | None`: return the first integer before `cm`, or return `None`.
- `_parse_measurements(value: str) -> tuple[int | None, int | None, int | None]`: parse `B90cm W62cm H93cm`.
- `_split_title(value: str) -> tuple[str, str]`: split `宮上唯依花（みやうえゆいか）` into display name and reading.
- `_collect_tables(page: Adaptor) -> dict[str, str]`: collect every `th`/`td` pair under `.database table`.
- `_parse_aliases(value: str) -> list[str]`: return an empty list for `""`, `-`, `–`, and `—`; otherwise split by comma.
- `_parse_sns(page: Adaptor) -> list[dict]`: collect `.sns tr` rows as `{"label": th_text, "url": href, "text": link_text_or_td_text}`.
- `_parse_representative_works(page: Adaptor) -> list[dict]`: collect `.gazou-large` and `.text-link` pairs after the `主な出演作品` heading.
- `_parse_similar_actresses(page: Adaptor) -> list[dict]`: collect `.yarpp-thumbnail` as `{"name": title_text, "url": href, "image_url": img_src}`.

The final public function must be:

```python
def parse_avjoho_profile(html: str, source_url: str) -> AvjohoProfilePayload | None:
    page = Adaptor(html)
    title = _first_text(page, "h1.entry-title::text")
    display_name, reading = _split_title(title)
    if not display_name:
        return None

    fields = _collect_tables(page)
    bust, waist, hip = _parse_measurements(fields.get("スリーサイズ", ""))
    payload = AvjohoProfilePayload(
        display_name=display_name,
        reading=reading,
        source_url=source_url,
        image_url=_first_attr(page, ".gazou img::attr(src)"),
        aliases=_parse_aliases(fields.get("別名", "")),
        debut_date=_parse_japanese_date(fields.get("デビュー", "")),
        birth_date=_parse_japanese_date(fields.get("生年月日", "")),
        height_cm=_parse_int_cm(fields.get("身長", "")),
        bust_cm=bust,
        waist_cm=waist,
        hip_cm=hip,
        cup=fields.get("カップ", ""),
        birthplace=fields.get("出身地", ""),
        blood_type=fields.get("血液型", ""),
        hobbies=fields.get("趣味・特技", ""),
        biography=_first_text(page, ".profile2::text"),
        exclusive_maker=fields.get("専属メーカー", ""),
        sns_links=_parse_sns(page),
        representative_works=_parse_representative_works(page),
        similar_actresses=_parse_similar_actresses(page),
        raw_profile=fields,
    )
    return payload
```

- [ ] **Step 4: Run the parser test**

Run: `python -m pytest backend/tests/test_avjoho_parser.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/content/actresses/__init__.py backend/app/modules/content/actresses/avjoho_parser.py backend/tests/test_avjoho_parser.py
git diff --cached --name-only
git commit -m "Parse avjoho actress profiles"
```

---

### Task 4: Actress Backend API and Fetch Service

**Files:**
- Create: `backend/app/modules/content/actresses/schemas.py`
- Create: `backend/app/modules/content/actresses/serializers.py`
- Create: `backend/app/modules/content/actresses/queries.py`
- Create: `backend/app/modules/content/actresses/service.py`
- Create: `backend/app/modules/content/actresses/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_content_actresses_api.py`

**Interfaces:**
- Produces: `GET /api/content/actresses`
- Produces: `GET /api/content/actresses/{profile_id}`
- Produces: `POST /api/content/actresses/fetch-from-task`
- Produces: `ActressFetchFromTaskRequest(task_id: uuid.UUID, avjoho_url: str | None = None)`
- Consumes: `ActressProfile` from Task 1, `parse_actor_section_metadata` from Task 2, `parse_avjoho_profile` from Task 3.

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_content_actresses_api.py` with these tests:

```python
import uuid
from datetime import date, datetime
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import ActressProfile, Movie


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def seed_profile(task_id: uuid.UUID | None = None, task_url_id: uuid.UUID | None = None) -> str:
    session = TestingSessionLocal()
    profile = ActressProfile(
        display_name="宮上唯依花",
        reading="みやうえゆいか",
        aliases=["Miyaue Yuika"],
        canonical_names=["宮上唯依花", "Miyaue Yuika"],
        source_url="https://db.avjoho.com/宮上唯依花/",
        source_task_ids=[task_id] if task_id else [],
        source_task_url_ids=[task_url_id] if task_url_id else [],
        image_url="https://example.test/cover.jpg",
        debut_date=date(2026, 9, 3),
        birth_date=date(1977, 12, 1),
        height_cm=163,
        bust_cm=90,
        waist_cm=62,
        hip_cm=93,
        cup="E",
        birthplace="京都府",
        exclusive_maker="DAHLIA",
        last_fetched_at=datetime(2026, 9, 9, 1, 0, 0),
    )
    session.add(profile)
    session.flush()
    profile_id = str(profile.id)
    session.commit()
    session.close()
    return profile_id


def test_list_actresses_uses_card_page_size_contract(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_profile()

    ok = client.get("/api/content/actresses?page=1&limit=24", headers=headers)
    bad = client.get("/api/content/actresses?page=1&limit=25", headers=headers)

    assert ok.status_code == HTTPStatus.OK
    assert ok.json()["data"]["page_size"] == 24
    assert ok.json()["data"]["rows"][0]["display_name"] == "宮上唯依花"
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_actress_detail_includes_recent_movies(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    task = CrawlTask(name="Actor Task", storage_location="Actor Task", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    task_url = CrawlTaskUrl(
        task_id=task.id,
        position=0,
        url="https://javdb.com/actors/a",
        url_type="actors",
        source="javdb",
        final_url="https://javdb.com/actors/a?page=1",
    )
    run = CrawlRun(task_id=task.id, task_name=task.name, status="completed", crawl_mode="incremental")
    old_movie = Movie(code="OLD-001", source_name="旧影片", actors=["No Name"], release_date=date(2025, 1, 1), cover="old.jpg", source_task_ids=[task.id])
    new_movie = Movie(code="NEW-001", source_name="新影片", actors=["Other Name"], release_date=date(2026, 1, 1), cover="new.jpg", source_task_ids=[task.id])
    session.add_all([task_url, run, old_movie, new_movie])
    session.flush()
    session.add_all([
        CrawlRunDetailTask(
            run_id=run.id,
            task_name=task.name,
            code="OLD-001",
            source_url="https://javdb.com/v/old",
            source_name="旧影片",
            task_url=task_url.url,
            task_url_type="actors",
            status="completed",
            movie_id=old_movie.id,
            created_at=datetime(2026, 9, 9, 1, 0, 0),
        ),
        CrawlRunDetailTask(
            run_id=run.id,
            task_name=task.name,
            code="NEW-001",
            source_url="https://javdb.com/v/new",
            source_name="新影片",
            task_url=task_url.url,
            task_url_type="actors",
            status="completed",
            movie_id=new_movie.id,
            created_at=datetime(2026, 9, 9, 1, 1, 0),
        ),
    ])
    session.commit()
    profile_id = seed_profile(task.id, task_url.id)
    session.close()

    response = client.get(f"/api/content/actresses/{profile_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["profile"]["id"] == profile_id
    assert [movie["code"] for movie in data["recent_movies"]] == ["NEW-001", "OLD-001"]


def test_fetch_from_task_rejects_task_without_actor_url(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    task = CrawlTask(name="No Actor", storage_location="No Actor", owner_id=admin_user.id)
    session.add(task)
    session.flush()
    session.add(CrawlTaskUrl(task_id=task.id, position=0, url="https://javdb.com/search?q=a", url_type="search", source="javdb", final_url="https://javdb.com/search?q=a"))
    task_id = str(task.id)
    session.commit()
    session.close()

    response = client.post("/api/content/actresses/fetch-from-task", json={"task_id": task_id}, headers=headers)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "actors" in response.json()["detail"]
```

Add separate service-level tests in the same file for manual URL validation and upsert merge:

```python
def test_fetch_from_task_rejects_non_avjoho_manual_url(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(uuid.uuid4()), "avjoho_url": "https://example.com/name/"},
        headers=headers,
    )

    assert response.status_code in {HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND}
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `python -m pytest backend/tests/test_content_actresses_api.py -v`

Expected: FAIL because the API module is not implemented.

- [ ] **Step 3: Add Pydantic schemas**

Create `backend/app/modules/content/actresses/schemas.py`:

```python
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class ActressProfileRead(BaseModel):
    id: uuid.UUID
    display_name: str
    reading: str
    aliases: list[str] = Field(default_factory=list)
    canonical_names: list[str] = Field(default_factory=list)
    source_url: str
    source_site: str
    image_url: str
    debut_date: date | None = None
    birth_date: date | None = None
    height_cm: int | None = None
    bust_cm: int | None = None
    waist_cm: int | None = None
    hip_cm: int | None = None
    cup: str
    birthplace: str
    blood_type: str
    hobbies: str
    biography: str
    exclusive_maker: str
    sns_links: list[dict] = Field(default_factory=list)
    representative_works: list[dict] = Field(default_factory=list)
    similar_actresses: list[dict] = Field(default_factory=list)
    source_task_ids: list[uuid.UUID] = Field(default_factory=list)
    source_task_url_ids: list[uuid.UUID] = Field(default_factory=list)
    last_fetched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ActressListResponse(BaseModel):
    rows: list[ActressProfileRead]
    total: int
    page: int
    page_size: int


class RecentMovieRead(BaseModel):
    id: uuid.UUID
    code: str | None = None
    title: str
    cover: str
    source_url: str | None = None
    release_date: date | None = None


class ActressDetailResponse(BaseModel):
    profile: ActressProfileRead
    recent_movies: list[RecentMovieRead]


class ActressFetchFromTaskRequest(BaseModel):
    task_id: uuid.UUID
    avjoho_url: str | None = Field(default=None, max_length=500)


class ActressFetchFailure(BaseModel):
    task_url_id: uuid.UUID
    url: str
    reason: str


class ActressFetchFromTaskResponse(BaseModel):
    profiles: list[ActressProfileRead]
    matched_candidate: str | None = None
    attempted_candidates: list[str] = Field(default_factory=list)
    used_manual_url: bool = False
    failures: list[ActressFetchFailure] = Field(default_factory=list)
```

- [ ] **Step 4: Add serializers and query helpers**

Create `serializers.py`:

```python
from backend.app.modules.content.actresses.schemas import ActressProfileRead


def serialize_actress_profile(profile) -> dict:
    return ActressProfileRead.model_validate(profile).model_dump(mode="json")
```

Create `queries.py` with these public functions:

```python
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTaskUrl
from shared.database.models.content import ActressProfile, Movie


VALID_ACTRESS_PAGE_SIZES = {8, 16, 24, 40}


def list_actress_profiles(db: Session, *, page: int, limit: int, keyword: str | None, source_task_id: str | None) -> tuple[list[ActressProfile], int]:
    query = select(ActressProfile)
    conditions = []
    if keyword and keyword.strip():
        text = f"%{keyword.strip()}%"
        conditions.append(or_(ActressProfile.display_name.ilike(text), ActressProfile.reading.ilike(text)))
    if source_task_id:
        conditions.append(ActressProfile.source_task_ids.any(uuid.UUID(source_task_id)))
    if conditions:
        query = query.where(*conditions)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(ActressProfile.updated_at.desc().nullslast(), ActressProfile.created_at.desc()).offset((page - 1) * limit).limit(limit)).all()
    return list(rows), total


def get_actress_profile(db: Session, profile_id: uuid.UUID) -> ActressProfile | None:
    return db.get(ActressProfile, profile_id)


def list_recent_movies_for_profile(db: Session, profile: ActressProfile, *, limit: int = 10) -> list[Movie]:
    task_ids = [uuid.UUID(str(value)) for value in (profile.source_task_ids or [])]
    task_url_ids = [uuid.UUID(str(value)) for value in (profile.source_task_url_ids or [])]
    if not task_ids or not task_url_ids:
        return []
    task_urls = db.scalars(select(CrawlTaskUrl.url).where(CrawlTaskUrl.id.in_(task_url_ids))).all()
    if not task_urls:
        return []
    movie_ids = select(CrawlRunDetailTask.movie_id).join(CrawlRun).where(
        CrawlRun.task_id.in_(task_ids),
        CrawlRunDetailTask.task_url.in_(list(task_urls)),
        CrawlRunDetailTask.movie_id.is_not(None),
    )
    query = select(Movie).where(Movie.id.in_(movie_ids))
    return list(db.scalars(query.order_by(Movie.release_date.desc().nullslast(), Movie.created_at.desc()).limit(limit)).all())
```

If the focused API test fails under SQLite because `CompatibleARRAY` stores arrays as JSON text, replace `ActressProfile.source_task_ids.any(uuid_value)` with the same dialect-specific helper pattern used by existing movie query tests in `backend/tests/test_content_movie_queries_sql.py`. Keep the public function signatures unchanged.

- [ ] **Step 5: Add service orchestration**

Create `service.py` with public class:

```python
class ActressProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_from_task(self, owner_id: uuid.UUID, body: ActressFetchFromTaskRequest) -> ActressFetchFromTaskResponse:
        return fetch_actress_profiles_from_task(self.db, owner_id, body)
```

Required internal functions and return contracts:

- `validate_avjoho_url(value: str) -> str`: return the stripped URL or raise `HTTPException(400, "avjoho URL 必须是 db.avjoho.com 的 HTTP(S) 地址")`.
- `build_avjoho_candidate_urls(candidates: list[str]) -> list[tuple[str, str]]`: return `(candidate, url)` tuples using `https://db.avjoho.com/{quote(candidate, safe="")}/`.
- `merge_unique(existing: list, incoming: list) -> list`: return existing values followed by new values, with duplicates removed after string trimming.
- `actor_candidate_names(task, task_url, javdb_metadata: dict[str, list[str]]) -> list[str]`: return unique names in `primary_names + aliases + [task_url.url_name, task.name]` order.
- `upsert_profile(db: Session, payload: AvjohoProfilePayload, *, task_id: uuid.UUID, task_url_id: uuid.UUID, candidate_names: list[str]) -> ActressProfile`: find by `source_url`, then by overlapping candidate names, then insert; update parsed fields and merge names/source IDs.
- `fetch_actress_profiles_from_task(db: Session, owner_id: uuid.UUID, body: ActressFetchFromTaskRequest) -> ActressFetchFromTaskResponse`: load task, collect actor URLs, fetch JavDB and avjoho pages, upsert profiles, and return match metadata.

`validate_avjoho_url` must parse with `urllib.parse.urlparse` and accept only schemes `http` and `https` with hostname exactly `db.avjoho.com`.

`actor_candidate_names` must order candidates:

```python
primary_names + aliases + [task_url.url_name, task.name]
```

and remove empty strings and duplicates.

`fetch_from_task` must:

```python
task = self.db.query(CrawlTask).options(selectinload(CrawlTask.urls)).filter(
    CrawlTask.id == body.task_id,
    CrawlTask.owner_id == owner_id,
).first()
if task is None:
    raise HTTPException(status_code=404, detail="Task not found")
actor_urls = [url for url in task.urls if url.url_type == "actors"]
if not actor_urls:
    raise HTTPException(status_code=400, detail="任务不包含 actors URL")
```

For each actor URL, fetch the JavDB actor page with `build_site_fetcher("javdb")`, call `detect_access_state(page)`, and parse metadata with `parse_actor_section_metadata(page)`. If `body.avjoho_url` is present, fetch that URL first and set `used_manual_url=True`. If no manual URL is present, build avjoho URLs from candidates using `quote(candidate.strip(), safe="")`.

Use `build_site_fetcher` for JavDB. For avjoho, use `requests.get(url, timeout=15)` or a small local fetch helper, then call `parse_avjoho_profile(response.text, normalized_url)`. A non-200 response or `None` parse counts as an attempted miss.

Commit the database transaction after successful upserts. If no profile is saved, raise:

```python
raise HTTPException(status_code=404, detail={"message": "未匹配到 avjoho 女优资料", "attempted_candidates": attempted_candidates})
```

- [ ] **Step 6: Add router and include it**

Create `router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.content.actresses.queries import VALID_ACTRESS_PAGE_SIZES, get_actress_profile, list_actress_profiles, list_recent_movies_for_profile
from backend.app.modules.content.actresses.schemas import ActressDetailResponse, ActressFetchFromTaskRequest, RecentMovieRead
from backend.app.modules.content.actresses.serializers import serialize_actress_profile
from backend.app.modules.content.actresses.service import ActressProfileService
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/content/actresses", tags=["content-actresses"])
```

Endpoint implementations:

```python
@router.get("")
def list_actresses(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24),
    keyword: str | None = Query(default=None, max_length=200),
    source_task_id: str | None = Query(default=None, max_length=36),
) -> dict:
    if limit not in VALID_ACTRESS_PAGE_SIZES:
        raise HTTPException(status_code=422, detail="limit must be one of 8, 16, 24, 40")
    rows, total = list_actress_profiles(db, page=page, limit=limit, keyword=keyword, source_task_id=source_task_id)
    return success(data={"rows": [serialize_actress_profile(row) for row in rows], "total": total, "page": page, "page_size": limit})

@router.get("/{profile_id:uuid}")
def get_actress(profile_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    profile = get_actress_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Actress profile not found")
    movies = list_recent_movies_for_profile(db, profile, limit=10)
    recent_movies = [
        RecentMovieRead(
            id=movie.id,
            code=movie.code,
            title=movie.source_name,
            cover=movie.cover,
            source_url=movie.source_url,
            release_date=movie.release_date,
        ).model_dump(mode="json")
        for movie in movies
    ]
    return success(data={"profile": serialize_actress_profile(profile), "recent_movies": recent_movies})

@router.post("/fetch-from-task")
def fetch_actress_from_task(body: ActressFetchFromTaskRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    result = ActressProfileService(db).fetch_from_task(current_user.id, body)
    return success(data=result.model_dump(mode="json"))
```

Reject invalid `limit` values with HTTP 422:

```python
if limit not in VALID_ACTRESS_PAGE_SIZES:
    raise HTTPException(status_code=422, detail="limit must be one of 8, 16, 24, 40")
```

In `backend/app/main.py`, add:

```python
from backend.app.modules.content.actresses.router import router as content_actresses_router
```

and include it next to movies:

```python
app.include_router(content_actresses_router)
```

- [ ] **Step 7: Run backend tests**

Run: `python -m pytest backend/tests/test_content_actresses_api.py backend/tests/test_content_models_metadata.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/content/actresses/schemas.py backend/app/modules/content/actresses/serializers.py backend/app/modules/content/actresses/queries.py backend/app/modules/content/actresses/service.py backend/app/modules/content/actresses/router.py backend/app/main.py backend/tests/test_content_actresses_api.py
git diff --cached --name-only
git commit -m "Add actress profile API"
```

---

### Task 5: Frontend Actress API, Routes, Card List, and Detail Page

**Files:**
- Create: `frontend/src/api/content/actresses/types.ts`
- Create: `frontend/src/api/content/actresses/index.ts`
- Modify: `frontend/src/api/queryKeys.ts`
- Create: `frontend/src/pages/content/actresses/ActressListPage.tsx`
- Create: `frontend/src/pages/content/actresses/ActressDetailPage.tsx`
- Create: `frontend/src/pages/content/actresses/ActressPages.module.less`
- Create: `frontend/src/pages/content/actresses/__tests__/actress-pages.test.tsx`
- Modify: `frontend/src/routes/index.tsx`
- Modify: `frontend/src/routes/tags.ts`
- Modify: `frontend/src/layout/Sidebar/index.tsx`

**Interfaces:**
- Consumes backend endpoints from Task 4.
- Produces route `/content/actresses`.
- Produces route `/content/actresses/$id`.
- Produces query keys `queryKeys.actresses.list(params)` and `queryKeys.actresses.detail(id)`.

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/src/pages/content/actresses/__tests__/actress-pages.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: 'profile-1' }),
}))

vi.mock('@/api/content/actresses', () => ({
  getActress: vi.fn(),
  getActresses: vi.fn(),
}))

import { getActress, getActresses } from '@/api/content/actresses'
import ActressDetailPage from '../ActressDetailPage'
import ActressListPage from '../ActressListPage'

function wrapper({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

const PROFILE = {
  id: 'profile-1',
  display_name: '宮上唯依花',
  reading: 'みやうえゆいか',
  aliases: ['Miyaue Yuika'],
  canonical_names: ['宮上唯依花'],
  source_url: 'https://db.avjoho.com/name/',
  source_site: 'avjoho',
  image_url: 'https://example.test/profile.jpg',
  debut_date: '2026-09-03',
  birth_date: '1977-12-01',
  height_cm: 163,
  bust_cm: 90,
  waist_cm: 62,
  hip_cm: 93,
  cup: 'E',
  birthplace: '京都府',
  blood_type: 'A型',
  hobbies: '',
  biography: '',
  exclusive_maker: 'DAHLIA',
  sns_links: [],
  representative_works: [],
  similar_actresses: [],
  source_task_ids: [],
  source_task_url_ids: [],
  last_fetched_at: '2026-09-09T01:00:00Z',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: null,
}

const RECENT_MOVIE = {
  id: 'movie-1',
  code: 'DLDSS-528',
  title: '宮上唯依花 Debut',
  cover: 'https://example.test/movie.jpg',
  source_url: 'https://javdb.com/v/example',
  release_date: '2026-09-03',
}

describe('actress pages', () => {
  beforeEach(() => {
    vi.mocked(getActresses).mockResolvedValue({
      rows: [PROFILE],
      total: 1,
      page: 1,
      page_size: 24,
    })
    vi.mocked(getActress).mockResolvedValue({
      profile: PROFILE,
      recent_movies: [RECENT_MOVIE],
    } as never)
  })

  it('renders actress cards with default page size 24', async () => {
    render(<ActressListPage />, { wrapper })

    expect(await screen.findByText('宮上唯依花')).toBeInTheDocument()
    expect(getActresses).toHaveBeenCalledWith(expect.objectContaining({ page: 1, limit: 24 }))
    expect(screen.getByText('Miyaue Yuika')).toBeInTheDocument()
  })

  it('renders recent movies on the standalone detail page', async () => {
    render(<ActressDetailPage />, { wrapper })

    expect(await screen.findByText('最近影片')).toBeInTheDocument()
    expect(screen.getByText('DLDSS-528')).toBeInTheDocument()
    expect(screen.getByText('宮上唯依花 Debut')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test -- src/pages/content/actresses/__tests__/actress-pages.test.tsx`

Expected: FAIL because the files do not exist.

- [ ] **Step 3: Add frontend API types and wrappers**

Create `frontend/src/api/content/actresses/types.ts`:

```ts
export interface ActressProfile {
  id: string
  display_name: string
  reading: string
  aliases: string[]
  canonical_names: string[]
  source_url: string
  source_site: string
  image_url: string
  debut_date: string | null
  birth_date: string | null
  height_cm: number | null
  bust_cm: number | null
  waist_cm: number | null
  hip_cm: number | null
  cup: string
  birthplace: string
  blood_type: string
  hobbies: string
  biography: string
  exclusive_maker: string
  sns_links: Array<{ label?: string; url?: string; text?: string }>
  representative_works: Array<{ title?: string; url?: string; image_url?: string }>
  similar_actresses: Array<{ name?: string; url?: string; image_url?: string }>
  source_task_ids: string[]
  source_task_url_ids: string[]
  last_fetched_at: string | null
  created_at: string
  updated_at: string | null
}

export interface ActressListResponse {
  rows: ActressProfile[]
  total: number
  page: number
  page_size: number
}

export interface RecentActressMovie {
  id: string
  code: string | null
  title: string
  cover: string
  source_url: string | null
  release_date: string | null
}

export interface ActressDetailResponse {
  profile: ActressProfile
  recent_movies: RecentActressMovie[]
}

export interface FetchActressFromTaskParams {
  task_id: string
  avjoho_url?: string
}

export interface FetchActressFromTaskResult {
  profiles: ActressProfile[]
  matched_candidate: string | null
  attempted_candidates: string[]
  used_manual_url: boolean
  failures: Array<{ task_url_id: string; url: string; reason: string }>
}
```

Create `index.ts`:

```ts
import { request } from '@/request'
import type { ActressDetailResponse, ActressListResponse, FetchActressFromTaskParams, FetchActressFromTaskResult } from './types'

const BASE_URL = '/api/content/actresses'

export function getActresses(params: { page: number; limit: number; keyword?: string; source_task_id?: string }): Promise<ActressListResponse> {
  return request.get<ActressListResponse>(BASE_URL, params)
}

export function getActress(id: string): Promise<ActressDetailResponse> {
  return request.get<ActressDetailResponse>(`${BASE_URL}/${id}`)
}

export function fetchActressFromTask(data: FetchActressFromTaskParams): Promise<FetchActressFromTaskResult> {
  return request.post<FetchActressFromTaskResult>(`${BASE_URL}/fetch-from-task`, data)
}
```

Add query keys:

```ts
actresses: {
  list: (params: { page: number; limit: number; keyword?: string; source_task_id?: string }) =>
    ['actresses', params] as const,
  detail: (id: string) => ['actresses', id] as const,
},
```

- [ ] **Step 4: Implement list/detail pages**

`ActressListPage.tsx` must use page size `24` by default and `['8', '16', '24', '40']` options:

```tsx
const ACTRESS_PAGE_SIZE_OPTIONS = ['8', '16', '24', '40']
const DEFAULT_ACTRESS_PAGE_SIZE = 24
```

Use Ant Design `Input.Search`, `Card`, `Image`, `Tag`, `Pagination`, and `Spin`. Each card should call:

```tsx
onClick={() => navigate({ to: '/content/actresses/$id', params: { id: profile.id } })}
```

`ActressDetailPage.tsx` must read `id` with `useParams`, call `getActress(id)`, render complete profile fields, and render backend-provided `最近影片` as a 10-item card grid with cover, `code`, and title. The frontend must not attempt name-based movie matching.

- [ ] **Step 5: Add routes, tags, and sidebar**

In `frontend/src/routes/index.tsx`, import the two pages and add:

```tsx
const contentActressesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/content/actresses',
  component: ActressListPage,
})

const contentActressDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/content/actresses/$id',
  component: ActressDetailPage,
})
```

Add both routes to `routeTree`.

In `frontend/src/routes/tags.ts`, add:

```ts
{ pattern: /^\/content\/actresses$/, meta: { title: '女优列表', singletonKey: '/content/actresses' } },
{
  pattern: /^\/content\/actresses\/[^/]+$/,
  meta: {
    title: '女优详情',
    activeMenu: '/content/actresses',
    singletonKey: '/content/actresses/:id',
  },
},
```

In `Sidebar/index.tsx`, add a user icon import such as `UserOutlined`, add menu item `/content/actresses`, and update selected key logic so `/content/actresses/$id` selects `/content/actresses`.

- [ ] **Step 6: Run frontend page tests**

Run: `cd frontend && pnpm test -- src/pages/content/actresses/__tests__/actress-pages.test.tsx`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/content/actresses/types.ts frontend/src/api/content/actresses/index.ts frontend/src/api/queryKeys.ts frontend/src/pages/content/actresses/ActressListPage.tsx frontend/src/pages/content/actresses/ActressDetailPage.tsx frontend/src/pages/content/actresses/ActressPages.module.less frontend/src/pages/content/actresses/__tests__/actress-pages.test.tsx frontend/src/routes/index.tsx frontend/src/routes/tags.ts frontend/src/layout/Sidebar/index.tsx
git diff --cached --name-only
git commit -m "Add actress profile pages"
```

---

### Task 6: Crawler Task One-Click Actress Fetch Action

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Modify: `frontend/src/pages/crawler/tasks/TaskListPage.tsx`
- Modify: `frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`

**Interfaces:**
- Consumes: `fetchActressFromTask({ task_id, avjoho_url? })` from Task 5.
- Produces: task-card action `获取女优资料` for actor tasks only.
- Produces: manual URL modal after automatic not-found errors.

- [ ] **Step 1: Write failing task-card action tests**

Extend `task-list-card-actions.test.tsx`:

```tsx
it('shows actress fetch action only for actor tasks', () => {
  renderCards()

  expect(screen.getByRole('button', { name: /获取女优资料/ })).toBeInTheDocument()
})

it('hides actress fetch action for non-actor tasks', () => {
  renderCards({
    tasks: [{
      ...baseTask,
      urls: [{ id: 'url-search', url: 'https://javdb.com/search?q=a', url_type: 'search', url_name: 'Search' }],
    }] as never,
  })

  expect(screen.queryByRole('button', { name: /获取女优资料/ })).not.toBeInTheDocument()
})

it('calls the actress fetch handler from the task card', () => {
  const onFetchActress = vi.fn()
  renderCards({ onFetchActress } as never)

  fireEvent.click(screen.getByRole('button', { name: /获取女优资料/ }))

  expect(onFetchActress).toHaveBeenCalledWith(expect.objectContaining({ id: 'task-1' }))
})
```

- [ ] **Step 2: Run the focused card tests to verify they fail**

Run: `cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`

Expected: FAIL because `onFetchActress` is not a prop and the button does not exist.

- [ ] **Step 3: Add card action prop and rendering**

In `TaskListCardsProps`, add:

```ts
onFetchActress: (task: CrawlTask) => void
```

In `TaskCard`, add the same prop and:

```ts
const hasActorUrls = task.urls.some((url) => url.url_type === 'actors')
const canFetchActress = runtimeReady && isIdle && !task.is_skip && hasActorUrls
```

Render the button in maintenance actions:

```tsx
{hasActorUrls && (
  <Tooltip title="获取女优资料">
    <Button
      aria-label={`获取 ${task.name} 的女优资料`}
      type="text"
      size="small"
      disabled={!canFetchActress}
      icon={<UserOutlined />}
      onClick={() => onFetchActress(task)}
    />
  </Tooltip>
)}
```

Import `UserOutlined` from `@ant-design/icons`.

- [ ] **Step 4: Wire TaskListPage fetch flow**

In `TaskListPage.tsx`, import:

```ts
import { fetchActressFromTask } from '@/api/content/actresses'
```

Add state:

```ts
const [fetchingActressTask, setFetchingActressTask] = useState<CrawlTask | null>(null)
const [manualAvjohoUrl, setManualAvjohoUrl] = useState('')
const [manualModalOpen, setManualModalOpen] = useState(false)
```

Add a helper:

```ts
const runFetchActress = useCallback(async (task: CrawlTask, avjohoUrl?: string) => {
  try {
    const result = await fetchActressFromTask({ task_id: task.id, avjoho_url: avjohoUrl })
    await queryClient.invalidateQueries({ queryKey: ['actresses'] })
    await message.success(`已更新 ${result.profiles.length} 条女优资料`)
    setManualModalOpen(false)
    setManualAvjohoUrl('')
  } catch (error) {
    const text = error instanceof Error ? error.message : '获取女优资料失败'
    if (!avjohoUrl && text.includes('未匹配到')) {
      setFetchingActressTask(task)
      setManualModalOpen(true)
      return
    }
    await message.error(text)
  }
}, [message, queryClient])
```

Pass:

```tsx
onFetchActress={(task) => void runFetchActress(task)}
```

Add a `Modal` with `Input` for manual URL:

```tsx
<Modal
  title="输入 avjoho 女优资料 URL"
  open={manualModalOpen}
  okText="获取"
  cancelText="取消"
  onCancel={() => setManualModalOpen(false)}
  onOk={() => {
    if (fetchingActressTask) {
      void runFetchActress(fetchingActressTask, manualAvjohoUrl)
    }
  }}
>
  <Input
    aria-label="avjoho URL"
    placeholder="https://db.avjoho.com/女优姓名/"
    value={manualAvjohoUrl}
    onChange={(event) => setManualAvjohoUrl(event.target.value)}
  />
</Modal>
```

Keep modal placement near existing task modals.

- [ ] **Step 5: Run focused frontend tests**

Run: `cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx src/pages/content/actresses/__tests__/actress-pages.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
git diff --cached --name-only
git commit -m "Add task actress fetch action"
```

---

### Task 7: Full Verification and Documentation Check

**Files:**
- Modify: `frontend/README.md` only if route/module conventions changed in a way the README documents.
- No source edits expected unless verification exposes defects.

**Interfaces:**
- Consumes all tasks.
- Produces passing verification evidence and final commits.

- [ ] **Step 1: Run backend-focused verification**

Run:

```bash
python -m pytest backend/tests/test_content_models_metadata.py backend/tests/test_avjoho_parser.py backend/tests/test_content_actresses_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run scraper parser verification**

Run:

```bash
python -m pytest scraper/tests/test_javdb_actor_metadata.py scraper/tests/test_javdb_parser_detail_title.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend-focused verification**

Run:

```bash
cd frontend && pnpm test -- src/pages/content/actresses/__tests__/actress-pages.test.tsx src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && pnpm build
```

Expected: PASS.

- [ ] **Step 5: Inspect final worktree**

Run:

```bash
git status --short
git log --oneline -5
```

Expected: no unstaged source changes unless verification forced a final fix; recent commits should correspond to the functional groups in this plan.

- [ ] **Step 6: Commit final fixes if any**

If verification required edits, stage only the touched files:

```bash
git add <exact-files>
git diff --cached --name-only
git commit -m "Fix actress profile verification issues"
```

Expected: commit contains only verification fixes.
