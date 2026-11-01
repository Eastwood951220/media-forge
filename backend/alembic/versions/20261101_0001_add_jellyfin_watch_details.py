"""Store Jellyfin last played time and play count.

Revision ID: 20261101_0001
Revises: 20261030_0001
"""

from alembic import op
import sqlalchemy as sa


revision = "20261101_0001"
down_revision = "20261030_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("jellyfin_last_played_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("movies", sa.Column("jellyfin_play_count", sa.Integer(), nullable=True))
    op.create_index("idx_movies_jellyfin_last_played_at", "movies", ["jellyfin_last_played_at"])
    op.create_index("idx_movies_jellyfin_play_count", "movies", ["jellyfin_play_count"])


def downgrade() -> None:
    op.drop_index("idx_movies_jellyfin_play_count", table_name="movies")
    op.drop_index("idx_movies_jellyfin_last_played_at", table_name="movies")
    op.drop_column("movies", "jellyfin_play_count")
    op.drop_column("movies", "jellyfin_last_played_at")
