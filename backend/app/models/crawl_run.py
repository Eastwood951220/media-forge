import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class CrawlRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_runs"
    __table_args__ = (
        Index("idx_crawl_runs_task_status", "task_id", "status"),
        Index("idx_crawl_runs_queued_at", "queued_at"),
        Index("idx_crawl_runs_resumed_from", "resumed_from"),
    )

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    crawl_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="incremental")
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumed_from: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    detail_tasks: Mapped[list["CrawlRunDetailTask"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="CrawlRunDetailTask.created_at",
        lazy="selectin",
    )


class CrawlRunDetailTask(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "crawl_run_detail_tasks"
    __table_args__ = (
        Index("idx_crawl_detail_run_status", "run_id", "status"),
        Index("idx_crawl_detail_run_source", "run_id", "source_url"),
        Index("idx_crawl_detail_created_at", "created_at"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    task_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_url_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_data: Mapped[dict | None] = mapped_column(CompatibleJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    crawled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    saved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    run: Mapped[CrawlRun] = relationship(back_populates="detail_tasks")
