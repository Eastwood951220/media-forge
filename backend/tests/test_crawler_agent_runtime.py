import asyncio
import uuid
from datetime import datetime, UTC
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentEvent, CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.constants import AGENT_PROTOCOL_VERSION, AGENT_REQUIRED_CAPABILITIES
from backend.app.modules.crawler.agent.dispatch import notify_work_item_available
from backend.app.modules.crawler.agent.errors import AgentUnavailableError, AgentWorkTimeoutError
from backend.app.modules.crawler.agent.parser_bridge import AgentPageSnapshot, parse_agent_detail_snapshot
from backend.app.modules.crawler.agent.registry import agent_registry
from backend.app.modules.crawler.agent.runtime import execute_agent_crawl
from backend.app.modules.crawler.runs import logs as run_logs
from shared.database.models.content import Movie


class AgentRuntimeState:
    def __init__(self, stopped: bool = False) -> None:
        self.stopped = stopped
        self.progress: dict[str, int] = {}

    def is_stop_requested(self, run_id: str) -> bool:
        return self.stopped

    def write_progress(self, run_id: str, progress: dict[str, int]) -> None:
        self.progress = dict(progress)


def make_agent_task_and_run(db_session) -> tuple[CrawlTask, CrawlRun]:
    task = CrawlTask(id=uuid.uuid4(), name="agent-task", owner_id=uuid.uuid4(), is_skip=False)
    task.urls = [
        CrawlTaskUrl(
            position=0,
            url="https://javdb.com/actors/a",
            url_type="actors",
            final_url="https://javdb.com/actors/a",
            source="javdb",
            url_name="Actor A",
        ),
    ]
    db_session.add(task)
    db_session.flush()
    run = CrawlRun(
        task_id=task.id,
        task_name=task.name,
        status="running",
        crawl_mode="incremental",
        queued_at=datetime.now(),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(run)
    return task, run


def create_online_agent(db_session, owner_id) -> CrawlerAgent:
    agent = CrawlerAgent(
        owner_id=owner_id,
        token_hash="hash",
        status="online",
        name="Chrome Agent",
        protocol_version=AGENT_PROTOCOL_VERSION,
        last_seen_at=datetime.now(UTC),
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)

    # Register a ready connection in the registry so _ensure_online_agent passes
    conn, _replaced = agent_registry.connect(
        agent_id=str(agent.id), owner_id=str(agent.owner_id), websocket=MagicMock()
    )
    agent_registry.mark_ready(
        str(agent.id),
        conn.generation,
        protocol_version=AGENT_PROTOCOL_VERSION,
        capabilities=set(AGENT_REQUIRED_CAPABILITIES),
    )
    return agent


class WakeupSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def test_execute_agent_crawl_fails_fast_when_agent_offline(db_session, tmp_path, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))

    with pytest.raises(AgentUnavailableError, match="Chrome Agent 未在线"):
        execute_agent_crawl(db_session, run, task, AgentRuntimeState())

    logs = run_logs.load_run_logs(str(run.id))
    assert any("Chrome Agent 未在线" in entry["message"] for entry in logs)
    error_entries = [entry for entry in logs if entry["level"] == "ERROR"]
    assert any("Chrome Agent 未在线" in entry["message"] for entry in error_entries)


def test_agent_detail_snapshot_parses_full_detail_fragment() -> None:
    snapshot = AgentPageSnapshot(
        page_kind="detail",
        url="https://javdb.com/v/abc001",
        fragments={
            "detail": """
              <div class="video-detail">
                <h2 class="title is-4">
                  <strong>ABC-001</strong>
                  <strong class="current-title">ABC title</strong>
                </h2>
                <nav class="movie-panel-info">
                  <div class="panel-block"><strong>日期:</strong><span>2026-01-02</span></div>
                </nav>
              </div>
            """,
            "title": "",
            "movie_panel": "",
        },
    )

    detail = parse_agent_detail_snapshot(snapshot)

    assert detail["code"] == "ABC-001"
    assert detail["source_name"] == "ABC title"


def test_execute_agent_crawl_list_phase_creates_detail_tasks_from_snapshot(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)

    def fake_wait(db, item, **kwargs):
        item.status = "completed"
        item.result_json = {
            "tasks": [
                {
                    "code": "ABC-001",
                    "url": "https://javdb.com/v/abc001",
                    "name": "ABC title",
                    "_task_url": "https://javdb.com/actors/a",
                    "_task_final_url": "https://javdb.com/actors/a",
                    "_task_url_type": "actors",
                    "_task_url_name": "Actor A",
                    "_task_source": "javdb",
                }
            ]
        }
        db.commit()
        db.refresh(item)
        return item

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)
    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime._run_agent_detail_phase", lambda *args, **kwargs: None)

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState())

    work_items = db_session.query(CrawlerAgentWorkItem).filter(CrawlerAgentWorkItem.run_id == run.id).all()
    rows = db_session.scalars(select(CrawlRunDetailTask).where(CrawlRunDetailTask.run_id == run.id)).all()
    assert len(work_items) == 1
    assert work_items[0].page_kind == "list"
    assert work_items[0].url == "https://javdb.com/actors/a"
    assert len(rows) == 1
    assert rows[0].code == "ABC-001"
    assert rows[0].status == "pending_crawl"
    assert rows[0].source_url_name == "Actor A"
    assert result["total_tasks"] == 1


class FakePipeline:
    def process_item(self, item, task_name=None, task_id=None):
        return {**item, "source_task_id": task_id}


def seed_pending_detail(db_session, run, task, code: str | None = None) -> CrawlRunDetailTask:
    detail = CrawlRunDetailTask(
        run_id=run.id,
        task_name=task.name,
        code=code,
        source_url="https://javdb.com/v/abc001",
        source_name="ABC title",
        source_url_name="Actor A",
        task_url="https://javdb.com/actors/a",
        task_final_url="https://javdb.com/actors/a",
        task_url_type="actors",
        status="pending_crawl",
        created_at=datetime.now(),
    )
    db_session.add(detail)
    db_session.commit()
    db_session.refresh(detail)
    return detail


def test_execute_agent_crawl_detail_phase_saves_movie(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)
    detail = seed_pending_detail(db_session, run, task)

    def fake_wait(db, item, **kwargs):
        item.status = "completed"
        item.result_json = {
            "detail": {
                "code": "ABC-001",
                "source_name": "ABC title",
                "source_url": "https://javdb.com/v/abc001",
            }
        }
        db.commit()
        db.refresh(item)
        return item

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)
    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.build_pipeline", lambda: FakePipeline())

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState(), detail_only=True)

    db_session.refresh(detail)
    movie = db_session.scalar(select(Movie).where(Movie.code == "ABC-001"))
    assert result["saved"] == 1
    assert detail.status == "saved"
    assert detail.item_data["code"] == "ABC-001"
    assert movie is not None
    assert str(task.id) in [str(value) for value in movie.source_task_ids]


def test_execute_agent_crawl_detail_parse_failure_marks_detail_failed(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)
    detail = seed_pending_detail(db_session, run, task)

    def fake_wait(db, item, **kwargs):
        item.status = "failed"
        item.error_reason = "missing_required_fragments:title"
        db.commit()
        db.refresh(item)
        raise AgentWorkFailedError(item.error_reason)

    from backend.app.modules.crawler.agent.errors import AgentWorkFailedError
    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState(), detail_only=True)

    db_session.refresh(detail)
    assert result["failed"] == 1
    assert detail.status == "crawl_failed"
    assert "missing_required_fragments:title" in detail.error


def test_execute_agent_crawl_timeout_fails_list_run(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)

    def fake_wait(db, item, **kwargs):
        raise AgentWorkTimeoutError()

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)

    with pytest.raises(AgentWorkTimeoutError, match="Chrome Agent 执行超时"):
        execute_agent_crawl(db_session, run, task, AgentRuntimeState())


def test_execute_agent_crawl_stop_while_waiting_returns_stopped(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)

    def fake_wait(db, item, **kwargs):
        from backend.app.modules.crawler.agent.errors import AgentWorkStopped
        raise AgentWorkStopped()

    monkeypatch.setattr("backend.app.modules.crawler.agent.runtime.wait_for_work_item_result", fake_wait)

    result = execute_agent_crawl(db_session, run, task, AgentRuntimeState(stopped=True))

    assert result["stopped"] is True


def test_agent_unavailable_error_replaces_placeholder_message(db_session, tmp_path, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    monkeypatch.setattr(run_logs, "RUN_LOG_DIR", str(tmp_path))

    with pytest.raises(AgentUnavailableError) as exc_info:
        execute_agent_crawl(db_session, run, task, AgentRuntimeState())

    assert "JavDB Agent runtime is configured but Agent work execution is not available" not in str(exc_info.value)
    assert "Chrome Agent 未在线" in str(exc_info.value)


def test_notify_work_item_available_sends_task_available(db_session) -> None:
    task, run = make_agent_task_and_run(db_session)
    agent = create_online_agent(db_session, task.owner_id)
    socket = WakeupSocket()
    conn, _ = agent_registry.connect(
        agent_id=str(agent.id),
        owner_id=str(agent.owner_id),
        websocket=socket,
    )
    agent_registry.mark_ready(
        str(agent.id),
        conn.generation,
        protocol_version=AGENT_PROTOCOL_VERSION,
        capabilities=set(AGENT_REQUIRED_CAPABILITIES),
    )
    item = CrawlerAgentWorkItem(
        owner_id=task.owner_id,
        run_id=run.id,
        task_id=task.id,
        page_kind="list",
        url="https://javdb.com/actors/a",
        status="pending",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    result = asyncio.run(
        notify_work_item_available(
            db_session,
            owner_id=task.owner_id,
            work_item=item,
        )
    )

    assert result.status == "sent"
    assert socket.sent[-1]["type"] == "task.available"
    assert socket.sent[-1]["payload"]["work_item_id"] == str(item.id)
    assert socket.sent[-1]["payload"]["run_id"] == str(run.id)
    assert socket.sent[-1]["payload"]["page_kind"] == "list"

    event = (
        db_session.query(CrawlerAgentEvent)
        .filter(CrawlerAgentEvent.work_item_id == item.id)
        .filter(CrawlerAgentEvent.event_type == "task_available_sent")
        .one()
    )
    assert event.source == "backend"
    assert event.level == "info"


def test_notify_work_item_available_records_no_ready_agent(db_session) -> None:
    task, run = make_agent_task_and_run(db_session)
    item = CrawlerAgentWorkItem(
        owner_id=task.owner_id,
        run_id=run.id,
        task_id=task.id,
        page_kind="detail",
        url="https://javdb.com/v/abc001",
        status="pending",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    result = asyncio.run(
        notify_work_item_available(
            db_session,
            owner_id=task.owner_id,
            work_item=item,
        )
    )

    assert result.status == "no_ready_agent"
    event = (
        db_session.query(CrawlerAgentEvent)
        .filter(CrawlerAgentEvent.work_item_id == item.id)
        .filter(CrawlerAgentEvent.event_type == "task_available_no_ready_agent")
        .one()
    )
    assert event.level == "warning"
    assert event.details_json == {"page_kind": "detail", "status": "no_ready_agent"}


def test_execute_agent_crawl_notifies_agent_after_list_work_item(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)
    calls: list[tuple[uuid.UUID, str]] = []

    async def fake_notify(db, *, owner_id, work_item):
        calls.append((owner_id, work_item.page_kind))

        class Result:
            status = "sent"
            message = "Chrome Agent 已通知领取任务"

        return Result()

    def fake_wait(db, item, **kwargs):
        item.status = "completed"
        item.result_json = {"tasks": []}
        db.commit()
        db.refresh(item)
        return item

    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.runtime.notify_work_item_available",
        fake_notify,
    )
    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.runtime.wait_for_work_item_result",
        fake_wait,
    )
    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.runtime._run_agent_detail_phase",
        lambda *args, **kwargs: None,
    )

    execute_agent_crawl(db_session, run, task, AgentRuntimeState())

    assert calls == [(task.owner_id, "list")]


def test_execute_agent_crawl_notifies_agent_after_detail_work_item(db_session, monkeypatch) -> None:
    task, run = make_agent_task_and_run(db_session)
    create_online_agent(db_session, task.owner_id)
    seed_pending_detail(db_session, run, task)
    calls: list[tuple[uuid.UUID, str]] = []

    async def fake_notify(db, *, owner_id, work_item):
        calls.append((owner_id, work_item.page_kind))

        class Result:
            status = "sent"
            message = "Chrome Agent 已通知领取任务"

        return Result()

    def fake_wait(db, item, **kwargs):
        item.status = "completed"
        item.result_json = {
            "detail": {
                "code": "ABC-001",
                "source_name": "ABC title",
                "source_url": "https://javdb.com/v/abc001",
            }
        }
        db.commit()
        db.refresh(item)
        return item

    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.runtime.notify_work_item_available",
        fake_notify,
    )
    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.runtime.wait_for_work_item_result",
        fake_wait,
    )
    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.runtime.build_pipeline",
        lambda: FakePipeline(),
    )
    monkeypatch.setattr(
        "backend.app.modules.crawler.agent.runtime.upsert_movie_with_magnets",
        lambda *args, **kwargs: None,
    )

    execute_agent_crawl(db_session, run, task, AgentRuntimeState(), detail_only=True)

    assert calls == [(task.owner_id, "detail")]
