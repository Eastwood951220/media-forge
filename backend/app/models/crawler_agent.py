import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

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
    error_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
