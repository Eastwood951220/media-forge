import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class ScrapingTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scraping_tasks"
    __table_args__ = (
        Index("idx_scraping_tasks_status_created", "status", "created_at"),
        Index("idx_scraping_tasks_created_by_status", "created_by", "status"),
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_snapshot: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["ScrapingTaskItem"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ScrapingTaskItem.created_at",
        lazy="selectin",
    )


class ScrapingTaskItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scraping_task_items"
    __table_args__ = (
        Index("idx_scraping_items_task_status", "task_id", "status"),
        Index("idx_scraping_items_created", "created_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scraping_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    movie_code: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    movie_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    folder: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped[ScrapingTask] = relationship(back_populates="items")
