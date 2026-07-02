"""replace source_task_names with source_task_ids in movies

Revision ID: 20260703_0003
Revises: 20260703_0002
Create Date: 2026-07-03 02:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260703_0003"
down_revision = "20260703_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add source_task_ids array column
    op.add_column(
        "movies",
        sa.Column(
            "source_task_ids",
            postgresql.ARRAY(sa.Uuid()),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
    )
    # Drop old index and column
    op.drop_index("idx_movies_source_task_names_gin", table_name="movies")
    op.drop_column("movies", "source_task_names")
    # Create new GIN index
    op.create_index(
        "idx_movies_source_task_ids_gin",
        "movies",
        ["source_task_ids"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    # Revert: add source_task_names back
    op.drop_index("idx_movies_source_task_ids_gin", table_name="movies")
    op.add_column(
        "movies",
        sa.Column(
            "source_task_names",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.create_index(
        "idx_movies_source_task_names_gin",
        "movies",
        ["source_task_names"],
        postgresql_using="gin",
    )
    op.drop_column("movies", "source_task_ids")
