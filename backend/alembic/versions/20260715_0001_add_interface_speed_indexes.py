"""add interface speed indexes

Revision ID: 20260715_0001
Revises: 20260708_0002
Create Date: 2026-07-15 00:00:00.000000
"""

from alembic import op


revision = "20260715_0001"
down_revision = "20260708_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_crawl_runs_created_at_desc ON crawl_runs (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crawl_runs_task_created_at_desc ON crawl_runs (task_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crawl_runs_task_status_created_at_desc ON crawl_runs (task_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_storage_main_created_by_created_at_desc ON storage_main_tasks (created_by, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_storage_main_created_by_status_created_at_desc ON storage_main_tasks (created_by, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_storage_sub_main_created_at ON storage_sub_tasks (main_task_id, created_at)")


def downgrade() -> None:
    op.drop_index("idx_storage_sub_main_created_at", table_name="storage_sub_tasks")
    op.drop_index("idx_storage_main_created_by_status_created_at_desc", table_name="storage_main_tasks")
    op.drop_index("idx_storage_main_created_by_created_at_desc", table_name="storage_main_tasks")
    op.drop_index("idx_crawl_runs_task_status_created_at_desc", table_name="crawl_runs")
    op.drop_index("idx_crawl_runs_task_created_at_desc", table_name="crawl_runs")
    op.drop_index("idx_crawl_runs_created_at_desc", table_name="crawl_runs")
