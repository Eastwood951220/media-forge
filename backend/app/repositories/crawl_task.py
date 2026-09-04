import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask, CrawlTaskTag, CrawlTaskUrl
from backend.app.models.enums import TaskStatus
from backend.app.repositories.base import BaseRepository
from backend.app.schemas.crawl_task import TaskUrlEntryCreate
from scraper.tasks.task_utils import build_final_url, determine_source


class CrawlTaskRepository(BaseRepository):
    """Repository for CrawlTask model operations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlTask)

    def _owner_query(
        self,
        owner_id: uuid.UUID,
        keyword: str | None = None,
        tag_names: list[str] | None = None,
    ):
        query = (
            self.session.query(CrawlTask)
            .options(selectinload(CrawlTask.urls), selectinload(CrawlTask.tags))
            .filter(CrawlTask.owner_id == owner_id)
        )
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            query = query.filter(CrawlTask.name.ilike(f"%{normalized_keyword}%"))
        return self._apply_tag_filter(query, owner_id, tag_names)

    def _apply_tag_filter(
        self,
        query,
        owner_id: uuid.UUID,
        tag_names: list[str] | None,
    ):
        normalized_tags = [name.strip() for name in tag_names or [] if name.strip()]
        if not normalized_tags:
            return query
        tag_count = len(set(normalized_tags))
        matching_task_ids = (
            self.session.query(CrawlTask.id)
            .join(CrawlTask.tags)
            .filter(CrawlTask.owner_id == owner_id, CrawlTaskTag.name.in_(set(normalized_tags)))
            .group_by(CrawlTask.id)
            .having(func.count(func.distinct(CrawlTaskTag.name)) == tag_count)
            .subquery()
        )
        return query.filter(CrawlTask.id.in_(self.session.query(matching_task_ids.c.id)))

    def get_by_owner(
        self,
        owner_id: uuid.UUID,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        tag_names: list[str] | None = None,
    ) -> tuple[list[CrawlTask], bool]:
        query = self._owner_query(owner_id, keyword, tag_names).order_by(
            CrawlTask.created_at.desc()
        )
        rows = query.offset((page - 1) * size).limit(size + 1).all()
        return rows[:size], len(rows) > size

    def count_by_owner(
        self,
        owner_id: uuid.UUID,
        keyword: str | None = None,
        tag_names: list[str] | None = None,
    ) -> int:
        query = self.session.query(CrawlTask).filter(CrawlTask.owner_id == owner_id)
        normalized_keyword = keyword.strip() if keyword else ""
        if normalized_keyword:
            query = query.filter(CrawlTask.name.ilike(f"%{normalized_keyword}%"))
        query = self._apply_tag_filter(query, owner_id, tag_names)
        return query.with_entities(func.count(CrawlTask.id)).scalar() or 0

    def get_tags_by_owner(self, owner_id: uuid.UUID) -> list[CrawlTaskTag]:
        return (
            self.session.query(CrawlTaskTag)
            .filter(CrawlTaskTag.owner_id == owner_id)
            .order_by(CrawlTaskTag.name.asc())
            .all()
        )

    def get_or_create_tags(self, owner_id: uuid.UUID, tag_names: list[str]) -> list[CrawlTaskTag]:
        if not tag_names:
            return []
        existing = (
            self.session.query(CrawlTaskTag)
            .filter(CrawlTaskTag.owner_id == owner_id, CrawlTaskTag.name.in_(tag_names))
            .all()
        )
        by_name = {tag.name: tag for tag in existing}
        for name in tag_names:
            if name not in by_name:
                tag = CrawlTaskTag(owner_id=owner_id, name=name)
                self.session.add(tag)
                self.session.flush()
                by_name[name] = tag
        return [by_name[name] for name in tag_names]

    def replace_task_tags(self, task: CrawlTask, tags: list[CrawlTaskTag]) -> None:
        task.tags = tags

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
        if source == "unknown":
            raise ValueError("不支持的 URL 来源")
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
        storage_location: str,
        is_skip: bool,
        urls: list[TaskUrlEntryCreate],
    ) -> CrawlTask:
        task = CrawlTask(name=name, storage_location=storage_location, is_skip=is_skip, owner_id=owner_id)
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

    def get_task_detail(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> CrawlTask | None:
        return (
            self.session.query(CrawlTask)
            .options(selectinload(CrawlTask.urls))
            .filter(CrawlTask.id == task_id, CrawlTask.owner_id == owner_id)
            .first()
        )

    def get_dict_by_owner(self, owner_id: uuid.UUID) -> list[dict[str, str]]:
        """Return task ID-to-name mapping for the owner."""
        rows = (
            self.session.query(CrawlTask.id, CrawlTask.name)
            .filter(CrawlTask.owner_id == owner_id)
            .order_by(CrawlTask.name.asc())
            .all()
        )
        return [{"id": str(row.id), "name": row.name} for row in rows]

    def get_summary_stats(self, owner_id: uuid.UUID) -> dict[str, int]:
        total = self.session.query(func.count(CrawlTask.id)).filter(CrawlTask.owner_id == owner_id).scalar() or 0
        enabled = self.session.query(func.count(CrawlTask.id)).filter(CrawlTask.owner_id == owner_id, CrawlTask.is_skip == False).scalar() or 0
        disabled = total - enabled
        return {
            "total": total,
            "enabled": enabled,
            "disabled": disabled,
        }

    def get_latest_runs_by_task_ids(self, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, CrawlRun]:
        if not task_ids:
            return {}

        ranked = (
            self.session.query(
                CrawlRun.id.label("run_id"),
                CrawlRun.task_id.label("task_id"),
                func.row_number()
                .over(
                    partition_by=CrawlRun.task_id,
                    order_by=(CrawlRun.created_at.desc(), CrawlRun.id.desc()),
                )
                .label("rank"),
            )
            .filter(CrawlRun.task_id.in_(task_ids))
            .subquery()
        )
        rows = (
            self.session.query(CrawlRun)
            .join(ranked, CrawlRun.id == ranked.c.run_id)
            .filter(ranked.c.rank == 1)
            .all()
        )
        return {row.task_id: row for row in rows if row.task_id is not None}
