from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.models.base import Base


class JellyfinSyncState(Base):
    __tablename__ = "jellyfin_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="never")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
