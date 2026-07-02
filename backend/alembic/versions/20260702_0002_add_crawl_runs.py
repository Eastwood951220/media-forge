"""add crawl_runs, crawl_run_detail_tasks, movies, movie_magnets, movie_filters

Revision ID: 20260702_0002
Revises: 20260702_0001
Create Date: 2026-07-02 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260702_0002"
down_revision = "20260702_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- crawl_runs --
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("task_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("crawl_mode", sa.String(length=50), nullable=False, server_default="incremental"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("resumed_from", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["crawl_tasks.id"],
            name="fk_crawl_runs_task_id_crawl_tasks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resumed_from"],
            ["crawl_runs.id"],
            name="fk_crawl_runs_resumed_from_crawl_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_runs"),
    )
    op.create_index("ix_crawl_runs_task_id", "crawl_runs", ["task_id"])
    op.create_index("ix_crawl_runs_status", "crawl_runs", ["status"])
    op.create_index("idx_crawl_runs_task_status", "crawl_runs", ["task_id", "status"])
    op.create_index("idx_crawl_runs_queued_at", "crawl_runs", ["queued_at"])
    op.create_index("idx_crawl_runs_resumed_from", "crawl_runs", ["resumed_from"])

    # -- crawl_run_detail_tasks --
    op.create_table(
        "crawl_run_detail_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("code", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("item_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["crawl_runs.id"],
            name="fk_crawl_run_detail_tasks_run_id_crawl_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_run_detail_tasks"),
    )
    op.create_index("ix_crawl_run_detail_tasks_run_id", "crawl_run_detail_tasks", ["run_id"])
    op.create_index("ix_crawl_run_detail_tasks_code", "crawl_run_detail_tasks", ["code"])
    op.create_index("ix_crawl_run_detail_tasks_status", "crawl_run_detail_tasks", ["status"])
    op.create_index("idx_crawl_detail_run_status", "crawl_run_detail_tasks", ["run_id", "status"])
    op.create_index("idx_crawl_detail_run_source", "crawl_run_detail_tasks", ["run_id", "source_url"])
    op.create_index("idx_crawl_detail_created_at", "crawl_run_detail_tasks", ["created_at"])

    # -- movies --
    op.create_table(
        "movies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("director", sa.Text(), nullable=False, server_default=""),
        sa.Column("maker", sa.Text(), nullable=False, server_default=""),
        sa.Column("series", sa.Text(), nullable=False, server_default=""),
        sa.Column("rating", sa.Numeric(3, 1), nullable=True),
        sa.Column("actors", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("source_task_names", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("cover", sa.Text(), nullable=False, server_default=""),
        sa.Column("marked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("storage_summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id", name="pk_movies"),
        sa.UniqueConstraint("code", name="uq_movies_code"),
        sa.UniqueConstraint("source_url", name="uq_movies_source_url"),
    )
    op.create_index("idx_movies_code", "movies", ["code"])
    op.create_index("idx_movies_source_url", "movies", ["source_url"])
    op.create_index("idx_movies_created_at", "movies", ["created_at"])
    op.create_index("idx_movies_updated_at", "movies", ["updated_at"])
    op.create_index("idx_movies_release_date", "movies", ["release_date"])
    op.create_index("idx_movies_rating", "movies", ["rating"])
    op.create_index("idx_movies_actors_gin", "movies", ["actors"], postgresql_using="gin")
    op.create_index("idx_movies_tags_gin", "movies", ["tags"], postgresql_using="gin")
    op.create_index("idx_movies_source_task_names_gin", "movies", ["source_task_names"], postgresql_using="gin")
    op.create_index("idx_movies_storage_summary_gin", "movies", ["storage_summary"], postgresql_using="gin")

    # -- movie_magnets --
    op.create_table(
        "movie_magnets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("magnet_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("info_hash", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("size_mb", sa.Numeric(), nullable=True),
        sa.Column("size_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("file_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("has_chinese_sub", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("date", sa.Text(), nullable=False, server_default=""),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("raw_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            name="fk_movie_magnets_movie_id_movies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_movie_magnets"),
        sa.UniqueConstraint("movie_id", "dedupe_key", name="uq_movie_magnets_movie_dedupe"),
    )
    op.create_index("idx_movie_magnets_movie_id", "movie_magnets", ["movie_id"])
    op.create_index("idx_movie_magnets_info_hash", "movie_magnets", ["info_hash"])
    op.create_index("idx_movie_magnets_quality", "movie_magnets", ["has_chinese_sub", "size_mb"])

    # -- movie_filters --
    op.create_table(
        "movie_filters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_movie_filters"),
        sa.UniqueConstraint("type", "name", name="uq_movie_filters_type_name"),
    )
    op.create_index("idx_movie_filters_type", "movie_filters", ["type"])


def downgrade() -> None:
    op.drop_table("movie_filters")
    op.drop_table("movie_magnets")
    op.drop_table("movies")
    op.drop_table("crawl_run_detail_tasks")
    op.drop_table("crawl_runs")
