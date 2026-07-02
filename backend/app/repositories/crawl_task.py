import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import CrawlTask
from backend.app.repositories.base import BaseRepository


class CrawlTaskRepository(BaseRepository):
    """Repository for CrawlTask model operations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlTask)

    def get_by_task_id(self, task_id: str) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .filter(CrawlTask.task_id == task_id)
            .first()
        )

    def _owner_query(self, owner_id: uuid.UUID, keyword: str | None = None):
        query = self.session.query(CrawlTask).filter(CrawlTask.owner_id == owner_id)
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            query = query.filter(CrawlTask.name.ilike(f"%{normalized_keyword}%"))
        return query

    def get_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
        keyword: str | None = None,
    ) -> list[CrawlTask]:
        return (
            self._owner_query(owner_id, keyword)
            .order_by(CrawlTask.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_owner(self, owner_id: uuid.UUID, keyword: str | None = None) -> int:
        return (
            self._owner_query(owner_id, keyword)
            .with_entities(func.count(CrawlTask.id))
            .scalar()
            or 0
        )

    def get_owned(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id)
            .first()
        )
