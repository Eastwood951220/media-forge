"""restore crawler task url schema

Revision ID: 20260702_0001
Revises:
Create Date: 2026-07-02 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260702_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_skip", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=True),
        sa.Column("celery_id", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_found", sa.Integer(), nullable=False),
        sa.Column("total_qualified", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_crawl_tasks_owner_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_tasks"),
        sa.UniqueConstraint("owner_id", "name", name="uq_crawl_tasks_owner_name"),
        sa.UniqueConstraint("task_id", name="uq_crawl_tasks_task_id"),
    )
    op.create_index("ix_crawl_tasks_owner_id", "crawl_tasks", ["owner_id"])
    op.create_index("ix_crawl_tasks_status", "crawl_tasks", ["status"])
    op.create_index("idx_crawl_tasks_owner_created_at", "crawl_tasks", ["owner_id", "created_at"])
    op.create_index("idx_crawl_tasks_owner_skip", "crawl_tasks", ["owner_id", "is_skip"])

    op.create_table(
        "crawl_task_urls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_type", sa.String(length=50), nullable=False),
        sa.Column("has_magnet", sa.Boolean(), nullable=False),
        sa.Column("has_chinese_sub", sa.Boolean(), nullable=False),
        sa.Column("sort_type", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("url_name", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["crawl_tasks.id"], name="fk_crawl_task_urls_task_id_crawl_tasks", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_task_urls"),
        sa.UniqueConstraint("task_id", "url", name="uq_crawl_task_urls_task_url"),
    )
    op.create_index("ix_crawl_task_urls_task_id", "crawl_task_urls", ["task_id"])
    op.create_index("idx_crawl_task_urls_task_position", "crawl_task_urls", ["task_id", "position"])
    op.create_index("idx_crawl_task_urls_source", "crawl_task_urls", ["source"])
    op.create_index("idx_crawl_task_urls_url_type", "crawl_task_urls", ["url_type"])


def downgrade() -> None:
    op.drop_index("idx_crawl_task_urls_url_type", table_name="crawl_task_urls")
    op.drop_index("idx_crawl_task_urls_source", table_name="crawl_task_urls")
    op.drop_index("idx_crawl_task_urls_task_position", table_name="crawl_task_urls")
    op.drop_index("ix_crawl_task_urls_task_id", table_name="crawl_task_urls")
    op.drop_table("crawl_task_urls")
    op.drop_index("idx_crawl_tasks_owner_skip", table_name="crawl_tasks")
    op.drop_index("idx_crawl_tasks_owner_created_at", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_status", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_owner_id", table_name="crawl_tasks")
    op.drop_table("crawl_tasks")
