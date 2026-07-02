"""add source_task_id to movies

Revision ID: 20260703_0001
Revises: 20260702_0002
Create Date: 2026-07-03 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260703_0001"
down_revision = "20260702_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "movies",
        sa.Column("source_task_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_movies_source_task_id_crawl_tasks",
        "movies",
        "crawl_tasks",
        ["source_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_movies_source_task_id", "movies", ["source_task_id"])


def downgrade() -> None:
    op.drop_index("idx_movies_source_task_id", table_name="movies")
    op.drop_constraint("fk_movies_source_task_id_crawl_tasks", "movies", type_="foreignkey")
    op.drop_column("movies", "source_task_id")
