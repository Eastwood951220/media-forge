"""Add crawler agent diagnostics columns and events table

Revision ID: 20260817_0001
Revises: 20260810_0001
Create Date: 2026-08-17 00:00:00.000000
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260817_0001"
down_revision = "20260810_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add columns to crawler_agents
    op.add_column(
        "crawler_agents",
        sa.Column("protocol_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "crawler_agents",
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Add phase timestamp columns to crawler_agent_work_items
    op.add_column(
        "crawler_agent_work_items",
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "crawler_agent_work_items",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "crawler_agent_work_items",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "crawler_agent_work_items",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create crawler_agent_events table
    op.create_table(
        "crawler_agent_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("work_item_id", sa.Uuid(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("phase", sa.String(100), nullable=True),
        sa.Column("level", sa.String(20), nullable=False, server_default="info"),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("details_json", postgresql.JSONB(), nullable=True),
        sa.Column("retention_class", sa.String(520), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["crawler_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["crawler_agent_work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_crawler_agent_events_owner_created",
        "crawler_agent_events",
        ["owner_id", "created_at"],
    )
    op.create_index(
        "idx_crawler_agent_events_agent_created",
        "crawler_agent_events",
        ["agent_id", "created_at"],
    )
    op.create_index(
        "idx_crawler_agent_events_run_created",
        "crawler_agent_events",
        ["run_id", "created_at"],
    )
    op.create_index(
        "idx_crawler_agent_events_work_created",
        "crawler_agent_events",
        ["work_item_id", "created_at"],
    )
    op.create_index(
        "idx_crawler_agent_events_retention_created",
        "crawler_agent_events",
        ["retention_class", "created_at"],
    )
    op.create_index(
        op.f("ix_crawler_agent_events_owner_id"),
        "crawler_agent_events",
        ["owner_id"],
    )
    op.create_index(
        op.f("ix_crawler_agent_events_agent_id"),
        "crawler_agent_events",
        ["agent_id"],
    )
    op.create_index(
        op.f("ix_crawler_agent_events_run_id"),
        "crawler_agent_events",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_crawler_agent_events_work_item_id"),
        "crawler_agent_events",
        ["work_item_id"],
    )
    op.create_index(
        op.f("ix_crawler_agent_events_event_type"),
        "crawler_agent_events",
        ["event_type"],
    )
    op.create_index(
        op.f("ix_crawler_agent_events_retention_class"),
        "crawler_agent_events",
        ["retention_class"],
    )


def downgrade() -> None:
    op.drop_table("crawler_agent_events")
    op.drop_column("crawler_agent_work_items", "finished_at")
    op.drop_column("crawler_agent_work_items", "started_at")
    op.drop_column("crawler_agent_work_items", "assigned_at")
    op.drop_column("crawler_agent_work_items", "queued_at")
    op.drop_column("crawler_agents", "connected_at")
    op.drop_column("crawler_agents", "protocol_version")