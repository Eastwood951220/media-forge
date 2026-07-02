from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import Movie
from shared.database.session import get_session_factory
from scraper.config.logging import get_logger


class MovieRepository:
    def __init__(self, session: Session | None = None):
        self.logger = get_logger("movie_repository")
        self._session = session
        self.available = True

    def _session_scope(self):
        return self._session or get_session_factory()()

    def get_collection(self):
        """Compatibility method - not used in PostgreSQL implementation."""
        return None

    def insert_if_not_exists(
        self,
        document: dict,
        unique_field: str = "code",
    ) -> UUID | None:
        if not self.available:
            return None

        close_session = self._session is None
        session = self._session_scope()
        try:
            # Check if exists
            value = document.get(unique_field)
            if not value:
                return None

            if unique_field == "code":
                existing = session.scalar(select(Movie).where(Movie.code == value))
            else:
                existing = session.scalar(select(Movie).where(Movie.source_url == value))

            if existing:
                return existing.id

            # Create new movie
            now = datetime.now(timezone.utc)
            movie = Movie(
                code=document.get("code"),
                source_url=document.get("source_url"),
                source_name=document.get("source_name", ""),
                release_date=document.get("release_date"),
                duration=document.get("duration", 0),
                director=document.get("director", ""),
                maker=document.get("maker", ""),
                series=document.get("series", ""),
                rating=document.get("rating"),
                actors=document.get("actors", []),
                tags=document.get("tags", []),
                source_task_names=document.get("source_task_name", []),
                source_task_id=document.get("source_task_id"),
                cover=document.get("cover", ""),
                marked=document.get("marked", False),
                storage_summary=document.get("storage_summary", {}),
                raw_detail=document.get("raw_detail", {}),
            )
            session.add(movie)
            session.commit()
            return movie.id
        except Exception as exc:
            session.rollback()
            self.available = False
            self.logger.warning("Failed to insert movie: %s", exc)
            return None
        finally:
            if close_session:
                session.close()

    def add_source_task_name(self, code: str, task_name: str) -> tuple[bool, list[str]]:
        """Add a task name to an existing movie's source_task_name list."""
        if not self.available or not code:
            return False, []

        close_session = self._session is None
        session = self._session_scope()
        try:
            movie = session.scalar(select(Movie).where(Movie.code == code))
            if not movie:
                return False, []

            previous_names = list(movie.source_task_names or [])
            if task_name not in previous_names:
                movie.source_task_names = previous_names + [task_name]
                session.commit()
                return True, previous_names
            return False, previous_names
        except Exception as exc:
            session.rollback()
            self.logger.warning("Failed to add source_task_name: %s", exc)
            return False, []
        finally:
            if close_session:
                session.close()

    def upsert_movie(self, item: dict) -> UUID | None:
        if not self.available:
            return None

        code = item.get("code")
        unique_field = "code" if code else "source_url"

        return self.insert_if_not_exists(
            document=item,
            unique_field=unique_field,
        )
