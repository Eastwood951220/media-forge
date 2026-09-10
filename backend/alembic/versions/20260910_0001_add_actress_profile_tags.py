"""add actress profile tags

Revision ID: 20260910_0001
Revises: 20260909_0001
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260910_0001"
down_revision = "20260909_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "actress_profiles",
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
    )
    op.create_index("idx_actress_profiles_tags_gin", "actress_profiles", ["tags"], postgresql_using="gin")
    op.alter_column("actress_profiles", "tags", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_actress_profiles_tags_gin", table_name="actress_profiles")
    op.drop_column("actress_profiles", "tags")
