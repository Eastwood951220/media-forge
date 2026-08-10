"""add crawler agents

Revision ID: 20260810_0001
Revises: 20260727_0001
Create Date: 2026-08-10 00:00:00.000000
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260810_0001"
down_revision = "20260727_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawler_agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default="Chrome Agent"),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="offline"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cookie_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_crawler_agents_owner_status", "crawler_agents", ["owner_id", "status"])
    op.create_index("idx_crawler_agents_last_seen", "crawler_agents", ["last_seen_at"])
    op.create_index(op.f("ix_crawler_agents_owner_id"), "crawler_agents", ["owner_id"])
    op.create_index(op.f("ix_crawler_agents_status"), "crawler_agents", ["status"])

    op.create_table(
        "crawler_agent_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["crawler_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_crawler_agent_sessions_session", "crawler_agent_sessions", ["session_id"], unique=True)
    op.create_index("idx_crawler_agent_sessions_expires", "crawler_agent_sessions", ["expires_at"])
    op.create_index(op.f("ix_crawler_agent_sessions_agent_id"), "crawler_agent_sessions", ["agent_id"])
    op.create_index(op.f("ix_crawler_agent_sessions_owner_id"), "crawler_agent_sessions", ["owner_id"])

    op.create_table(
        "crawler_agent_work_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("detail_task_id", sa.Uuid(), nullable=True),
        sa.Column("url_entry_id", sa.Uuid(), nullable=True),
        sa.Column("page_kind", sa.String(20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assigned_agent_id", sa.Uuid(), nullable=True),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_reason", sa.String(100), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["crawler_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["detail_task_id"], ["crawl_run_detail_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["crawl_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["url_entry_id"], ["crawl_task_urls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_crawler_agent_work_claim", "crawler_agent_work_items", ["owner_id", "status", "claimed_until"])
    op.create_index("idx_crawler_agent_work_run_status", "crawler_agent_work_items", ["run_id", "status"])
    op.create_index("idx_crawler_agent_work_detail", "crawler_agent_work_items", ["detail_task_id"])
    op.create_index(op.f("ix_crawler_agent_work_items_assigned_agent_id"), "crawler_agent_work_items", ["assigned_agent_id"])
    op.create_index(op.f("ix_crawler_agent_work_items_detail_task_id"), "crawler_agent_work_items", ["detail_task_id"])
    op.create_index(op.f("ix_crawler_agent_work_items_owner_id"), "crawler_agent_work_items", ["owner_id"])
    op.create_index(op.f("ix_crawler_agent_work_items_run_id"), "crawler_agent_work_items", ["run_id"])
    op.create_index(op.f("ix_crawler_agent_work_items_status"), "crawler_agent_work_items", ["status"])
    op.create_index(op.f("ix_crawler_agent_work_items_task_id"), "crawler_agent_work_items", ["task_id"])
    op.create_index(op.f("ix_crawler_agent_work_items_url_entry_id"), "crawler_agent_work_items", ["url_entry_id"])


def downgrade() -> None:
    op.drop_table("crawler_agent_work_items")
    op.drop_table("crawler_agent_sessions")
    op.drop_table("crawler_agents")
