"""add url context to crawl run detail tasks

Revision ID: 20260708_0001
Revises: 20260704_0001
Create Date: 2026-07-08 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260708_0001"
down_revision = "20260704_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_run_detail_tasks", sa.Column("source_url_name", sa.String(length=200), nullable=True))
    op.add_column("crawl_run_detail_tasks", sa.Column("task_url", sa.Text(), nullable=True))
    op.add_column("crawl_run_detail_tasks", sa.Column("task_final_url", sa.Text(), nullable=True))
    op.add_column("crawl_run_detail_tasks", sa.Column("task_url_type", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_run_detail_tasks", "task_url_type")
    op.drop_column("crawl_run_detail_tasks", "task_final_url")
    op.drop_column("crawl_run_detail_tasks", "task_url")
    op.drop_column("crawl_run_detail_tasks", "source_url_name")
