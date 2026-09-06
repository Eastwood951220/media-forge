from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import case, func, literal, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.storage_task import StorageMainTask
from backend.app.modules.crawler.tasks.runtime_status import build_task_runtime_status_response
from backend.app.modules.dashboard.schemas import (
    CountItem,
    DailyTrendItem,
    DashboardAlert,
    DashboardContentSection,
    DashboardCrawlerSection,
    DashboardMovieStorageStatus,
    DashboardOverview,
    DashboardOverviewDraft,
    DashboardQueueStatus,
    DashboardContentRankings,
    DashboardRankingGroup,
    DashboardRunsSection,
    DashboardRuntimeStats,
    DashboardStorageIndex,
    DashboardStorageSection,
    DashboardTaskStats,
    PartialError,
    RecentCrawlerRun,
    RecentStorageTask,
    RankingItem,
    SystemStatus,
)
from shared.database.models.content import Movie


RECENT_LIMIT = 6
TREND_DAYS = 7
RANKING_LIMIT = 5
RECENT_RANKING_DAYS = 30


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _safe_section(
    section: str,
    partial_errors: list[PartialError],
    fallback,
    builder: Callable[[], object],
):
    try:
        return builder()
    except Exception as exc:
        partial_errors.append(PartialError(section=section, message=str(exc)))
        return fallback


def _count_items(rows) -> list[CountItem]:
    return [CountItem(status=str(status), count=int(count)) for status, count in rows]


def _build_crawler_section(db: Session, owner_id: uuid.UUID, queue_status: dict) -> DashboardCrawlerSection:
    total = int(db.query(func.count(CrawlTask.id)).filter(CrawlTask.owner_id == owner_id).scalar() or 0)
    disabled = int(
        db.query(func.count(CrawlTask.id))
        .filter(CrawlTask.owner_id == owner_id, CrawlTask.is_skip.is_(True))
        .scalar()
        or 0
    )
    runtime_response = build_task_runtime_status_response(db, owner_id)
    return DashboardCrawlerSection(
        task_stats=DashboardTaskStats(total=total, enabled=max(total - disabled, 0), disabled=disabled),
        runtime_stats=DashboardRuntimeStats(**runtime_response.stats.model_dump()),
        queue=DashboardQueueStatus(**queue_status),
    )


def _build_runs_section(db: Session, owner_id: uuid.UUID) -> DashboardRunsSection:
    owner_task_ids = db.query(CrawlTask.id).filter(CrawlTask.owner_id == owner_id).subquery()
    owner_runs = db.query(CrawlRun).filter(CrawlRun.task_id.in_(owner_task_ids))
    status_rows = owner_runs.with_entities(CrawlRun.status, func.count(CrawlRun.id)).group_by(CrawlRun.status).all()
    recent_rows = owner_runs.order_by(CrawlRun.created_at.desc()).limit(RECENT_LIMIT).all()
    since = datetime.now(timezone.utc) - timedelta(days=TREND_DAYS - 1)
    trend_rows = (
        owner_runs.filter(CrawlRun.created_at >= since)
        .with_entities(func.date(CrawlRun.created_at), CrawlRun.status, func.count(CrawlRun.id))
        .group_by(func.date(CrawlRun.created_at), CrawlRun.status)
        .all()
    )
    trend_by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"completed": 0, "failed": 0})
    for day, status, count in trend_rows:
        day_key = str(day)
        if status in {"completed", "failed"}:
            trend_by_day[day_key][status] = int(count)
    today = datetime.now(timezone.utc).date()
    daily_trend = []
    for offset in range(TREND_DAYS - 1, -1, -1):
        day_key = (today - timedelta(days=offset)).isoformat()
        values = trend_by_day[day_key]
        daily_trend.append(DailyTrendItem(date=day_key, completed=values["completed"], failed=values["failed"]))
    return DashboardRunsSection(
        status_distribution=_count_items(status_rows),
        daily_trend=daily_trend,
        recent=[
            RecentCrawlerRun(
                id=str(row.id),
                task_name=row.task_name,
                status=row.status,
                crawl_mode=row.crawl_mode,
                created_at=_iso(row.created_at),
                started_at=_iso(row.started_at),
                finished_at=_iso(row.finished_at),
                error=row.error,
            )
            for row in recent_rows
        ],
    )


def _json_text_value(column, key: str, dialect_name: str):
    if dialect_name == "sqlite":
        return func.json_extract(column, f"$.{key}")
    if dialect_name == "postgresql":
        return type_coerce(column, JSONB)[key].astext
    return func.json_extract(column, f"$.{key}")


def _count_movie_storage_statuses(db: Session) -> tuple[int, dict[str, int]]:
    """Count movie storage statuses using SQL aggregation."""
    dialect = db.bind.dialect.name
    storage_status_expr = _json_text_value(Movie.storage_summary, "storage_status", dialect)
    last_status_expr = _json_text_value(Movie.storage_summary, "last_status", dialect)

    storage_status = func.coalesce(storage_status_expr, "")
    last_status = func.coalesce(last_status_expr, "")
    raw_status = case(
        (storage_status != "", storage_status),
        else_=last_status,
    )
    status_expr = case(
        (raw_status == "completed", literal("stored")),
        (raw_status.in_(("stored", "storing", "not_stored")), raw_status),
        (raw_status.in_(("queued", "running", "pending", "waiting_download", "moving")), literal("storing")),
        else_=literal("not_stored"),
    ).label("storage_status")

    rows = (
        db.query(status_expr, func.count(Movie.id))
        .select_from(Movie)
        .group_by(status_expr)
        .all()
    )
    counts = {"stored": 0, "storing": 0, "not_stored": 0}
    total = 0
    for status, count in rows:
        normalized = str(status or "not_stored")
        if normalized not in counts:
            normalized = "not_stored"
        count_int = int(count or 0)
        counts[normalized] += count_int
        total += count_int
    return total, counts


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_storage_status_from_summary(summary: object) -> str:
    if not isinstance(summary, dict):
        return "not_stored"
    status = str(summary.get("storage_status") or summary.get("last_status") or "")
    if status == "completed":
        return "stored"
    if status in {"queued", "running", "pending", "waiting_download", "moving"}:
        return "storing"
    if status in {"stored", "storing", "not_stored"}:
        return status
    return "not_stored"


def _add_movie_rank_values(
    counters: dict[str, Counter[str]],
    *,
    actors: list[str] | None,
    tags: list[str] | None,
    maker: str | None,
    series: str | None,
) -> None:
    for actor in sorted({str(value).strip() for value in (actors or []) if str(value).strip()}):
        counters["actors"][actor] += 1
    for tag in sorted({str(value).strip() for value in (tags or []) if str(value).strip()}):
        counters["tags"][tag] += 1
    maker_name = str(maker or "").strip()
    if maker_name:
        counters["makers"][maker_name] += 1
    series_name = str(series or "").strip()
    if series_name:
        counters["series"][series_name] += 1


def _empty_ranking_counters() -> dict[str, Counter[str]]:
    return {
        "actors": Counter(),
        "makers": Counter(),
        "tags": Counter(),
        "series": Counter(),
    }


def _ranking_items(counter: Counter[str]) -> list[RankingItem]:
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:RANKING_LIMIT]
    return [RankingItem(name=name, count=count) for name, count in ordered]


def _ranking_group(counters: dict[str, Counter[str]]) -> DashboardRankingGroup:
    return DashboardRankingGroup(
        actors=_ranking_items(counters["actors"]),
        makers=_ranking_items(counters["makers"]),
        tags=_ranking_items(counters["tags"]),
        series=_ranking_items(counters["series"]),
    )


def _build_content_rankings(db: Session) -> DashboardContentRankings:
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=RECENT_RANKING_DAYS)
    total = _empty_ranking_counters()
    recent_storage = _empty_ranking_counters()
    recent_created = _empty_ranking_counters()

    rows = db.query(
        Movie.actors,
        Movie.tags,
        Movie.maker,
        Movie.series,
        Movie.storage_summary,
        Movie.created_at,
    ).all()
    for actors, tags, maker, series, storage_summary, created_at in rows:
        values = {
            "actors": list(actors or []),
            "tags": list(tags or []),
            "maker": maker,
            "series": series,
        }
        _add_movie_rank_values(total, **values)

        created_at_value = _parse_datetime(created_at)
        if created_at_value is not None and created_at_value >= recent_cutoff:
            _add_movie_rank_values(recent_created, **values)

        synced_at = _parse_datetime((storage_summary or {}).get("synced_at") if isinstance(storage_summary, dict) else None)
        if _normalized_storage_status_from_summary(storage_summary) == "stored" and synced_at is not None and synced_at >= recent_cutoff:
            _add_movie_rank_values(recent_storage, **values)

    return DashboardContentRankings(
        total=_ranking_group(total),
        recent_storage=_ranking_group(recent_storage),
        recent_created=_ranking_group(recent_created),
    )


def _build_content_section(db: Session) -> DashboardContentSection:
    total, counts = _count_movie_storage_statuses(db)
    return DashboardContentSection(
        movie_total=total,
        storage_status=DashboardMovieStorageStatus(**counts),
        rankings=_build_content_rankings(db),
    )


def _build_storage_section(db: Session, owner_id: uuid.UUID, index_metadata: dict) -> DashboardStorageSection:
    owner_tasks = db.query(StorageMainTask).filter(StorageMainTask.created_by == owner_id)
    status_rows = owner_tasks.with_entities(StorageMainTask.status, func.count(StorageMainTask.id)).group_by(StorageMainTask.status).all()
    recent_rows = owner_tasks.order_by(StorageMainTask.created_at.desc()).limit(RECENT_LIMIT).all()
    return DashboardStorageSection(
        task_status_distribution=_count_items(status_rows),
        recent_tasks=[
            RecentStorageTask(
                id=str(row.id),
                alias=row.alias,
                display_name=row.display_name,
                status=row.status,
                total_count=row.total_count,
                success_count=row.success_count,
                failed_count=row.failed_count,
                skipped_count=row.skipped_count,
                created_at=_iso(row.created_at),
                started_at=_iso(row.started_at),
                finished_at=_iso(row.finished_at),
                error_message=row.error_message,
            )
            for row in recent_rows
        ],
        index=DashboardStorageIndex(**index_metadata),
    )


def _build_alerts(runs: DashboardRunsSection, storage: DashboardStorageSection) -> list[DashboardAlert]:
    alerts: list[DashboardAlert] = []
    for run in runs.recent:
        if run.status == "failed":
            alerts.append(
                DashboardAlert(
                    id=f"crawler-run-{run.id}",
                    title=f"采集运行失败：{run.task_name}",
                    description=run.error or "采集运行失败",
                    severity="error",
                    source="crawler",
                    target_path=f"/crawler/runs/{run.id}",
                    occurred_at=run.finished_at or run.created_at,
                )
            )
    for task in storage.recent_tasks:
        if task.status == "failed":
            alerts.append(
                DashboardAlert(
                    id=f"storage-task-{task.id}",
                    title=f"存储任务失败：{task.display_name}",
                    description=task.error_message or "存储任务失败",
                    severity="error",
                    source="storage",
                    target_path=f"/storage/tasks/{task.id}",
                    occurred_at=task.finished_at or task.created_at,
                )
            )
    for index_error in storage.index.errors:
        path = str(index_error.get("path") or "存储索引")
        message = str(index_error.get("error") or "索引错误")
        alerts.append(
            DashboardAlert(
                id=f"storage-index-{len(alerts)}",
                title=f"存储索引错误：{path}",
                description=message,
                severity="error",
                source="storage.index",
                target_path="/storage/config",
                occurred_at=storage.index.completed_at,
            )
        )
    return alerts[:RECENT_LIMIT]


def derive_system_status(draft: DashboardOverviewDraft) -> SystemStatus:
    if (
        draft.failed_run_count > 0
        or draft.failed_storage_count > 0
        or draft.index_status == "failed"
        or len(draft.index_errors) > 0
    ):
        return "error"
    if (
        int(draft.queue_status.get("queue_size") or 0) > 0
        or bool(draft.queue_status.get("stop_requested"))
        or draft.index_status == "never_built"
        or draft.stopped_runtime_count > 0
    ):
        return "warning"
    if bool(draft.queue_status.get("is_running")) or draft.running_runtime_count > 0 or draft.index_status == "running":
        return "busy"
    return "healthy"


def build_dashboard_overview(
    *,
    db: Session,
    owner_id: uuid.UUID,
    queue_status: dict,
    index_metadata: dict,
) -> DashboardOverview:
    partial_errors: list[PartialError] = []
    crawler = _safe_section(
        "crawler",
        partial_errors,
        DashboardCrawlerSection(queue=DashboardQueueStatus(**queue_status)),
        lambda: _build_crawler_section(db, owner_id, queue_status),
    )
    runs = _safe_section("runs", partial_errors, DashboardRunsSection(), lambda: _build_runs_section(db, owner_id))
    content = _safe_section("content", partial_errors, DashboardContentSection(), lambda: _build_content_section(db))
    storage = _safe_section(
        "storage",
        partial_errors,
        DashboardStorageSection(index=DashboardStorageIndex(**index_metadata)),
        lambda: _build_storage_section(db, owner_id, index_metadata),
    )
    alerts = _build_alerts(runs, storage)
    failed_run_count = sum(item.count for item in runs.status_distribution if item.status == "failed")
    failed_storage_count = sum(item.count for item in storage.task_status_distribution if item.status == "failed")
    draft = DashboardOverviewDraft(
        queue_status=queue_status,
        index_status=storage.index.status,
        index_errors=storage.index.errors,
        failed_run_count=failed_run_count,
        failed_storage_count=failed_storage_count,
        stopped_runtime_count=crawler.runtime_stats.stopped,
        running_runtime_count=crawler.runtime_stats.running,
    )
    return DashboardOverview(
        system_status=derive_system_status(draft),
        refreshed_at=datetime.now(timezone.utc).isoformat(),
        crawler=crawler,
        runs=runs,
        content=content,
        storage=storage,
        alerts=alerts,
        partial_errors=partial_errors,
    )
