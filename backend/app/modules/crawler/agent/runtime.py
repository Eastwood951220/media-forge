from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.errors import (
    AgentRuntimeError,
    AgentUnavailableError,
    AgentWorkStopped,
)
from backend.app.modules.crawler.agent.parser_bridge import (
    AgentPageSnapshot,
    parse_agent_detail_snapshot,
    parse_agent_list_snapshot,
)
from backend.app.modules.crawler.agent.work_items import (
    create_work_item,
    is_work_item_completable,
    mark_work_item_failed,
    wait_for_work_item_result,
)
from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config
from backend.app.modules.crawler.runtime.detail_queue import upsert_detail_task
from backend.app.modules.crawler.runtime.events import append_run_log_for_run, publish_run_detail_updated
from backend.app.modules.crawler.runtime.source_task_names import find_existing_movie_codes


def complete_work_item_from_snapshot(
    db: Session,
    *,
    work_item_id: str,
    snapshot: AgentPageSnapshot,
) -> CrawlerAgentWorkItem:
    item = db.get(CrawlerAgentWorkItem, uuid.UUID(work_item_id))
    if item is None:
        raise ValueError("agent_work_item_not_found")
    if not is_work_item_completable(item):
        return item
    try:
        if item.page_kind == "list":
            item.result_json = {"tasks": parse_agent_list_snapshot(snapshot)}
        elif item.page_kind == "detail":
            item.result_json = {"detail": parse_agent_detail_snapshot(snapshot)}
        else:
            raise ValueError(f"unsupported_page_kind:{item.page_kind}")
    except Exception as exc:
        mark_work_item_failed(db, item, str(exc))
        raise
    item.status = "completed"
    item.error_reason = None
    item.claimed_until = None
    db.commit()
    db.refresh(item)
    return item


def _ensure_online_agent(db: Session, owner_id: uuid.UUID) -> CrawlerAgent:
    agent = (
        db.query(CrawlerAgent)
        .filter(CrawlerAgent.owner_id == owner_id)
        .filter(CrawlerAgent.status == "online")
        .order_by(CrawlerAgent.last_seen_at.desc(), CrawlerAgent.created_at.desc())
        .first()
    )
    if agent is None:
        raise AgentUnavailableError()
    return agent


def _selected_urls(task: CrawlTask, selected_task_url_ids: list[uuid.UUID] | None):
    task_urls = list(task.urls)
    if selected_task_url_ids is not None:
        selected_ids = {uuid.UUID(str(url_id)) for url_id in selected_task_url_ids}
        task_urls = [url for url in task_urls if url.id in selected_ids]
        if not task_urls:
            raise ValueError("选择的 URL 不属于该任务")
    return task_urls


def _should_persist_agent_list_item(run: CrawlRun, item: dict[str, Any]) -> bool:
    if run.crawl_mode != "incremental":
        return True
    return not (item.get("status") == "skipped" and item.get("reason") == "already_exists")


def _append_existing_source_task_ids(db: Session, task: CrawlTask, items: list[dict[str, Any]]) -> None:
    from backend.app.modules.content.movies.persistence import append_source_task_ids_for_codes

    codes = [str(item.get("code")) for item in items if item.get("code")]
    if not codes:
        return
    existing_codes = find_existing_movie_codes(db, codes)
    if existing_codes:
        append_source_task_ids_for_codes(db, existing_codes, task.id)


def _run_agent_list_phase(
    db: Session,
    run: CrawlRun,
    task: CrawlTask,
    runtime,
    config,
    *,
    selected_task_url_ids: list[uuid.UUID] | None = None,
) -> None:
    for url_entry in _selected_urls(task, selected_task_url_ids):
        if url_entry.source != "javdb":
            continue
        item = create_work_item(
            db,
            owner_id=task.owner_id,
            run_id=run.id,
            task_id=task.id,
            url_entry_id=url_entry.id,
            page_kind="list",
            url=url_entry.final_url or url_entry.url,
        )
        append_run_log_for_run(db, run, f"Chrome Agent 列表任务已创建: {item.url}", "INFO", agent_task_id=str(item.id))
        completed = wait_for_work_item_result(
            db,
            item,
            runtime=runtime,
            run_id=str(run.id),
            timeout_seconds=float(config.SECURITY_WAIT_SECONDS),
        )
        tasks = list((completed.result_json or {}).get("tasks") or [])
        for task_info in tasks:
            task_info.setdefault("_task_url", url_entry.url)
            task_info.setdefault("_task_final_url", url_entry.final_url)
            task_info.setdefault("_task_url_type", url_entry.url_type)
            task_info.setdefault("_task_url_name", url_entry.url_name)
            task_info.setdefault("_task_source", url_entry.source)
        _append_existing_source_task_ids(db, task, tasks)
        persisted = []
        for task_info in tasks:
            if not _should_persist_agent_list_item(run, task_info):
                continue
            detail = upsert_detail_task(db, run=run, task_name=task.name, item=task_info)
            if detail is not None:
                persisted.append(detail)
        db.commit()
        publish_run_detail_updated(db, run, persisted, refresh_tasks=True, reason="agent_list_completed")
        append_run_log_for_run(db, run, f"Chrome Agent 列表解析完成: 新增详情子任务 {len(persisted)} 条", "INFO")


def _build_agent_result(db: Session, run: CrawlRun) -> dict[str, Any]:
    from backend.app.models.crawl_run import CrawlRunDetailTask

    total = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id).count()
    saved = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "saved").count()
    failed = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status.in_(["crawl_failed", "save_failed"])).count()
    skipped = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run.id, CrawlRunDetailTask.status == "skipped").count()
    return {
        "total_tasks": total,
        "completed_tasks": saved,
        "failed_tasks": failed,
        "skipped_tasks": skipped,
        "saved": saved,
        "failed": failed,
        "skipped": skipped,
    }


def _run_agent_detail_phase(db: Session, run: CrawlRun, task: CrawlTask, runtime, config) -> None:
    return None


def execute_agent_crawl(
    db: Session,
    run,
    task,
    runtime,
    *,
    detail_only: bool = False,
    selected_task_url_ids: list | None = None,
) -> dict:
    try:
        _ensure_online_agent(db, task.owner_id)
        if not detail_only:
            _run_agent_list_phase(
                db,
                run,
                task,
                runtime,
                read_crawler_runtime_config(),
                selected_task_url_ids=selected_task_url_ids,
            )
        _run_agent_detail_phase(db, run, task, runtime, read_crawler_runtime_config())
    except AgentWorkStopped:
        return {**_build_agent_result(db, run), "stopped": True}
    except AgentRuntimeError as exc:
        append_run_log_for_run(db, run, str(exc), "ERROR")
        raise

    return _build_agent_result(db, run)
