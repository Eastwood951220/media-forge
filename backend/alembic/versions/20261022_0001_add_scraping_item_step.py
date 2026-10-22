"""Add current scraping item step.

Revision ID: 20261022_0001
Revises: 20261020_0001
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_0001"
down_revision = "20261020_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scraping_task_items",
        sa.Column("step", sa.String(length=50), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("scraping_task_items", "step")
