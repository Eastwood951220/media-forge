import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.types import CompatibleARRAY, CompatibleJSON


class Movie(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "movies"
    __table_args__ = (
        Index("idx_movies_code", "code"),
        Index("idx_movies_source_url", "source_url"),
        Index("idx_movies_created_at", "created_at"),
        Index("idx_movies_updated_at", "updated_at"),
        Index("idx_movies_release_date", "release_date"),
        Index("idx_movies_rating", "rating"),
        Index("idx_movies_source_task_id", "source_task_id"),
        Index("idx_movies_actors_gin", "actors", postgresql_using="gin"),
        Index("idx_movies_tags_gin", "tags", postgresql_using="gin"),
        Index("idx_movies_source_task_names_gin", "source_task_names", postgresql_using="gin"),
        Index("idx_movies_storage_summary_gin", "storage_summary", postgresql_using="gin"),
        UniqueConstraint("code", name="uq_movies_code"),
        UniqueConstraint("source_url", name="uq_movies_source_url"),
    )

    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    director: Mapped[str] = mapped_column(Text, nullable=False, default="")
    maker: Mapped[str] = mapped_column(Text, nullable=False, default="")
    series: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    actors: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    source_task_names: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cover: Mapped[str] = mapped_column(Text, nullable=False, default="")
    marked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_summary: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    raw_detail: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)

    magnets: Mapped[list["MovieMagnet"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MovieMagnet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "movie_magnets"
    __table_args__ = (
        UniqueConstraint("movie_id", "dedupe_key", name="uq_movie_magnets_movie_dedupe"),
        Index("idx_movie_magnets_movie_id", "movie_id"),
        Index("idx_movie_magnets_info_hash", "info_hash"),
        Index("idx_movie_magnets_quality", "has_chinese_sub", "size_mb"),
    )

    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    magnet_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    info_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    size_mb: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    size_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    has_chinese_sub: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_data: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)

    movie: Mapped[Movie] = relationship(back_populates="magnets")


class MovieFilter(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "movie_filters"
    __table_args__ = (
        UniqueConstraint("type", "name", name="uq_movie_filters_type_name"),
        Index("idx_movie_filters_type", "type"),
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
