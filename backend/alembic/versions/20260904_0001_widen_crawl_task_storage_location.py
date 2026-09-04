"""widen crawl task storage location

Revision ID: 20260904_0001
Revises: 20260817_0001
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0001"
down_revision = "20260817_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "crawl_tasks",
        "storage_location",
        existing_type=sa.String(length=10),
        type_=sa.String(length=200),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "crawl_tasks",
        "storage_location",
        existing_type=sa.String(length=200),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
