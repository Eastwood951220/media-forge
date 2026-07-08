"""add crawler detail queue indexes

Revision ID: 20260708_0002
Revises: 20260708_0001
Create Date: 2026-07-08
"""

from alembic import op

revision = "20260708_0002"
down_revision = "20260708_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_crawl_detail_claim", "crawl_run_detail_tasks", ["run_id", "status", "created_at"])
    op.create_index("idx_crawl_detail_run_code", "crawl_run_detail_tasks", ["run_id", "code"])


def downgrade() -> None:
    op.drop_index("idx_crawl_detail_run_code", table_name="crawl_run_detail_tasks")
    op.drop_index("idx_crawl_detail_claim", table_name="crawl_run_detail_tasks")
