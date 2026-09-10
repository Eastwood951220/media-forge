"""Coverage for the actress-only tag normalization migration.

Two layers:

* a database-free parity guard that keeps the Alembic revision and the SQL
  mirror statement-for-statement identical, and
* a PostgreSQL-gated test that exercises the four data-copy statements against
  a throwaway scratch schema inside a transaction that is always rolled back.
"""

from __future__ import annotations

import importlib.util
import re
import uuid
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
MIGRATION_PATH = _BACKEND_DIR / "alembic" / "versions" / "20260910_0002_normalize_actress_tags.py"
MIRROR_PATH = _REPO_ROOT / "sql" / "20260910_normalize_actress_tags.sql"

_EXECUTE_PATTERN = re.compile(r'op\.execute\(\s*"""(.*?)"""\s*\)', re.DOTALL)


def _read_migration_text() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _upgrade_sql_blocks(migration_text: str) -> list[str]:
    upgrade_start = migration_text.index("def upgrade()")
    downgrade_start = migration_text.index("def downgrade()")
    upgrade_body = migration_text[upgrade_start:downgrade_start]
    return [match.group(1) for match in _EXECUTE_PATTERN.finditer(upgrade_body)]


def _normalize_sql(sql: str) -> str:
    without_comments = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return " ".join(without_comments.split()).rstrip(";").strip()


def _mirror_insert_statements(sql_text: str) -> list[str]:
    statements = [
        statement
        for statement in sql_text.split(";")
        if _normalize_sql(statement).upper().startswith("INSERT INTO")
    ]
    return statements


def test_migration_and_sql_mirror_are_statement_for_statement_identical() -> None:
    migration_text = _read_migration_text()
    sql_text = MIRROR_PATH.read_text(encoding="utf-8")

    blocks = _upgrade_sql_blocks(migration_text)
    assert len(blocks) == 4
    mirror_inserts = _mirror_insert_statements(sql_text)
    assert len(mirror_inserts) == 4

    assert [_normalize_sql(block) for block in blocks] == [
        _normalize_sql(statement) for statement in mirror_inserts
    ]


def test_migration_down_revision_points_at_previous_revision() -> None:
    spec = importlib.util.spec_from_file_location("_actress_tag_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "20260910_0001"


# -- PostgreSQL-gated transformation coverage --------------------------------

# Minimal legacy schema read by the four statements, plus the two new tables
# they write. Nothing here references the real mediaforge schema.
_SETUP_DDL = (
    """
    CREATE TABLE actress_profiles (
        id UUID PRIMARY KEY,
        source_task_ids UUID[] NOT NULL DEFAULT '{}',
        tags TEXT[] NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE crawl_tasks (
        id UUID PRIMARY KEY,
        owner_id UUID NOT NULL
    )
    """,
    """
    CREATE TABLE crawl_task_tags (
        id UUID PRIMARY KEY,
        name VARCHAR(50) NOT NULL
    )
    """,
    """
    CREATE TABLE crawl_task_tag_links (
        task_id UUID NOT NULL,
        tag_id UUID NOT NULL
    )
    """,
    """
    CREATE TABLE actress_tags (
        id UUID PRIMARY KEY,
        owner_id UUID NOT NULL,
        name VARCHAR(50) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_actress_tags_owner_name UNIQUE (owner_id, name)
    )
    """,
    """
    CREATE TABLE actress_tag_links (
        actress_profile_id UUID NOT NULL,
        tag_id UUID NOT NULL,
        PRIMARY KEY (actress_profile_id, tag_id)
    )
    """,
)

LONG_TAG = "长" * 51


def _text_array(values: list[str]) -> str:
    return "ARRAY[" + ", ".join("'" + value.replace("'", "''") + "'" for value in values) + "]::text[]"


def _postgres_sync_url() -> str | None:
    from shared.runtime_config import load_runtime_config

    values = load_runtime_config(override=True)
    url = values.get("DATABASE_URL")
    if not url:
        return None
    return url.replace("+asyncpg", "+psycopg")


def _connect_postgres():
    url = _postgres_sync_url()
    if not url:
        pytest.skip("DATABASE_URL is not configured; skipping the PostgreSQL migration test")

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    try:
        engine = create_engine(url, poolclass=NullPool)
        connection = engine.connect()
    except Exception as exc:  # pragma: no cover - depends on the local environment
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    return engine, connection


def test_actress_tag_migration_transformation_is_owner_scoped_and_skips_over_long_names() -> None:
    """Exercise the four INSERTs in a scratch schema that is always rolled back."""
    engine, connection = _connect_postgres()
    schema = f"mf_actress_tag_test_{uuid.uuid4().hex[:12]}"

    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    task_a, task_b, task_no_match = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    profile_a, profile_b = uuid.uuid4(), uuid.uuid4()
    tag_match, tag_no_match, tag_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    transaction = connection.begin()
    try:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        for ddl in _SETUP_DDL:
            connection.exec_driver_sql(ddl)

        seed_statements = [
            "INSERT INTO crawl_tasks (id, owner_id) VALUES "
            f"('{task_a}', '{user_a}'), ('{task_b}', '{user_b}'), ('{task_no_match}', '{user_a}')",
            "INSERT INTO actress_profiles (id, source_task_ids, tags) VALUES "
            f"('{profile_a}', ARRAY['{task_a}']::uuid[], {_text_array(['标签A', '重复', LONG_TAG])}), "
            f"('{profile_b}', ARRAY['{task_b}']::uuid[], {_text_array(['标签B'])})",
            "INSERT INTO crawl_task_tags (id, name) VALUES "
            f"('{tag_match}', '匹配标签'), ('{tag_no_match}', '无匹配标签'), ('{tag_b}', 'B任务标签')",
            "INSERT INTO crawl_task_tag_links (task_id, tag_id) VALUES "
            f"('{task_a}', '{tag_match}'), ('{task_no_match}', '{tag_no_match}'), ('{task_b}', '{tag_b}')",
        ]
        for statement in seed_statements:
            connection.exec_driver_sql(statement)

        # Run the migration's own four statements, in order.
        for block in _upgrade_sql_blocks(_read_migration_text()):
            connection.exec_driver_sql(block)

        tag_rows = connection.exec_driver_sql(
            "SELECT owner_id::text, name FROM actress_tags ORDER BY owner_id, name"
        ).fetchall()
        tags_by_owner: dict[str, set[str]] = {}
        for owner, name in tag_rows:
            tags_by_owner.setdefault(owner, set()).add(name)

        # Owner scoping: each owner sees only their own dictionary rows.
        assert tags_by_owner.get(str(user_a)) == {"标签A", "重复", "匹配标签"}
        assert tags_by_owner.get(str(user_b)) == {"标签B", "B任务标签"}
        assert "标签B" not in tags_by_owner[str(user_a)]
        assert "标签A" not in tags_by_owner[str(user_b)]

        all_names = {name for _owner, name in tag_rows}
        # Over-long legacy array names are skipped instead of aborting.
        assert LONG_TAG not in all_names
        assert all(len(name) <= 50 for name in all_names)
        # Task tags linked to no actress profile are dropped.
        assert "无匹配标签" not in all_names

        link_rows = connection.exec_driver_sql(
            "SELECT atl.actress_profile_id::text, at.owner_id::text, at.name "
            "FROM actress_tag_links atl JOIN actress_tags at ON at.id = atl.tag_id "
            "ORDER BY at.name"
        ).fetchall()
        links = {(profile, owner, name) for profile, owner, name in link_rows}

        # A profile array tag whose owner owns the source task yields both a
        # dictionary row and a link.
        assert (str(profile_a), str(user_a), "标签A") in links
        assert (str(profile_b), str(user_b), "标签B") in links
        # A matched crawl task tag is copied and linked as well.
        assert (str(profile_a), str(user_a), "匹配标签") in links
        assert (str(profile_b), str(user_b), "B任务标签") in links
        # Links never cross owners.
        assert all(owner == str(user_a) for profile, owner, _name in links if profile == str(profile_a))
        assert all(owner == str(user_b) for profile, owner, _name in links if profile == str(profile_b))
        # No link is created for skipped or dropped names.
        assert all(name != LONG_TAG for _profile, _owner, name in links)
        assert all(name != "无匹配标签" for _profile, _owner, name in links)
    finally:
        # PostgreSQL DDL is transactional, so the scratch schema disappears here
        # and the real mediaforge schema is left untouched.
        transaction.rollback()
        connection.close()
        engine.dispose()
