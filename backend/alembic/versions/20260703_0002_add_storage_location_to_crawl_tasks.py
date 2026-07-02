"""add storage_location to crawl_tasks

Revision ID: 20260703_0002
Revises: 20260703_0001
Create Date: 2026-07-03 01:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260703_0002"
down_revision = "20260703_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crawl_tasks",
        sa.Column("storage_location", sa.String(length=10), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("crawl_tasks", "storage_location")
