"""add crawl_runs table

Revision ID: 20260702_0002
Revises: 20260702_0001
Create Date: 2026-07-02 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260702_0002"
down_revision = "20260702_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_found", sa.Integer(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("total_qualified", sa.Integer(), nullable=False),
        sa.Column("total_failed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["crawl_tasks.id"],
            name="fk_crawl_runs_task_id_crawl_tasks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_crawl_runs_owner_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_runs"),
    )
    op.create_index("ix_crawl_runs_task_id", "crawl_runs", ["task_id"])
    op.create_index("ix_crawl_runs_owner_id", "crawl_runs", ["owner_id"])
    op.create_index("ix_crawl_runs_status", "crawl_runs", ["status"])
    op.create_index("idx_crawl_runs_task_created", "crawl_runs", ["task_id", "created_at"])
    op.create_index("idx_crawl_runs_owner_created", "crawl_runs", ["owner_id", "created_at"])
    op.create_index("idx_crawl_runs_owner_status", "crawl_runs", ["owner_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_crawl_runs_owner_status", table_name="crawl_runs")
    op.drop_index("idx_crawl_runs_owner_created", table_name="crawl_runs")
    op.drop_index("idx_crawl_runs_task_created", table_name="crawl_runs")
    op.drop_index("ix_crawl_runs_status", table_name="crawl_runs")
    op.drop_index("ix_crawl_runs_owner_id", table_name="crawl_runs")
    op.drop_index("ix_crawl_runs_task_id", table_name="crawl_runs")
    op.drop_table("crawl_runs")
