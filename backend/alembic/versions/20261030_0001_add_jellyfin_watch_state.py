"""Add Jellyfin watch snapshot and sync status.

Revision ID: 20261030_0001
Revises: 20261022_0001
"""

from alembic import op
import sqlalchemy as sa


revision = "20261030_0001"
down_revision = "20261022_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("jellyfin_item_id", sa.String(length=100), nullable=True))
    op.add_column("movies", sa.Column("jellyfin_watch_status", sa.String(length=30), nullable=True))
    op.add_column("movies", sa.Column("jellyfin_playback_position_ticks", sa.BigInteger(), nullable=True))
    op.create_index("idx_movies_jellyfin_watch_status", "movies", ["jellyfin_watch_status"])
    op.create_table(
        "jellyfin_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("jellyfin_sync_state")
    op.drop_index("idx_movies_jellyfin_watch_status", table_name="movies")
    op.drop_column("movies", "jellyfin_playback_position_ticks")
    op.drop_column("movies", "jellyfin_watch_status")
    op.drop_column("movies", "jellyfin_item_id")
