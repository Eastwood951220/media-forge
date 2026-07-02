import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrawlTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_tasks"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    target_websites: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    schedule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    crawl_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    celery_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    total_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_qualified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<CrawlTask(id={self.id}, name={self.name}, status={self.status})>"
