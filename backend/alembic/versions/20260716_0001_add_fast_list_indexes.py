"""add fast list indexes

Revision ID: 20260716_0001
Revises: 20260715_0001
Create Date: 2026-07-16 00:00:00.000000
"""

from alembic import op


revision = "20260716_0001"
down_revision = "20260715_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_crawl_tasks_owner_created_at_desc ON crawl_tasks (owner_id, created_at DESC)")


def downgrade() -> None:
    op.drop_index("idx_crawl_tasks_owner_created_at_desc", table_name="crawl_tasks")
