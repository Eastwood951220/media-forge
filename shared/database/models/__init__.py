"""SQLAlchemy models shared across backend and other packages."""

from shared.database.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.database.models.content import Movie, MovieFilter, MovieMagnet

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "Movie",
    "MovieMagnet",
    "MovieFilter",
]
