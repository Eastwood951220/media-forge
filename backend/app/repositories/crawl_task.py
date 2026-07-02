import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend.app.models.crawl_task import CrawlRun, CrawlTask, CrawlTaskUrl
from backend.app.models.enums import CrawlRunStatus, TaskStatus
from backend.app.repositories.base import BaseRepository
from backend.app.schemas.crawl_task import TaskUrlEntryCreate
from scraper.tasks.task_utils import build_final_url, determine_source


class CrawlTaskRepository(BaseRepository):
    """Repository for CrawlTask model operations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlTask)

    def _owner_query(self, owner_id: uuid.UUID, keyword: str | None = None):
        query = (
            self.session.query(CrawlTask)
            .options(selectinload(CrawlTask.urls))
            .filter(CrawlTask.owner_id == owner_id)
        )
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
        query = self.session.query(CrawlTask).filter(CrawlTask.owner_id == owner_id)
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            query = query.filter(CrawlTask.name.ilike(f"%{normalized_keyword}%"))
        return query.with_entities(func.count(CrawlTask.id)).scalar() or 0

    def get_owned(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .options(selectinload(CrawlTask.urls))
            .filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id)
            .first()
        )

    def get_by_name(self, owner_id: uuid.UUID, name: str) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .filter(CrawlTask.owner_id == owner_id, CrawlTask.name == name)
            .first()
        )

    def build_url_values(self, entry: TaskUrlEntryCreate, position: int) -> dict:
        source = determine_source(entry.url)
        final_url = build_final_url(
            url=entry.url,
            url_type=entry.url_type,
            has_magnet=entry.has_magnet,
            has_chinese_sub=entry.has_chinese_sub,
            sort_type=entry.sort_type,
            source=source,
        )
        return {
            "position": position,
            "url": entry.url,
            "url_type": entry.url_type,
            "has_magnet": entry.has_magnet,
            "has_chinese_sub": entry.has_chinese_sub,
            "sort_type": entry.sort_type,
            "source": source,
            "final_url": entry.final_url or final_url,
            "url_name": entry.url_name,
        }

    def build_url_rows(self, entries: list[TaskUrlEntryCreate]) -> list[CrawlTaskUrl]:
        return [
            CrawlTaskUrl(**self.build_url_values(entry, position))
            for position, entry in enumerate(entries)
        ]

    def create_with_urls(
        self,
        *,
        owner_id: uuid.UUID,
        name: str,
        is_skip: bool,
        urls: list[TaskUrlEntryCreate],
    ) -> CrawlTask:
        task = CrawlTask(name=name, is_skip=is_skip, owner_id=owner_id)
        task.urls = self.build_url_rows(urls)
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return self.get_owned(task.id, owner_id) or task

    def replace_urls(self, task: CrawlTask, urls: list[TaskUrlEntryCreate]) -> None:
        existing_by_url = {row.url: row for row in task.urls}
        next_rows: list[CrawlTaskUrl] = []

        for position, entry in enumerate(urls):
            values = self.build_url_values(entry, position)
            row = existing_by_url.pop(entry.url, None)
            if row is None:
                row = CrawlTaskUrl(**values)
            else:
                for field, value in values.items():
                    setattr(row, field, value)
            next_rows.append(row)

        task.urls = next_rows

    # -- Status queries for movie list --

    def get_by_status(
        self,
        owner_id: uuid.UUID,
        *,
        task_status: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[CrawlTask]:
        return (
            self.session.query(CrawlTask)
            .options(selectinload(CrawlTask.urls))
            .filter(CrawlTask.owner_id == owner_id, CrawlTask.status == task_status)
            .order_by(CrawlTask.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_status(self, owner_id: uuid.UUID, *, task_status: str) -> int:
        return (
            self.session.query(func.count(CrawlTask.id))
            .filter(CrawlTask.owner_id == owner_id, CrawlTask.status == task_status)
            .scalar()
            or 0
        )

    def get_owner_stats(self, owner_id: uuid.UUID) -> dict:
        rows = (
            self.session.query(CrawlTask.status, func.count(CrawlTask.id))
            .filter(CrawlTask.owner_id == owner_id)
            .group_by(CrawlTask.status)
            .all()
        )
        counts: dict[str, int] = {s.value: 0 for s in TaskStatus}
        for status_val, cnt in rows:
            counts[status_val] = cnt
        return {
            "total": sum(counts.values()),
            **counts,
        }

    # -- CrawlRun operations --

    def create_run(self, *, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlRun:
        run = CrawlRun(task_id=task_id, owner_id=owner_id)
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(
        self,
        run: CrawlRun,
        *,
        status: str,
        total_found: int = 0,
        total_pages: int = 0,
        total_qualified: int = 0,
        total_failed: int = 0,
        error_message: str | None = None,
    ) -> CrawlRun:
        run.status = status
        run.finished_at = datetime.now()
        run.total_found = total_found
        run.total_pages = total_pages
        run.total_qualified = total_qualified
        run.total_failed = total_failed
        run.error_message = error_message
        self.session.flush()
        return run

    def get_latest_runs(
        self,
        owner_id: uuid.UUID,
        *,
        task_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 10,
    ) -> list[CrawlRun]:
        query = (
            self.session.query(CrawlRun)
            .filter(CrawlRun.owner_id == owner_id)
        )
        if task_id is not None:
            query = query.filter(CrawlRun.task_id == task_id)
        return (
            query.order_by(CrawlRun.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_latest_run(self, task_id: uuid.UUID) -> CrawlRun | None:
        return (
            self.session.query(CrawlRun)
            .filter(CrawlRun.task_id == task_id)
            .order_by(CrawlRun.created_at.desc())
            .first()
        )

    def snapshot_exists(self, task_id: uuid.UUID) -> bool:
        return (
            self.session.query(func.count(CrawlRun.id))
            .filter(CrawlRun.task_id == task_id)
            .scalar()
            or 0
        ) > 0

    def get_task_detail(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .options(
                selectinload(CrawlTask.urls),
                selectinload(CrawlTask.runs),
            )
            .filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id)
            .first()
        )
