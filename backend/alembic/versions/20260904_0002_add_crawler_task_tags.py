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
