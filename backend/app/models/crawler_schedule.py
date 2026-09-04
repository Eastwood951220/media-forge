import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class CrawlerSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_schedules"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_crawler_schedules_owner_name"),
        Index("idx_crawler_schedules_owner_enabled", "owner_id", "enabled"),
        Index("idx_crawler_schedules_next_run", "enabled", "next_run_at"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(5), nullable=False)
    weekdays: Mapped[list[int]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    auto_storage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="single")
    selected_storage_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tasks: Mapped[list["CrawlTask"]] = relationship(
        secondary="crawler_schedule_tasks",
        lazy="selectin",
    )
    runs: Mapped[list["CrawlerScheduleRun"]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="CrawlerScheduleRun.triggered_at.desc()",
        lazy="selectin",
    )


class CrawlerScheduleTask(Base):
    __tablename__ = "crawler_schedule_tasks"
    __table_args__ = (
        UniqueConstraint("schedule_id", "task_id", name="uq_crawler_schedule_tasks_schedule_task"),
        Index("idx_crawler_schedule_tasks_schedule_id", "schedule_id"),
        Index("idx_crawler_schedule_tasks_task_id", "task_id"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawler_schedules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class CrawlerScheduleRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "crawler_schedule_runs"
    __table_args__ = (
        Index("idx_crawler_schedule_runs_schedule_triggered", "schedule_id", "triggered_at"),
        Index("idx_crawler_schedule_runs_owner_status", "owner_id", "status"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawler_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    storage_status: Mapped[str] = mapped_column(String(30), nullable=False, default="disabled")
    storage_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("storage_main_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    storage_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    schedule: Mapped[CrawlerSchedule] = relationship(back_populates="runs")
    crawl_run_links: Mapped[list["CrawlerScheduleRunCrawlRun"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CrawlerScheduleRunCrawlRun(Base):
    __tablename__ = "crawler_schedule_run_crawl_runs"
    __table_args__ = (
        UniqueConstraint("schedule_run_id", "crawl_run_id", name="uq_crawler_schedule_run_crawl_run"),
        Index("idx_crawler_schedule_run_crawl_runs_schedule_run", "schedule_run_id"),
        Index("idx_crawler_schedule_run_crawl_runs_crawl_run", "crawl_run_id"),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawler_schedule_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crawl_tasks.id", ondelete="SET NULL"), nullable=True)

    schedule_run: Mapped[CrawlerScheduleRun] = relationship(back_populates="crawl_run_links")
    crawl_run: Mapped["CrawlRun"] = relationship(lazy="joined")
