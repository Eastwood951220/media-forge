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
