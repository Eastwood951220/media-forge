from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """Repository for User model operations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_username(self, username: str) -> User | None:
        return self.session.query(User).filter(User.username == username).first()

    def username_exists(self, username: str) -> bool:
        return (
            self.session.query(User).filter(User.username == username).first()
            is not None
        )
