"""add scraping status and scraping tasks

Revision ID: 20261020_0001
Revises: 20260910_0002
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0001"
down_revision = "20260910_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("scraping_status", sa.String(length=20), nullable=True))
    op.add_column("movies", sa.Column("scraping_folder", sa.Text(), nullable=True))
    op.add_column("movies", sa.Column("scraping_checked_at", sa.DateTime(), nullable=True))

    op.create_table(
        "scraping_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scraping_tasks_status"), "scraping_tasks", ["status"])
    op.create_index(op.f("ix_scraping_tasks_created_by"), "scraping_tasks", ["created_by"])
    op.create_index("idx_scraping_tasks_status_created", "scraping_tasks", ["status", "created_at"])
    op.create_index("idx_scraping_tasks_created_by_status", "scraping_tasks", ["created_by", "status"])

    op.create_table(
        "scraping_task_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("movie_code", sa.String(length=100), nullable=False),
        sa.Column("movie_title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["scraping_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scraping_task_items_task_id"), "scraping_task_items", ["task_id"])
    op.create_index(op.f("ix_scraping_task_items_status"), "scraping_task_items", ["status"])
    op.create_index("idx_scraping_items_task_status", "scraping_task_items", ["task_id", "status"])
    op.create_index("idx_scraping_items_created", "scraping_task_items", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_scraping_items_created", table_name="scraping_task_items")
    op.drop_index("idx_scraping_items_task_status", table_name="scraping_task_items")
    op.drop_index(op.f("ix_scraping_task_items_status"), table_name="scraping_task_items")
    op.drop_index(op.f("ix_scraping_task_items_task_id"), table_name="scraping_task_items")
    op.drop_table("scraping_task_items")

    op.drop_index("idx_scraping_tasks_created_by_status", table_name="scraping_tasks")
    op.drop_index("idx_scraping_tasks_status_created", table_name="scraping_tasks")
    op.drop_index(op.f("ix_scraping_tasks_created_by"), table_name="scraping_tasks")
    op.drop_index(op.f("ix_scraping_tasks_status"), table_name="scraping_tasks")
    op.drop_table("scraping_tasks")

    op.drop_column("movies", "scraping_checked_at")
    op.drop_column("movies", "scraping_folder")
    op.drop_column("movies", "scraping_status")
