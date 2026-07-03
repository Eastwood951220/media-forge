import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleJSON


class StorageMainTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "storage_main_tasks"
    __table_args__ = (
        Index("idx_storage_main_status_created", "status", "created_at"),
        Index("idx_storage_main_created_by_status", "created_by", "status"),
    )

    alias: Mapped[str] = mapped_column(String(240), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_snapshot: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtasks: Mapped[list["StorageSubTask"]] = relationship(
        back_populates="main_task",
        cascade="all, delete-orphan",
        order_by="StorageSubTask.created_at",
        lazy="selectin",
    )


class StorageSubTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "storage_sub_tasks"
    __table_args__ = (
        Index("idx_storage_sub_main_status", "main_task_id", "status"),
        Index("idx_storage_sub_movie_status", "movie_id", "status"),
        Index("idx_storage_sub_created", "created_at"),
    )

    main_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("storage_main_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    movie_code: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    movie_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(50), nullable=False, default="prepare")
    storage_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_storage_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_locations: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    download_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_paths: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    magnet_attempts: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    current_magnet_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    current_magnet_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    renamed_files: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    moved_files: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    skipped_files: Mapped[list] = mapped_column(CompatibleJSON, nullable=False, default=list)
    result: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    skip_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    main_task: Mapped[StorageMainTask] = relationship(back_populates="subtasks")
