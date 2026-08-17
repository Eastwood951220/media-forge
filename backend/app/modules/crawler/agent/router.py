from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentSession, CrawlerAgentWorkItem
from backend.app.modules.crawler.agent.auth import (
    create_agent_session_id,
    create_agent_token,
    hash_agent_token,
    session_is_expired,
    verify_agent_token,
)
from backend.app.modules.crawler.agent.constants import (
    AGENT_HEARTBEAT_FRESH_SECONDS,
    AGENT_HEARTBEAT_INTERVAL_SECONDS,
    AGENT_MAX_ATTEMPTS,
    AGENT_MINIMUM_PROTOCOL_VERSION,
    AGENT_PROTOCOL_VERSION,
    AGENT_TASK_POLL_INTERVAL_MS,
)
from backend.app.modules.crawler.agent.registry import agent_registry
from backend.app.modules.crawler.agent.diagnostics import (
    delete_operational_events,
    list_agent_events,
    serialize_agent_event,
)
from backend.app.modules.crawler.agent.errors import agent_error_message
from backend.app.modules.crawler.agent.protocol import AgentProtocolContext, dispatch_agent_message, handle_agent_hello
from backend.app.modules.crawler.agent.schemas import (
    AgentEventPageResponse,
    AgentSessionCreateRequest,
    AgentSessionCreateResponse,
    AgentStatusResponse,
    AgentTokenRotateResponse,
)
from backend.app.modules.crawler.agent.work_items import release_agent_work_items
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/agent", tags=["crawler-agent"])


def _serialize_work_item(item: CrawlerAgentWorkItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "run_id": str(item.run_id),
        "task_id": str(item.task_id) if item.task_id else None,
        "detail_task_id": str(item.detail_task_id) if item.detail_task_id else None,
        "url_entry_id": str(item.url_entry_id) if item.url_entry_id else None,
        "page_kind": item.page_kind,
        "url": item.url,
        "status": item.status,
        "attempt": item.attempt,
        "error_reason": item.error_reason,
        "queued_at": item.queued_at.isoformat() if item.queued_at else None,
        "assigned_at": item.assigned_at.isoformat() if item.assigned_at else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "assigned_agent_id": str(item.assigned_agent_id) if item.assigned_agent_id else None,
    }


def _status(agent: CrawlerAgent | None, db: Session) -> dict[str, Any]:
    if agent is None:
        return AgentStatusResponse(status="not_configured").model_dump(mode="json")

    fresh_after = datetime.now(UTC) - timedelta(seconds=AGENT_HEARTBEAT_FRESH_SECONDS)
    last_seen = agent.last_seen_at or datetime.min.replace(tzinfo=UTC)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)

    current_item = (
        db.query(CrawlerAgentWorkItem)
        .filter(
            CrawlerAgentWorkItem.assigned_agent_id == agent.id,
            CrawlerAgentWorkItem.status.in_(["assigned", "running"]),
        )
        .order_by(CrawlerAgentWorkItem.created_at.desc())
        .first()
    )

    pending_count = (
        db.query(CrawlerAgentWorkItem)
        .filter(
            CrawlerAgentWorkItem.owner_id == agent.owner_id,
            CrawlerAgentWorkItem.status == "pending",
        )
        .count()
    )
    active_count = (
        db.query(CrawlerAgentWorkItem)
        .filter(
            CrawlerAgentWorkItem.owner_id == agent.owner_id,
            CrawlerAgentWorkItem.status.in_(["assigned", "running"]),
        )
        .count()
    )

    derived_status = agent.status
    if agent.status in ("online", "busy") and last_seen < fresh_after:
        derived_status = "offline"
    if not agent_registry.has_ready_owner(str(agent.owner_id)):
        derived_status = "offline"

    if derived_status == "offline" and agent.status in ("online", "busy"):
        agent.status = "offline"
        db.commit()

    return AgentStatusResponse(
        status=derived_status,
        agent_id=str(agent.id),
        name=agent.name,
        protocol_version=agent.protocol_version,
        connected_at=agent.connected_at,
        last_seen_at=agent.last_seen_at,
        last_cookie_sync_at=agent.last_cookie_sync_at,
        version=agent.version,
        current_work_item=_serialize_work_item(current_item) if current_item else None,
        pending_count=pending_count,
        active_count=active_count,
    ).model_dump(mode="json")


@router.get("/status")
def get_agent_status(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    agent = (
        db.query(CrawlerAgent)
        .filter(CrawlerAgent.owner_id == current_user.id)
        .order_by(CrawlerAgent.created_at.desc())
        .first()
    )
    return success(data=_status(agent, db))


@router.post("/token/rotate")
def rotate_agent_token(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    raw_token = create_agent_token()
    agent = (
        db.query(CrawlerAgent)
        .filter(CrawlerAgent.owner_id == current_user.id)
        .order_by(CrawlerAgent.created_at.desc())
        .first()
    )
    if agent is None:
        agent = CrawlerAgent(owner_id=current_user.id, token_hash=hash_agent_token(raw_token), status="offline")
        db.add(agent)
    else:
        agent.token_hash = hash_agent_token(raw_token)
        agent.status = "offline"
    db.commit()
    db.refresh(agent)
    payload = AgentTokenRotateResponse(token=raw_token, status=AgentStatusResponse(**_status(agent, db)))
    return success(data=payload.model_dump(mode="json"))


@router.post("/sessions")
def create_agent_session(body: AgentSessionCreateRequest, db: Session = Depends(get_db)) -> dict:
    agents = db.query(CrawlerAgent).all()
    agent = next((item for item in agents if verify_agent_token(body.token, item.token_hash)), None)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")
    session_id = create_agent_session_id()
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    session = CrawlerAgentSession(
        agent_id=agent.id, owner_id=agent.owner_id, session_id=session_id, expires_at=expires_at
    )
    agent.version = body.version or agent.version
    agent.name = body.name or agent.name
    db.add(session)
    db.commit()
    return success(data=AgentSessionCreateResponse(session=session_id, expires_at=expires_at).model_dump(mode="json"))


@router.get("/events")
def list_agent_event_history(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    cursor: str | None = Query(default=None),
    size: int = Query(default=50, ge=1, le=100),
    level: str | None = Query(default=None),
    source: str | None = Query(default=None),
    phase: str | None = Query(default=None),
    work_item_id: uuid.UUID | None = Query(default=None),
    from_time: datetime | None = Query(default=None),
    to_time: datetime | None = Query(default=None),
) -> dict:
    page = list_agent_events(
        db,
        owner_id=current_user.id,
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


@router.delete("/events/operational")
def clear_operational_agent_events(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    deleted = delete_operational_events(db, owner_id=current_user.id)
    db.commit()
    return success(data={"deleted": deleted})


@router.websocket("/ws")
async def agent_ws(
    websocket: WebSocket,
    session: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    await websocket.accept()
    agent_session = (
        db.query(CrawlerAgentSession)
        .filter(CrawlerAgentSession.session_id == session)
        .first()
    )
    if agent_session is None or session_is_expired(agent_session.expires_at):
        await websocket.send_json({
            "id": "server_invalid_session",
            "type": "server.error",
            "payload": {"reason": "invalid_session"},
        })
        await websocket.close()
        return
    agent = db.get(CrawlerAgent, agent_session.agent_id)
    if agent is None:
        await websocket.send_json({
            "id": "server_missing_agent",
            "type": "server.error",
            "payload": {"reason": "missing_agent"},
        })
        await websocket.close()
        return
    # Register connection but stay offline until handshake
    connection, _replaced = agent_registry.connect(
        agent_id=str(agent.id), owner_id=str(agent.owner_id), websocket=websocket
    )
    ctx = AgentProtocolContext(
        websocket=websocket,
        db=db,
        agent=agent,
        connection=connection,
        registry=agent_registry,
    )
    handshake_complete = False
    await websocket.send_json({
        "id": "server_hello",
        "type": "server.hello",
        "payload": {
            "agent_id": str(agent.id),
            "protocol_version": AGENT_PROTOCOL_VERSION,
            "minimum_protocol_version": AGENT_MINIMUM_PROTOCOL_VERSION,
            "heartbeat_interval_seconds": AGENT_HEARTBEAT_INTERVAL_SECONDS,
            "heartbeat_fresh_seconds": AGENT_HEARTBEAT_FRESH_SECONDS,
            "task_poll_interval_ms": AGENT_TASK_POLL_INTERVAL_MS,
            "max_attempts": AGENT_MAX_ATTEMPTS,
        },
    })
    try:
        while True:
            message = await websocket.receive_json()

            # ── Handshake gate ──────────────────────────────────────────
            if message.get("type") == "agent.hello":
                ok = await handle_agent_hello(ctx, message)
                if ok:
                    handshake_complete = True
                else:
                    break  # connection closed by handler
                continue

            if not handshake_complete:
                await websocket.send_json({
                    "id": f"err_{message.get('id')}",
                    "type": "server.error",
                    "payload": {"reason": "handshake_required"},
                })
                continue

            # ── All post-handshake messages go through dispatch ────────
            try:
                await dispatch_agent_message(ctx, message)
            except Exception as exc:
                await websocket.send_json({
                    "id": f"err_{message.get('id')}",
                    "type": "server.error",
                    "payload": {"reason": agent_error_message(str(exc))},
                })

    except WebSocketDisconnect:
        pass
    finally:
        # Disconnect cleanup: release this agent's active work items
        release_agent_work_items(
            db, agent_id=str(agent.id), now=datetime.now(UTC)
        )
        agent_registry.disconnect_if_current(str(agent.id), connection.generation)
        if agent.status not in ("upgrade_required",):
            agent.status = "offline"
        db.commit()