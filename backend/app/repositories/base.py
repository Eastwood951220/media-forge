from typing import TypeVar

from sqlalchemy.orm import Session

from shared.database.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository:
    """Generic base repository for SQLAlchemy models."""

    def __init__(self, session: Session, model: type[Base]) -> None:
        self.session = session
        self.model = model

    def get_by_id(self, id: str) -> Base | None:
        return self.session.get(self.model, id)

    def get_all(self, *, skip: int = 0, limit: int = 100) -> list[Base]:
        return (
            self.session.query(self.model)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create(self, obj: Base) -> Base:
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def update(self, obj: Base) -> Base:
        self.session.merge(obj)
        self.session.commit()
        return obj

    def delete(self, obj: Base) -> None:
        self.session.delete(obj)
        self.session.commit()
