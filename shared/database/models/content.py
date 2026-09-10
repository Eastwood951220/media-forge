import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
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
        Index("idx_movies_source_task_ids_gin", "source_task_ids", postgresql_using="gin"),
        Index("idx_movies_source_task_url_ids_gin", "source_task_url_ids", postgresql_using="gin"),
        Index("idx_movies_actors_gin", "actors", postgresql_using="gin"),
        Index("idx_movies_tags_gin", "tags", postgresql_using="gin"),
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
    source_task_ids: Mapped[list[uuid.UUID]] = mapped_column(CompatibleARRAY(Uuid), nullable=False, default=list)
    source_task_url_ids: Mapped[list[uuid.UUID]] = mapped_column(CompatibleARRAY(Uuid), nullable=False, default=list)
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


actress_tag_links = Table(
    "actress_tag_links",
    Base.metadata,
    Column("actress_profile_id", ForeignKey("actress_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("actress_tags.id", ondelete="CASCADE"), primary_key=True),
    Index("idx_actress_tag_links_profile_id", "actress_profile_id"),
    Index("idx_actress_tag_links_tag_id", "tag_id"),
)


class ActressTag(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "actress_tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_actress_tags_owner_name"),
        Index("idx_actress_tags_owner_name", "owner_id", "name"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    profiles: Mapped[list["ActressProfile"]] = relationship(
        secondary=actress_tag_links,
        back_populates="tags",
        lazy="select",
    )


class ActressProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "actress_profiles"
    __table_args__ = (
        Index("idx_actress_profiles_display_name", "display_name"),
        Index("idx_actress_profiles_source_url", "source_url"),
        Index("idx_actress_profiles_source_task_ids_gin", "source_task_ids", postgresql_using="gin"),
        Index("idx_actress_profiles_aliases_gin", "aliases", postgresql_using="gin"),
        Index("idx_actress_profiles_canonical_names_gin", "canonical_names", postgresql_using="gin"),
        UniqueConstraint("source_url", name="uq_actress_profiles_source_url"),
    )

    display_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reading: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aliases: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    canonical_names: Mapped[list[str]] = mapped_column(CompatibleARRAY(Text), nullable=False, default=list)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_site: Mapped[str] = mapped_column(Text, nullable=False, default="avjoho")
    source_task_ids: Mapped[list[uuid.UUID]] = mapped_column(CompatibleARRAY(Uuid), nullable=False, default=list)
    source_task_url_ids: Mapped[list[uuid.UUID]] = mapped_column(CompatibleARRAY(Uuid), nullable=False, default=list)
    tags: Mapped[list[ActressTag]] = relationship(
        secondary=actress_tag_links,
        back_populates="profiles",
        order_by="ActressTag.name",
        lazy="selectin",
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    debut_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bust_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waist_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hip_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cup: Mapped[str] = mapped_column(Text, nullable=False, default="")
    birthplace: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blood_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hobbies: Mapped[str] = mapped_column(Text, nullable=False, default="")
    biography: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exclusive_maker: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sns_links: Mapped[list[dict]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    representative_works: Mapped[list[dict]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    similar_actresses: Mapped[list[dict]] = mapped_column(CompatibleJSON, nullable=False, default=list)
    raw_profile: Mapped[dict] = mapped_column(CompatibleJSON, nullable=False, default=dict)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
