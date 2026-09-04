"""add crawler schedules

Revision ID: 20260904_0003
Revises: 20260904_0002
Create Date: 2026-09-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260904_0003"
down_revision = "20260904_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- crawler_schedules --
    op.create_table(
        "crawler_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("schedule_type", sa.String(length=20), nullable=False),
        sa.Column("time_of_day", sa.String(length=5), nullable=False),
        sa.Column("weekdays", postgresql.JSONB(), nullable=False),
        sa.Column("auto_storage_enabled", sa.Boolean(), nullable=False),
        sa.Column("storage_mode", sa.String(length=30), nullable=False),
        sa.Column("selected_storage_location", sa.String(length=500), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_crawler_schedules_owner_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_crawler_schedules"),
        sa.UniqueConstraint("owner_id", "name", name="uq_crawler_schedules_owner_name"),
    )
    op.create_index("idx_crawler_schedules_owner_enabled", "crawler_schedules", ["owner_id", "enabled"])
    op.create_index("idx_crawler_schedules_next_run", "crawler_schedules", ["enabled", "next_run_at"])
    op.create_index(op.f("ix_crawler_schedules_owner_id"), "crawler_schedules", ["owner_id"])

    # -- crawler_schedule_tasks --
    op.create_table(
        "crawler_schedule_tasks",
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["schedule_id"],
            ["crawler_schedules.id"],
            name="fk_crawler_schedule_tasks_schedule_id_crawler_schedules",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["crawl_tasks.id"],
            name="fk_crawler_schedule_tasks_task_id_crawl_tasks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("schedule_id", "task_id", name="pk_crawler_schedule_tasks"),
        sa.UniqueConstraint("schedule_id", "task_id", name="uq_crawler_schedule_tasks_schedule_task"),
    )
    op.create_index("idx_crawler_schedule_tasks_schedule_id", "crawler_schedule_tasks", ["schedule_id"])
    op.create_index("idx_crawler_schedule_tasks_task_id", "crawler_schedule_tasks", ["task_id"])

    # -- crawler_schedule_runs --
    op.create_table(
        "crawler_schedule_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("storage_status", sa.String(length=30), nullable=False),
        sa.Column("storage_task_id", sa.Uuid(), nullable=True),
        sa.Column("storage_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["schedule_id"],
            ["crawler_schedules.id"],
            name="fk_crawler_schedule_runs_schedule_id_crawler_schedules",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_crawler_schedule_runs_owner_id_users"),
        sa.ForeignKeyConstraint(
            ["storage_task_id"],
            ["storage_main_tasks.id"],
            name="fk_crawler_schedule_runs_storage_task_id_storage_main_tasks",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crawler_schedule_runs"),
    )
    op.create_index(
        "idx_crawler_schedule_runs_schedule_triggered",
        "crawler_schedule_runs",
        ["schedule_id", "triggered_at"],
    )
    op.create_index("idx_crawler_schedule_runs_owner_status", "crawler_schedule_runs", ["owner_id", "status"])
    op.create_index(op.f("ix_crawler_schedule_runs_schedule_id"), "crawler_schedule_runs", ["schedule_id"])
    op.create_index(op.f("ix_crawler_schedule_runs_owner_id"), "crawler_schedule_runs", ["owner_id"])

    # -- crawler_schedule_run_crawl_runs --
    op.create_table(
        "crawler_schedule_run_crawl_runs",
        sa.Column("schedule_run_id", sa.Uuid(), nullable=False),
        sa.Column("crawl_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["schedule_run_id"],
            ["crawler_schedule_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["crawl_run_id"],
            ["crawl_runs.id"],
            name="fk_crawler_schedule_run_crawl_runs_crawl_run_id_crawl_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["crawl_tasks.id"],
            name="fk_crawler_schedule_run_crawl_runs_task_id_crawl_tasks",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("schedule_run_id", "crawl_run_id", name="pk_crawler_schedule_run_crawl_runs"),
        sa.UniqueConstraint(
            "schedule_run_id",
            "crawl_run_id",
            name="uq_crawler_schedule_run_crawl_run",
        ),
    )
    op.create_index(
        "idx_crawler_schedule_run_crawl_runs_schedule_run",
        "crawler_schedule_run_crawl_runs",
        ["schedule_run_id"],
    )
    op.create_index(
        "idx_crawler_schedule_run_crawl_runs_crawl_run",
        "crawler_schedule_run_crawl_runs",
        ["crawl_run_id"],
    )

    # -- crawl_runs: schedule link columns --
    op.add_column(
        "crawl_runs",
        sa.Column("trigger_source", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("schedule_run_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_crawl_runs_schedule_id_crawler_schedules",
        "crawl_runs",
        "crawler_schedules",
        ["schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_crawl_runs_schedule_run_id_crawler_schedule_runs",
        "crawl_runs",
        "crawler_schedule_runs",
        ["schedule_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_crawl_runs_trigger_source"), "crawl_runs", ["trigger_source"])
    op.create_index(op.f("ix_crawl_runs_schedule_id"), "crawl_runs", ["schedule_id"])
    op.create_index(op.f("ix_crawl_runs_schedule_run_id"), "crawl_runs", ["schedule_run_id"])

    # -- crawl_run_detail_tasks: saved movie link --
    op.add_column(
        "crawl_run_detail_tasks",
        sa.Column("movie_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_crawl_run_detail_tasks_movie_id_movies",
        "crawl_run_detail_tasks",
        "movies",
        ["movie_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_crawl_run_detail_tasks_movie_id"), "crawl_run_detail_tasks", ["movie_id"])


def downgrade() -> None:
    # crawl_run_detail_tasks: drop index/constraint before the column
    op.drop_index(op.f("ix_crawl_run_detail_tasks_movie_id"), table_name="crawl_run_detail_tasks")
    op.drop_constraint("fk_crawl_run_detail_tasks_movie_id_movies", "crawl_run_detail_tasks", type_="foreignkey")
    op.drop_column("crawl_run_detail_tasks", "movie_id")

    # crawl_runs: drop indexes/constraints before the columns
    op.drop_index(op.f("ix_crawl_runs_trigger_source"), table_name="crawl_runs")
    op.drop_index(op.f("ix_crawl_runs_schedule_id"), table_name="crawl_runs")
    op.drop_index(op.f("ix_crawl_runs_schedule_run_id"), table_name="crawl_runs")
    op.drop_constraint("fk_crawl_runs_schedule_id_crawler_schedules", "crawl_runs", type_="foreignkey")
    op.drop_constraint("fk_crawl_runs_schedule_run_id_crawler_schedule_runs", "crawl_runs", type_="foreignkey")
    op.drop_column("crawl_runs", "trigger_source")
    op.drop_column("crawl_runs", "schedule_id")
    op.drop_column("crawl_runs", "schedule_run_id")

    # Drop the new tables in reverse dependency order.
    op.drop_table("crawler_schedule_run_crawl_runs")
    op.drop_table("crawler_schedule_runs")
    op.drop_table("crawler_schedule_tasks")
    op.drop_table("crawler_schedules")
