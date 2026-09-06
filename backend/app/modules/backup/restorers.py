from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from sqlalchemy import Date, DateTime, Numeric, Table, TypeDecorator, Uuid, delete, insert, select, update
from sqlalchemy.orm import Session

from backend.app.models.crawl_task import (
    CrawlTask,
    CrawlTaskTag,
    CrawlTaskUrl,
    crawl_task_tag_links,
)
from backend.app.models.crawler_schedule import CrawlerSchedule, CrawlerScheduleTask
from backend.app.modules.backup.format import read_jsonl
from backend.app.modules.content.movies.filter_sync import sync_movie_filters
from backend.app.modules.crawler.schedules.service import calculate_next_run_at
from scraper.config import settings as scraper_settings
from shared.database.models.content import Movie, MovieFilter, MovieMagnet


@dataclass
class RestoreStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    conflicts: int = 0
    errors: int = 0
    conflict_samples: list[dict[str, Any]] = field(default_factory=list)


def stats_to_dict(stats: RestoreStats) -> dict[str, int]:
    return {
        "created": stats.created,
        "updated": stats.updated,
        "skipped": stats.skipped,
        "conflicts": stats.conflicts,
        "errors": stats.errors,
    }


def _coerce_column_value(column: Any, value: Any) -> Any:
    """Convert a JSON payload value back to the Python type of ``column``."""
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, TypeDecorator):
        item_type = getattr(column_type, "item_type", None)
        if item_type is not None and isinstance(item_type, Uuid) and isinstance(value, list):
            return [uuid.UUID(str(item)) for item in value]
        return value
    if isinstance(column_type, Uuid):
        if isinstance(value, list):
            return [uuid.UUID(str(item)) for item in value]
        return uuid.UUID(str(value))
    if isinstance(column_type, DateTime):
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    if isinstance(column_type, Date):
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))
    if isinstance(column_type, Numeric):
        return Decimal(str(value))
    return value


def _row_values(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    """Keep only known columns and coerce payload values per column type."""
    values: dict[str, Any] = {}
    for column in table.columns:
        if column.name in row and row[column.name] is not None:
            values[column.name] = _coerce_column_value(column, row[column.name])
    return values


def _require_archive_file(zip_file: ZipFile, arcname: str) -> None:
    names = {info.filename for info in zip_file.infolist()}
    if arcname not in names:
        raise ValueError(f"Backup archive missing {arcname}")


def restore_movies(
    db: Session,
    zip_file: ZipFile,
    mode: str,
    batch_size: int = 1000,
) -> RestoreStats:
    """Restore the movie group (movies, magnets) and rebuild filter rows."""
    _require_archive_file(zip_file, "data/movies.jsonl")
    stats = RestoreStats()

    if mode == "overwrite":
        db.execute(delete(MovieFilter))
        db.execute(delete(MovieMagnet))
        db.execute(delete(Movie))
        db.flush()

    movie_table = Movie.__table__
    skipped_movie_ids: set[uuid.UUID] = set()
    # Map archive movie ids to the movie rows that actually exist after restore.
    resolved_movies: dict[uuid.UUID, Movie] = {}
    processed = 0

    for row in read_jsonl(zip_file, "data/movies.jsonl"):
        try:
            incoming_id = row.get("id")
            existing = None
            if incoming_id is not None:
                incoming_uuid = uuid.UUID(str(incoming_id))
                existing = db.get(Movie, incoming_uuid)
            code = row.get("code")
            source_url = row.get("source_url")

            if existing is None and code:
                existing = db.scalar(select(Movie).where(Movie.code == str(code)))
            if existing is None and source_url:
                existing = db.scalar(select(Movie).where(Movie.source_url == str(source_url)))

            if existing is not None:
                # A different movie already owns the incoming code.
                if incoming_id is not None and existing.id != uuid.UUID(str(incoming_id)) and code:
                    stats.conflicts += 1
                    stats.conflict_samples.append(
                        {
                            "code": str(code),
                            "incoming_id": str(incoming_id),
                            "existing_id": str(existing.id),
                        }
                    )
                    skipped_movie_ids.add(uuid.UUID(str(incoming_id)))
                    stats.skipped += 1
                    continue
                values = _row_values(movie_table, row)
                values.pop("id", None)
                db.execute(
                    update(Movie).where(Movie.id == existing.id).values(**values)
                )
                resolved_movies[uuid.UUID(str(incoming_id)) if incoming_id else existing.id] = existing
                stats.updated += 1
                continue

            # Insert a new movie, keeping its original id when possible.
            values = _row_values(movie_table, row)
            values["id"] = uuid.UUID(str(incoming_id)) if incoming_id else uuid.uuid4()
            movie = Movie(**values)
            db.add(movie)
            resolved_movies[values["id"]] = movie
            stats.created += 1
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()

    db.commit()
    stats = _restore_magnets(db, zip_file, resolved_movies, skipped_movie_ids, stats, batch_size)

    # Filter counts are derived from the restored library, never trusted from
    # the backup, so rebuild them after every movie restore.
    db.commit()
    sync_movie_filters(db)
    db.commit()
    return stats


def _restore_magnets(
    db: Session,
    zip_file: ZipFile,
    resolved_movies: dict[uuid.UUID, Movie],
    skipped_movie_ids: set[uuid.UUID],
    stats: RestoreStats,
    batch_size: int,
) -> RestoreStats:
    """Restore magnet rows mapped onto the resolved movie ids."""
    archive_names = {info.filename for info in zip_file.infolist()}
    if "data/movie_magnets.jsonl" not in archive_names:
        return stats

    magnet_table = MovieMagnet.__table__
    processed = 0
    for row in read_jsonl(zip_file, "data/movie_magnets.jsonl"):
        try:
            incoming_movie_id = row.get("movie_id")
            if incoming_movie_id is None:
                stats.skipped += 1
                continue
            movie_uuid = uuid.UUID(str(incoming_movie_id))
            if movie_uuid in skipped_movie_ids:
                stats.skipped += 1
                continue
            target_movie = resolved_movies.get(movie_uuid)
            if target_movie is None:
                stats.skipped += 1
                continue
            dedupe_key = str(row.get("dedupe_key") or "")
            values = _row_values(magnet_table, row)
            values["movie_id"] = target_movie.id

            incoming_id = row.get("id")
            existing = None
            if incoming_id is not None:
                existing = db.get(MovieMagnet, uuid.UUID(str(incoming_id)))
            if existing is None and dedupe_key:
                existing = db.scalar(
                    select(MovieMagnet).where(
                        MovieMagnet.movie_id == target_movie.id,
                        MovieMagnet.dedupe_key == dedupe_key,
                    )
                )
            if existing is not None:
                values.pop("id", None)
                db.execute(update(MovieMagnet).where(MovieMagnet.id == existing.id).values(**values))
                stats.updated += 1
                continue
            values["id"] = uuid.UUID(str(incoming_id)) if incoming_id else uuid.uuid4()
            db.execute(insert(MovieMagnet.__table__).values(**values))
            stats.created += 1
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()
    db.commit()
    return stats


def restore_tasks_and_schedules(
    db: Session,
    zip_file: ZipFile,
    mode: str,
    owner_id: uuid.UUID,
    batch_size: int = 1000,
) -> RestoreStats:
    """Restore the tasks and schedules group for ``owner_id``."""
    _require_archive_file(zip_file, "data/crawl_tasks.jsonl")
    stats = RestoreStats()

    if mode == "overwrite":
        _clear_tasks_group(db, owner_id)

    task_id_map = _restore_tasks(db, zip_file, owner_id, stats, batch_size)
    _restore_task_urls(db, zip_file, task_id_map, stats, batch_size)
    tag_id_map = _restore_task_tags(db, zip_file, owner_id, stats, batch_size)
    _restore_task_tag_links(db, zip_file, task_id_map, tag_id_map, stats, batch_size)
    schedule_id_map = _restore_schedules(db, zip_file, owner_id, stats, batch_size)
    _restore_schedule_tasks(db, zip_file, schedule_id_map, task_id_map, stats, batch_size)
    db.commit()
    return stats


def _owned_task_ids(db: Session, owner_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(CrawlTask.id).where(CrawlTask.owner_id == owner_id)).all())


def _clear_tasks_group(db: Session, owner_id: uuid.UUID) -> None:
    """Delete the current user's reusable task and schedule rows before overwrite."""
    task_ids = _owned_task_ids(db, owner_id)
    schedule_ids = list(db.scalars(select(CrawlerSchedule.id).where(CrawlerSchedule.owner_id == owner_id)).all())
    schedule_link_table = CrawlerScheduleTask.__table__

    if task_ids:
        db.execute(
            delete(schedule_link_table).where(schedule_link_table.c.task_id.in_(task_ids))
        )
        db.execute(
            delete(crawl_task_tag_links).where(crawl_task_tag_links.c.task_id.in_(task_ids))
        )
        db.execute(delete(CrawlTaskUrl).where(CrawlTaskUrl.task_id.in_(task_ids)))
    if schedule_ids:
        db.execute(
            delete(schedule_link_table).where(schedule_link_table.c.schedule_id.in_(schedule_ids))
        )
        db.execute(delete(CrawlerSchedule).where(CrawlerSchedule.id.in_(schedule_ids)))
    owned_tag_ids = list(db.scalars(select(CrawlTaskTag.id).where(CrawlTaskTag.owner_id == owner_id)).all())
    if owned_tag_ids:
        db.execute(
            delete(crawl_task_tag_links).where(crawl_task_tag_links.c.tag_id.in_(owned_tag_ids))
        )
    db.execute(delete(CrawlTask).where(CrawlTask.owner_id == owner_id))
    db.execute(delete(CrawlTaskTag).where(CrawlTaskTag.owner_id == owner_id))
    db.flush()


def _restore_tasks(
    db: Session,
    zip_file: ZipFile,
    owner_id: uuid.UUID,
    stats: RestoreStats,
    batch_size: int,
) -> dict[uuid.UUID, uuid.UUID]:
    """Restore tasks and map archive task ids to resolved task ids."""
    task_table = CrawlTask.__table__
    task_id_map: dict[uuid.UUID, uuid.UUID] = {}
    processed = 0
    for row in read_jsonl(zip_file, "data/crawl_tasks.jsonl"):
        try:
            incoming_id = row.get("id")
            incoming_uuid = uuid.UUID(str(incoming_id)) if incoming_id else None
            existing = db.get(CrawlTask, incoming_uuid) if incoming_uuid else None
            name = str(row.get("name") or "")
            if existing is None and name:
                existing = db.scalar(
                    select(CrawlTask).where(
                        CrawlTask.owner_id == owner_id,
                        CrawlTask.name == name,
                    )
                )
            if existing is not None:
                values = _row_values(task_table, row)
                values.pop("id", None)
                values["owner_id"] = owner_id
                db.execute(update(CrawlTask).where(CrawlTask.id == existing.id).values(**values))
                resolved_id = existing.id
                stats.updated += 1
            else:
                values = _row_values(task_table, row)
                values["owner_id"] = owner_id
                values["id"] = incoming_uuid or uuid.uuid4()
                db.execute(insert(CrawlTask.__table__).values(**values))
                resolved_id = values["id"]
                stats.created += 1
            if incoming_uuid is not None:
                task_id_map[incoming_uuid] = resolved_id
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()
    db.commit()
    return task_id_map


def _restore_task_urls(
    db: Session,
    zip_file: ZipFile,
    task_id_map: dict[uuid.UUID, uuid.UUID],
    stats: RestoreStats,
    batch_size: int,
) -> None:
    archive_names = {info.filename for info in zip_file.infolist()}
    if "data/crawl_task_urls.jsonl" not in archive_names:
        return
    url_table = CrawlTaskUrl.__table__
    processed = 0
    for row in read_jsonl(zip_file, "data/crawl_task_urls.jsonl"):
        try:
            archive_task_id = row.get("task_id")
            if archive_task_id is None:
                stats.skipped += 1
                continue
            resolved_task_id = task_id_map.get(uuid.UUID(str(archive_task_id)))
            if resolved_task_id is None:
                stats.skipped += 1
                continue
            url = str(row.get("url") or "")
            values = _row_values(url_table, row)
            values["task_id"] = resolved_task_id

            incoming_id = row.get("id")
            existing = None
            if incoming_id is not None:
                existing = db.get(CrawlTaskUrl, uuid.UUID(str(incoming_id)))
            if existing is None and url:
                existing = db.scalar(
                    select(CrawlTaskUrl).where(
                        CrawlTaskUrl.task_id == resolved_task_id,
                        CrawlTaskUrl.url == url,
                    )
                )
            if existing is not None:
                values.pop("id", None)
                db.execute(update(CrawlTaskUrl).where(CrawlTaskUrl.id == existing.id).values(**values))
                stats.updated += 1
                continue
            values["id"] = uuid.UUID(str(incoming_id)) if incoming_id else uuid.uuid4()
            db.execute(insert(CrawlTaskUrl.__table__).values(**values))
            stats.created += 1
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()
    db.commit()


def _restore_task_tags(
    db: Session,
    zip_file: ZipFile,
    owner_id: uuid.UUID,
    stats: RestoreStats,
    batch_size: int,
) -> dict[uuid.UUID, uuid.UUID]:
    archive_names = {info.filename for info in zip_file.infolist()}
    tag_id_map: dict[uuid.UUID, uuid.UUID] = {}
    if "data/crawl_task_tags.jsonl" not in archive_names:
        return tag_id_map
    tag_table = CrawlTaskTag.__table__
    processed = 0
    for row in read_jsonl(zip_file, "data/crawl_task_tags.jsonl"):
        try:
            incoming_id = row.get("id")
            incoming_uuid = uuid.UUID(str(incoming_id)) if incoming_id else None
            name = str(row.get("name") or "")
            existing = None
            if incoming_uuid is not None and name:
                existing = db.scalar(
                    select(CrawlTaskTag).where(
                        CrawlTaskTag.owner_id == owner_id,
                        CrawlTaskTag.name == name,
                    )
                )
            if existing is not None:
                resolved_id = existing.id
                stats.updated += 1
            else:
                values = _row_values(tag_table, row)
                values["owner_id"] = owner_id
                values["name"] = name
                values["id"] = incoming_uuid or uuid.uuid4()
                db.execute(insert(CrawlTaskTag.__table__).values(**values))
                resolved_id = values["id"]
                stats.created += 1
            if incoming_uuid is not None:
                tag_id_map[incoming_uuid] = resolved_id
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()
    db.commit()
    return tag_id_map


def _restore_task_tag_links(
    db: Session,
    zip_file: ZipFile,
    task_id_map: dict[uuid.UUID, uuid.UUID],
    tag_id_map: dict[uuid.UUID, uuid.UUID],
    stats: RestoreStats,
    batch_size: int,
) -> None:
    archive_names = {info.filename for info in zip_file.infolist()}
    if "data/crawl_task_tag_links.jsonl" not in archive_names:
        return
    processed = 0
    for row in read_jsonl(zip_file, "data/crawl_task_tag_links.jsonl"):
        try:
            archive_task_id = row.get("task_id")
            archive_tag_id = row.get("tag_id")
            if archive_task_id is None or archive_tag_id is None:
                stats.skipped += 1
                continue
            task_uuid = uuid.UUID(str(archive_task_id))
            tag_uuid = uuid.UUID(str(archive_tag_id))
            resolved_task_id = task_id_map.get(task_uuid)
            resolved_tag_id = tag_id_map.get(tag_uuid)
            if resolved_task_id is None or resolved_tag_id is None:
                stats.skipped += 1
                continue
            link_exists = db.scalar(
                select(crawl_task_tag_links.c.task_id).where(
                    crawl_task_tag_links.c.task_id == resolved_task_id,
                    crawl_task_tag_links.c.tag_id == resolved_tag_id,
                )
            )
            if link_exists is not None:
                stats.skipped += 1
                continue
            db.execute(
                insert(crawl_task_tag_links).values(
                    task_id=resolved_task_id,
                    tag_id=resolved_tag_id,
                )
            )
            stats.created += 1
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()
    db.commit()


def _restore_schedules(
    db: Session,
    zip_file: ZipFile,
    owner_id: uuid.UUID,
    stats: RestoreStats,
    batch_size: int,
) -> dict[uuid.UUID, uuid.UUID]:
    archive_names = {info.filename for info in zip_file.infolist()}
    schedule_id_map: dict[uuid.UUID, uuid.UUID] = {}
    if "data/crawler_schedules.jsonl" not in archive_names:
        return schedule_id_map
    schedule_table = CrawlerSchedule.__table__
    processed = 0
    for row in read_jsonl(zip_file, "data/crawler_schedules.jsonl"):
        try:
            incoming_id = row.get("id")
            incoming_uuid = uuid.UUID(str(incoming_id)) if incoming_id else None
            name = str(row.get("name") or "")
            existing = None
            if incoming_uuid is not None:
                existing = db.get(CrawlerSchedule, incoming_uuid)
            if existing is None and name:
                existing = db.scalar(
                    select(CrawlerSchedule).where(
                        CrawlerSchedule.owner_id == owner_id,
                        CrawlerSchedule.name == name,
                    )
                )
            schedule_type = str(row.get("schedule_type") or "daily")
            time_of_day = str(row.get("time_of_day") or "03:30")
            weekdays = row.get("weekdays") or []
            enabled = bool(row.get("enabled", True))

            if existing is not None:
                values = _row_values(schedule_table, row)
                values.pop("id", None)
                values["owner_id"] = owner_id
                values["next_run_at"] = _computed_next_run(schedule_type, time_of_day, weekdays, enabled)
                db.execute(update(CrawlerSchedule).where(CrawlerSchedule.id == existing.id).values(**values))
                resolved_id = existing.id
                stats.updated += 1
            else:
                values = _row_values(schedule_table, row)
                values["owner_id"] = owner_id
                values["id"] = incoming_uuid or uuid.uuid4()
                values["next_run_at"] = _computed_next_run(schedule_type, time_of_day, weekdays, enabled)
                db.execute(insert(CrawlerSchedule.__table__).values(**values))
                resolved_id = values["id"]
                stats.created += 1
            if incoming_uuid is not None:
                schedule_id_map[incoming_uuid] = resolved_id
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()
    db.commit()
    return schedule_id_map


def _computed_next_run(schedule_type: str, time_of_day: str, weekdays: list[int], enabled: bool) -> Any:
    if not enabled:
        return None
    try:
        return calculate_next_run_at(schedule_type, time_of_day, [int(day) for day in weekdays])
    except Exception:
        return None


def _restore_schedule_tasks(
    db: Session,
    zip_file: ZipFile,
    schedule_id_map: dict[uuid.UUID, uuid.UUID],
    task_id_map: dict[uuid.UUID, uuid.UUID],
    stats: RestoreStats,
    batch_size: int,
) -> None:
    archive_names = {info.filename for info in zip_file.infolist()}
    if "data/crawler_schedule_tasks.jsonl" not in archive_names:
        return
    processed = 0
    for row in read_jsonl(zip_file, "data/crawler_schedule_tasks.jsonl"):
        try:
            archive_schedule_id = row.get("schedule_id")
            archive_task_id = row.get("task_id")
            if archive_schedule_id is None or archive_task_id is None:
                stats.skipped += 1
                continue
            schedule_uuid = uuid.UUID(str(archive_schedule_id))
            task_uuid = uuid.UUID(str(archive_task_id))
            resolved_schedule_id = schedule_id_map.get(schedule_uuid)
            resolved_task_id = task_id_map.get(task_uuid)
            if resolved_schedule_id is None or resolved_task_id is None:
                stats.skipped += 1
                continue
            link_exists = db.scalar(
                select(CrawlerScheduleTask.__table__.c.schedule_id).where(
                    CrawlerScheduleTask.schedule_id == resolved_schedule_id,
                    CrawlerScheduleTask.task_id == resolved_task_id,
                )
            )
            if link_exists is not None:
                stats.skipped += 1
                continue
            db.execute(
                insert(CrawlerScheduleTask.__table__).values(
                    schedule_id=resolved_schedule_id,
                    task_id=resolved_task_id,
                )
            )
            stats.created += 1
        except Exception:
            db.rollback()
            stats.errors += 1
        processed += 1
        if processed % batch_size == 0:
            db.commit()
    db.commit()


def restore_config(zip_file: ZipFile, include_sensitive_in_archive: bool) -> RestoreStats:
    """Restore config files present in the archive.

    Sensitive values that are absent from the archive (because the backup was
    created without ``include_sensitive``) are left untouched locally.
    """
    stats = RestoreStats()
    archive_names = {info.filename for info in zip_file.infolist()}

    if "config/crawler_config.json" in archive_names:
        from backend.app.modules.crawler.config.conf_reader import (
            CONFIG_KEYS,
            write_crawler_config,
        )

        try:
            payload = json.loads(read_text(zip_file, "config/crawler_config.json"))
            if isinstance(payload, dict):
                write_crawler_config({key: value for key, value in payload.items() if key in CONFIG_KEYS})
                stats.updated += 1
        except Exception:
            stats.errors += 1

    if "config/movie_filter_config.json" in archive_names:
        from backend.app.modules.content.movies.filter_config import write_movie_filter_config

        try:
            payload = json.loads(read_text(zip_file, "config/movie_filter_config.json"))
            filters = payload.get("filters") if isinstance(payload, dict) else None
            if isinstance(filters, dict):
                write_movie_filter_config(filters)
                stats.updated += 1
        except Exception:
            stats.errors += 1

    if "config/storage_config.json" in archive_names:
        from backend.app.modules.storage.config.service import StorageConfigService

        try:
            payload = json.loads(read_text(zip_file, "config/storage_config.json"))
            if isinstance(payload, dict):
                if not include_sensitive_in_archive:
                    payload = {key: value for key, value in payload.items() if key != "api_token"}
                StorageConfigService().update_config(payload)
                stats.updated += 1
        except Exception:
            stats.errors += 1

    if include_sensitive_in_archive and "config/javdb_cookies.json" in archive_names:
        try:
            text = read_text(zip_file, "config/javdb_cookies.json")
            cookie_path = Path(scraper_settings.COOKIE_DIR) / "javdb_cookies.json"
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cookie_path.with_name(f"{cookie_path.name}.tmp")
            temp_path.write_text(text, encoding="utf-8")
            temp_path.replace(cookie_path)
            stats.updated += 1
        except Exception:
            stats.errors += 1
    return stats


def read_text(zip_file: ZipFile, arcname: str) -> str:
    try:
        with zip_file.open(arcname, "r") as raw:
            return raw.read().decode("utf-8")
    except KeyError as exc:
        raise ValueError(f"Backup archive missing {arcname}") from exc
