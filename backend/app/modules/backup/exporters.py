from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from zipfile import ZipFile

from sqlalchemy import Table, func, select
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import (
    CrawlTask,
    CrawlTaskTag,
    CrawlTaskUrl,
    crawl_task_tag_links,
)
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleTask
from backend.app.modules.backup.format import write_jsonl
from backend.app.modules.content.movies.filter_config import read_movie_filter_config
from backend.app.modules.crawler.config.conf_reader import read_crawler_config_dict
from backend.app.modules.storage.config.service import StorageConfigService
from scraper.config import settings as scraper_settings
from shared.database.models.content import Movie, MovieFilter, MovieMagnet

Scope = Callable[[Any, uuid.UUID], Any]

MOVIE_EXPORTS: tuple[tuple[Any, str, Scope | None], ...] = (
    (Movie, "data/movies.jsonl", None),
    (MovieMagnet, "data/movie_magnets.jsonl", None),
    (MovieFilter, "data/movie_filters.jsonl", None),
)

TASK_EXPORTS: tuple[tuple[Any, str, Scope | None], ...] = (
    (
        CrawlTask,
        "data/crawl_tasks.jsonl",
        lambda stmt, owner_id: stmt.where(CrawlTask.owner_id == owner_id),
    ),
    (
        CrawlTaskUrl,
        "data/crawl_task_urls.jsonl",
        lambda stmt, owner_id: stmt.where(
            CrawlTaskUrl.task_id.in_(select(CrawlTask.id).where(CrawlTask.owner_id == owner_id))
        ),
    ),
    (
        CrawlTaskTag,
        "data/crawl_task_tags.jsonl",
        lambda stmt, owner_id: stmt.where(CrawlTaskTag.owner_id == owner_id),
    ),
    (
        crawl_task_tag_links,
        "data/crawl_task_tag_links.jsonl",
        lambda stmt, owner_id: stmt.where(
            crawl_task_tag_links.c.task_id.in_(
                select(CrawlTask.id).where(CrawlTask.owner_id == owner_id)
            )
        ),
    ),
    (
        CrawlerSchedule,
        "data/crawler_schedules.jsonl",
        lambda stmt, owner_id: stmt.where(CrawlerSchedule.owner_id == owner_id),
    ),
    (
        CrawlerScheduleTask,
        "data/crawler_schedule_tasks.jsonl",
        lambda stmt, owner_id: stmt.where(
            CrawlerScheduleTask.schedule_id.in_(
                select(CrawlerSchedule.id).where(CrawlerSchedule.owner_id == owner_id)
            )
        ).where(
            CrawlerScheduleTask.task_id.in_(
                select(CrawlTask.id).where(CrawlTask.owner_id == owner_id)
            )
        ),
    ),
)

PAGE_SIZE = 2000


def _json_ready(value: Any) -> Any:
    """Convert non-JSON-safe column values into JSON-compatible equivalents."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def serialize_model_row(model: object, exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialize one ORM row to plain JSON-compatible column values."""
    excluded = exclude or set()
    payload: dict[str, Any] = {}
    for column in model.__table__.columns:  # type: ignore[attr-defined]
        if column.name in excluded:
            continue
        payload[column.name] = _json_ready(getattr(model, column.name))
    return payload


def _scope_entity_rows(db: Session, entity: Any, owner_id: uuid.UUID | None) -> Any:
    """Build a scoped select statement for one entity in ``db``.

    ``owner_id`` may be ``None`` for automatic backups, which include every
    user's rows instead of one owner's rows.
    """
    specs = [spec for spec in MOVIE_EXPORTS + TASK_EXPORTS if spec[0] is entity]
    scope: Scope | None = None
    if specs:
        scope = specs[0][2]
    stmt = select(entity)
    if scope is not None and owner_id is not None:
        stmt = scope(stmt, owner_id)
    return stmt


def iter_entity_rows(db: Session, entity: Any, owner_id: uuid.UUID) -> Any:
    """Iterate over all rows of ``entity`` in pages without one giant fetch.

    ``entity`` may be an ORM model class or a plain SQLAlchemy ``Table`` such
    as the task-tag link table.
    """
    table = entity.__table__ if isinstance(entity, type) else entity
    order_columns = list(table.primary_key.columns)
    if not order_columns:
        raise ValueError(f"Table {table.name} has no primary key for paging")
    stmt = _scope_entity_rows(db, entity, owner_id).order_by(*order_columns)
    offset = 0
    while True:
        page_stmt = stmt.limit(PAGE_SIZE).offset(offset)
        if isinstance(entity, Table):
            rows = db.execute(page_stmt).mappings().all()
        else:
            rows = db.execute(page_stmt).scalars().all()
        if not rows:
            break
        yield from rows
        offset += PAGE_SIZE


def count_entity_rows(db: Session, entity: Any, owner_id: uuid.UUID) -> int:
    """Count rows for one export entity using the same scope as the export."""
    table = entity.__table__ if isinstance(entity, type) else entity
    stmt = _scope_entity_rows(db, entity, owner_id)
    stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    return int(db.execute(stmt).scalar_one())


def export_db_group(
    db: Session,
    zip_file: ZipFile,
    specs: tuple[tuple[Any, str, Scope | None], ...],
    owner_id: uuid.UUID,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, int]:
    """Write every table of one data group as JSONL and return row counts."""
    row_counts: dict[str, int] = {}
    for entity, arcname, _scope in specs:
        if on_progress is not None:
            total = count_entity_rows(db, entity, owner_id)
            on_progress(arcname, 0, total)

        def counting_rows() -> Any:
            processed = 0
            for row in iter_entity_rows(db, entity, owner_id):
                if isinstance(entity, Table):
                    yield {key: _json_ready(value) for key, value in row.items()}
                else:
                    yield serialize_model_row(row)
                processed += 1
                if on_progress is not None and processed % 500 == 0:
                    on_progress(arcname, processed, None)

        count = write_jsonl(zip_file, arcname, counting_rows())
        row_counts[arcname] = count
        if on_progress is not None:
            on_progress(arcname, count, None)
    return row_counts


def export_config_files(
    zip_file: ZipFile,
    include_sensitive: bool,
) -> None:
    """Write the configuration group entries into the archive.

    Sensitive values (CloudDrive2 API token, JavDB cookies) are only included
    when ``include_sensitive`` is true.
    """
    crawler_config = read_crawler_config_dict()
    zip_file.writestr(
        "config/crawler_config.json",
        json.dumps(crawler_config, ensure_ascii=False, indent=2).encode("utf-8"),
    )

    filter_config = read_movie_filter_config()
    zip_file.writestr(
        "config/movie_filter_config.json",
        json.dumps(filter_config, ensure_ascii=False, indent=2).encode("utf-8"),
    )

    storage_config = StorageConfigService().get_raw_config()
    if not include_sensitive:
        storage_config = {key: value for key, value in storage_config.items() if key != "api_token"}
    zip_file.writestr(
        "config/storage_config.json",
        json.dumps(storage_config, ensure_ascii=False, indent=2).encode("utf-8"),
    )

    if include_sensitive:
        cookie_path = Path(scraper_settings.COOKIE_DIR) / "javdb_cookies.json"
        if cookie_path.is_file():
            zip_file.write(cookie_path, "config/javdb_cookies.json")
