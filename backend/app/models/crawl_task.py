import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrawlTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_tasks"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_crawl_tasks_owner_name"),
        Index("idx_crawl_tasks_owner_created_at", "owner_id", "created_at"),
        Index("idx_crawl_tasks_owner_skip", "owner_id", "is_skip"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    task_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    celery_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_qualified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    urls: Mapped[list["CrawlTaskUrl"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="CrawlTaskUrl.position",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<CrawlTask(id={self.id}, name={self.name}, urls={len(self.urls)})>"


class CrawlTaskUrl(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawl_task_urls"
    __table_args__ = (
        UniqueConstraint("task_id", "url", name="uq_crawl_task_urls_task_url"),
        Index("idx_crawl_task_urls_task_position", "task_id", "position"),
        Index("idx_crawl_task_urls_source", "source"),
        Index("idx_crawl_task_urls_url_type", "url_type"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_type: Mapped[str] = mapped_column(String(50), nullable=False)
    has_magnet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_chinese_sub: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    final_url: Mapped[str] = mapped_column(Text, nullable=False)
    url_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    task: Mapped[CrawlTask] = relationship(back_populates="urls")
