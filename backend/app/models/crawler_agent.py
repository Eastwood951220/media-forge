import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class CrawlerAgent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_agents"
    __table_args__ = (
        Index("idx_crawler_agents_owner_status", "owner_id", "status"),
        Index("idx_crawler_agents_last_seen", "last_seen_at"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Chrome Agent")
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="offline", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_cookie_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    protocol_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)


class CrawlerAgentSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_agent_sessions"
    __table_args__ = (
        Index("idx_crawler_agent_sessions_session", "session_id", unique=True),
        Index("idx_crawler_agent_sessions_expires", "expires_at"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawler_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CrawlerAgentWorkItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_agent_work_items"
    __table_args__ = (
        Index("idx_crawler_agent_work_claim", "owner_id", "status", "claimed_until"),
        Index("idx_crawler_agent_work_run_status", "run_id", "status"),
        Index("idx_crawler_agent_work_detail", "detail_task_id"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    detail_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_run_detail_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    url_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_task_urls.id", ondelete="SET NULL"), nullable=True, index=True)
    page_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawler_agents.id", ondelete="SET NULL"), nullable=True, index=True)
    claimed_until: Mapped[datetime | None] = mapped_column(nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)


class CrawlerAgentEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "crawler_agent_events"
    __table_args__ = (
        Index("idx_crawler_agent_events_owner_created", "owner_id", "created_at"),
        Index("idx_crawler_agent_events_agent_created", "agent_id", "created_at"),
        Index("idx_crawler_agent_events_run_created", "run_id", "created_at"),
        Index("idx_crawler_agent_events_work_created", "work_item_id", "created_at"),
        Index("idx_crawler_agent_events_retention_created", "retention_class", "created_at"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawler_agents.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawler_agent_work_items.id", ondelete="CASCADE"), nullable=True, index=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    phase: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    details_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    retention_class: Mapped[str] = mapped_column(String(520), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
