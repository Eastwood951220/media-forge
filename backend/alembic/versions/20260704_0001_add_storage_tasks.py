"""add storage tasks

Revision ID: 20260704_0001
Revises: 20260703_0003
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql
from alembic import op

revision: str = "20260704_0001"
down_revision: str | None = "20260703_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = sa.JSON() if bind.dialect.name == "sqlite" else sa.dialects.postgresql.JSONB()
    json_empty = sa.text("'{}'") if bind.dialect.name == "sqlite" else sa.text("'{}'::jsonb")
    json_list = sa.text("'[]'") if bind.dialect.name == "sqlite" else sa.text("'[]'::jsonb")

    op.create_table(
        "storage_main_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=240), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("storage_mode", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_snapshot", json_type, nullable=False, server_default=json_empty),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_storage_main_status_created", "storage_main_tasks", ["status", "created_at"])
    op.create_index("idx_storage_main_created_by_status", "storage_main_tasks", ["created_by", "status"])

    op.create_table(
        "storage_sub_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("main_task_id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("movie_code", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("movie_title", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("step", sa.String(length=50), nullable=False, server_default="prepare"),
        sa.Column("storage_mode", sa.String(length=30), nullable=False),
        sa.Column("selected_storage_location", sa.Text(), nullable=True),
        sa.Column("target_locations", json_type, nullable=False, server_default=json_list),
        sa.Column("download_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_paths", json_type, nullable=False, server_default=json_list),
        sa.Column("magnet_attempts", json_type, nullable=False, server_default=json_list),
        sa.Column("current_magnet_id", sa.Uuid(), nullable=True),
        sa.Column("current_magnet_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("renamed_files", json_type, nullable=False, server_default=json_list),
        sa.Column("moved_files", json_type, nullable=False, server_default=json_list),
        sa.Column("skipped_files", json_type, nullable=False, server_default=json_list),
        sa.Column("result", json_type, nullable=False, server_default=json_empty),
        sa.Column("skip_reason", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["main_task_id"], ["storage_main_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_storage_sub_main_status", "storage_sub_tasks", ["main_task_id", "status"])
    op.create_index("idx_storage_sub_movie_status", "storage_sub_tasks", ["movie_id", "status"])
    op.create_index("idx_storage_sub_created", "storage_sub_tasks", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_storage_sub_created", table_name="storage_sub_tasks")
    op.drop_index("idx_storage_sub_movie_status", table_name="storage_sub_tasks")
    op.drop_index("idx_storage_sub_main_status", table_name="storage_sub_tasks")
    op.drop_table("storage_sub_tasks")
    op.drop_index("idx_storage_main_created_by_status", table_name="storage_main_tasks")
    op.drop_index("idx_storage_main_status_created", table_name="storage_main_tasks")
    op.drop_table("storage_main_tasks")
