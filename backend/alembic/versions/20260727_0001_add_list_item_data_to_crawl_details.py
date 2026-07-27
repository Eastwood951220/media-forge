"""add list item data to crawl detail tasks

Revision ID: 20260727_0001
Revises: 20260716_0001
Create Date: 2026-07-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260727_0001"
down_revision = "20260716_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crawl_run_detail_tasks",
        sa.Column("list_item_data", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crawl_run_detail_tasks", "list_item_data")
