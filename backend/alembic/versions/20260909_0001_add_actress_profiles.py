"""add actress profiles

Revision ID: 20260909_0001
Revises: 20260904_0003
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260909_0001"
down_revision = "20260904_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actress_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("reading", sa.Text(), nullable=False),
        sa.Column("aliases", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("canonical_names", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_site", sa.Text(), nullable=False),
        sa.Column("source_task_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("source_task_url_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("debut_date", sa.Date(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("bust_cm", sa.Integer(), nullable=True),
        sa.Column("waist_cm", sa.Integer(), nullable=True),
        sa.Column("hip_cm", sa.Integer(), nullable=True),
        sa.Column("cup", sa.Text(), nullable=False),
        sa.Column("birthplace", sa.Text(), nullable=False),
        sa.Column("blood_type", sa.Text(), nullable=False),
        sa.Column("hobbies", sa.Text(), nullable=False),
        sa.Column("biography", sa.Text(), nullable=False),
        sa.Column("exclusive_maker", sa.Text(), nullable=False),
        sa.Column("sns_links", sa.JSON(), nullable=False),
        sa.Column("representative_works", sa.JSON(), nullable=False),
        sa.Column("similar_actresses", sa.JSON(), nullable=False),
        sa.Column("raw_profile", sa.JSON(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url", name="uq_actress_profiles_source_url"),
    )
    op.create_index("idx_actress_profiles_display_name", "actress_profiles", ["display_name"])
    op.create_index("idx_actress_profiles_source_url", "actress_profiles", ["source_url"])
    op.create_index(
        "idx_actress_profiles_source_task_ids_gin",
        "actress_profiles",
        ["source_task_ids"],
        postgresql_using="gin",
    )
    op.create_index("idx_actress_profiles_aliases_gin", "actress_profiles", ["aliases"], postgresql_using="gin")
    op.create_index(
        "idx_actress_profiles_canonical_names_gin",
        "actress_profiles",
        ["canonical_names"],
        postgresql_using="gin",
    )
    op.add_column(
        "movies",
        sa.Column("source_task_url_ids", sa.ARRAY(sa.Uuid()), nullable=False, server_default=sa.text("'{}'::uuid[]")),
    )
    op.create_index("idx_movies_source_task_url_ids_gin", "movies", ["source_task_url_ids"], postgresql_using="gin")
    op.alter_column("movies", "source_task_url_ids", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_movies_source_task_url_ids_gin", table_name="movies")
    op.drop_column("movies", "source_task_url_ids")
    op.drop_index("idx_actress_profiles_canonical_names_gin", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_aliases_gin", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_source_task_ids_gin", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_source_url", table_name="actress_profiles")
    op.drop_index("idx_actress_profiles_display_name", table_name="actress_profiles")
    op.drop_table("actress_profiles")
