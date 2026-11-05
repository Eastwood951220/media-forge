from typing import Any

from sqlalchemy import Boolean, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApplicationSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'application_settings'
    __table_args__ = (UniqueConstraint('namespace', 'key', name='uq_application_settings_namespace_key'),)

    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Any] = mapped_column(JSON().with_variant(JSONB(), 'postgresql'), nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
