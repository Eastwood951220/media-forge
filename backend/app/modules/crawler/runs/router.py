import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import cast, func, or_, String, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, noload

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.crawler.runs.logs import load_run_logs
from backend.app.models.crawler_agent import CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.diagnostics import list_agent_events, serialize_agent_event
from backend.app.modules.crawler.runs.schemas import (
    AgentWorkItemPage,
    AgentWorkItemRead,
    AgentWorkSummary,
    CrawlRunDetailRead,
    CrawlRunDetailTaskListItem,
    CrawlRunListItem,
    RunDetailRetryRequest,
    RunTaskPage,
    RunTaskSummary,
    _serialize_run_detail_task,
    accepted_run_action,
    serialize_run,
)
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.tasks.runtime_status import publish_task_status_for_task_id
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/crawler/runs", tags=["crawler-runs"])


def _hidden_incremental_existing_skip_filter(run: CrawlRun):
    if run.crawl_mode != "incremental":
        return None
    return or_(
        CrawlRunDetailTask.status != "skipped",
        CrawlRunDetailTask.error != "already_exists",
        CrawlRunDetailTask.error.is_(None),
    )


def _visible_run_detail_task_query(db: Session, run: CrawlRun):
    query = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id)
    hidden_filter = _hidden_incremental_existing_skip_filter(run)
    if hidden_filter is not None:
        query = query.filter(hidden_filter)
    return query


def _json_item_text(column, key: str, dialect_name: str):
    if dialect_name == "postgresql":
        return type_coerce(column, JSONB)[key].astext
    return func.json_extract(column, f"$.{key}")


def _run_task_summary(db: Session, run: CrawlRun) -> dict:
    query = _visible_run_detail_task_query(db, run)
    total = query.count()
    counts = (
        query.with_entities(CrawlRunDetailTask.status, func.count(CrawlRunDetailTask.id))
        .group_by(CrawlRunDetailTask.status)
        .all()
    )
    summary = RunTaskSummary(total=total)
    for status, count in counts:
        if hasattr(summary, status):
            setattr(summary, status, count)
    summary.completed = summary.saved + summary.skipped
    summary.waiting = summary.pending_crawl
    summary.failed = summary.crawl_failed + summary.save_failed
    return summary.model_dump(mode="json")


def _owned_agent_work_items(db: Session, run_id: uuid.UUID):
    return (
        db.query(CrawlerAgentWorkItem)
        .filter(CrawlerAgentWorkItem.run_id == run_id)
        .order_by(CrawlerAgentWorkItem.created_at.asc(), CrawlerAgentWorkItem.id.asc())
        .all()
    )


def _agent_work_summary(items: list[CrawlerAgentWorkItem]) -> dict:
    summary = AgentWorkSummary()
    for item in items:
        summary.total += 1
        if item.status == "pending":
            summary.pending += 1
        elif item.status in {"assigned", "running"}:
            summary.active += 1
        elif item.status == "completed":
            summary.completed += 1
        elif item.status == "failed":
            summary.failed += 1
    return summary.model_dump(mode="json")


def _owned_run_query(
    db: Session,
    owner_id: uuid.UUID,
    *,
    task_id: uuid.UUID | None = None,
    status_filter: str | None = None,
):
    query = (
        db.query(CrawlRun)
        .join(CrawlTask, CrawlRun.task_id == CrawlTask.id)
        .options(noload(CrawlRun.detail_tasks))
        .filter(CrawlTask.owner_id == owner_id)
    )
    if task_id is not None:
        query = query.filter(CrawlRun.task_id == task_id)
    if status_filter is not None:
        query = query.filter(CrawlRun.status == status_filter)
    return query


@router.get("")
def list_runs(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    task_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict:
    query = _owned_run_query(db, current_user.id, task_id=task_id, status_filter=status_filter)
    total = query.count()
    rows = (
        query
        .order_by(CrawlRun.created_at.desc(), CrawlRun.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return paginated(
        rows=[serialize_run(r, CrawlRunListItem) for r in rows],
        total=total,
    )


@router.get("/{run_id}")
def get_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    payload = serialize_run(run, CrawlRunDetailRead)
    payload["logs"] = []
    return success(data=payload)


@router.get("/{run_id}/logs")
def get_run_logs(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return success(data=load_run_logs(str(run_id)))


@router.get("/{run_id}/tasks")
def list_run_tasks(
    run_id: uuid.UUID,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1, description="Page number, 1-based"),
    size: int = Query(default=50, ge=1, le=200, description="Page size"),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    query = _visible_run_detail_task_query(db, run)
    if status_filter is not None:
        query = query.filter(CrawlRunDetailTask.status == status_filter)
    if keyword:
        dialect_name = db.bind.dialect.name
        query = query.filter(
            CrawlRunDetailTask.code.ilike(f"%{keyword}%")
            | CrawlRunDetailTask.source_name.ilike(f"%{keyword}%")
            | CrawlRunDetailTask.source_url_name.ilike(f"%{keyword}%")
            | cast(_json_item_text(CrawlRunDetailTask.item_data, "code", dialect_name), String).ilike(f"%{keyword}%")
            | cast(_json_item_text(CrawlRunDetailTask.item_data, "source_name", dialect_name), String).ilike(f"%{keyword}%")
            | cast(_json_item_text(CrawlRunDetailTask.item_data, "name", dialect_name), String).ilike(f"%{keyword}%")
        )
    total = query.count()
    offset = (page - 1) * size
    rows = query.order_by(CrawlRunDetailTask.created_at.asc()).offset(offset).limit(size).all()
    payload = paginated(
        rows=[_serialize_run_detail_task(r) for r in rows],
        total=total,
    )
    payload["summary"] = _run_task_summary(db, run)
    return payload


@router.get("/{run_id}/agent-work-items")
def list_run_agent_work_items(
    run_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    run = _owned_run_query(db, current_user.id).filter(CrawlRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    items = _owned_agent_work_items(db, run_id)
    return success(data=AgentWorkItemPage(
        rows=[AgentWorkItemRead.model_validate(item) for item in items],
        summary=AgentWorkSummary(**_agent_work_summary(items)),
    ).model_dump(mode="json"))


@router.get("/{run_id}/agent-events")
def list_run_agent_events(
    run_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    cursor: str | None = Query(default=None),
    size: int = Query(default=50, ge=1, le=100),
    level: str | None = Query(default=None),
    source: str | None = Query(default=None),
    phase: str | None = Query(default=None),
    work_item_id: uuid.UUID | None = Query(default=None),
) -> dict:
    run = _owned_run_query(db, current_user.id).filter(CrawlRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    page = list_agent_events(
        db,
        owner_id=current_user.id,
        run_id=run.id,
        cursor=cursor,
        size=size,
        level=level,
        source=source,
        phase=phase,
        work_item_id=work_item_id,
    )
    return success(data={
        "rows": [serialize_agent_event(event) for event in page.rows],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    })


@router.post("/{run_id}/tasks/retry", status_code=status.HTTP_201_CREATED)
def retry_run_tasks(
    run_id: uuid.UUID,
    payload: RunDetailRetryRequest,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    try:
        CrawlerRunService(db, get_runtime_state()).retry_failed_details(
            run_id,
            detail_ids=payload.detail_ids,
            retry_all=payload.retry_all,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
    return success(data=accepted_run_action(run_id))


@router.delete("/{run_id}")
def delete_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="运行中任务不能删除，请先停止")
    task_id = run.task_id
    db.delete(run)
    db.commit()
    if task_id is not None:
        publish_task_status_for_task_id(db, task_id)
    return success(data=accepted_run_action(run_id))


@router.post("/{run_id}/stop")
def stop_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    try:
        CrawlerRunService(db, get_runtime_state()).stop_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success(data=accepted_run_action(run_id))


@router.post("/{run_id}/restart", status_code=status.HTTP_201_CREATED)
def restart_run(run_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    try:
        CrawlerRunService(db, get_runtime_state()).restart_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
    return success(data=accepted_run_action(run_id))
