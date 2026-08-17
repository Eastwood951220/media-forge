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
from backend.app.modules.crawler.agent.cookie_sync import AgentCookie, sync_javdb_cookies
from backend.app.modules.crawler.agent.registry import agent_registry
from backend.app.modules.crawler.agent.runtime import complete_work_item_from_snapshot
from backend.app.modules.crawler.agent.work_items import claim_next_work_item
from backend.app.modules.crawler.agent.parser_bridge import AgentPageSnapshot
from backend.app.modules.crawler.agent.schemas import (
    AgentSessionCreateRequest,
    AgentSessionCreateResponse,
    AgentStatusResponse,
    AgentTokenRotateResponse,
)
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/agent", tags=["crawler-agent"])


def _status(agent: CrawlerAgent | None) -> AgentStatusResponse:
    if agent is None:
        return AgentStatusResponse(status="not_configured")
    return AgentStatusResponse(
        status=agent.status,
        agent_id=str(agent.id),
        name=agent.name,
        last_seen_at=agent.last_seen_at,
        last_cookie_sync_at=agent.last_cookie_sync_at,
        version=agent.version,
    )


@router.get("/status")
def get_agent_status(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    agent = (
        db.query(CrawlerAgent)
        .filter(CrawlerAgent.owner_id == current_user.id)
        .order_by(CrawlerAgent.created_at.desc())
        .first()
    )
    return success(data=_status(agent).model_dump(mode="json"))


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
    payload = AgentTokenRotateResponse(token=raw_token, status=_status(agent))
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
    agent.status = "online"
    agent.last_seen_at = datetime.now(UTC)
    db.commit()
    await agent_registry.connect(
        agent_id=str(agent.id), owner_id=str(agent.owner_id), websocket=websocket
    )
    await websocket.send_json({
        "id": "server_hello",
        "type": "server.hello",
        "payload": {"agent_id": str(agent.id)},
    })
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "agent.cookie_sync":
                payload = message.get("payload") or {}
                cookies = [
                    AgentCookie.model_validate(cookie)
                    for cookie in payload.get("cookies", [])
                ]
                result = sync_javdb_cookies(cookies)
                agent.last_cookie_sync_at = datetime.now(UTC)
                agent.last_seen_at = datetime.now(UTC)
                db.commit()
                await websocket.send_json({
                    "id": f"ack_{message.get('id')}",
                    "type": "server.ack",
                    "payload": {
                        "message_id": message.get("id"),
                        "accepted": result.accepted,
                        "rejected": result.rejected,
                        "cookie_names": result.cookie_names,
                    },
                })
                continue
            if message.get("type") == "agent.heartbeat":
                await agent_registry.touch(str(agent.id))
                agent.last_seen_at = datetime.now(UTC)
                db.commit()
                await websocket.send_json({
                    "id": f"ack_{message.get('id')}",
                    "type": "server.ack",
                    "payload": {"message_id": message.get("id")},
                })
                continue
            if message.get("type") == "agent.task_request":
                item = claim_next_work_item(
                    db, owner_id=str(agent.owner_id), agent_id=str(agent.id),
                    execution_timeout_seconds=120,
                )
                if item is None:
                    await websocket.send_json({
                        "id": f"none_{message.get('id')}",
                        "type": "task.none",
                        "payload": {},
                    })
                else:
                    await websocket.send_json({
                        "id": f"task_{item.id}",
                        "type": "task.assigned",
                        "payload": {
                            "agent_task_id": str(item.id),
                            "run_id": str(item.run_id),
                            "detail_task_id": str(item.detail_task_id) if item.detail_task_id else None,
                            "url_entry_id": str(item.url_entry_id) if item.url_entry_id else None,
                            "page_kind": item.page_kind,
                            "url": item.url,
                            "attempt": item.attempt,
                        },
                    })
                continue
            if message.get("type") == "agent.page_snapshot":
                payload = message.get("payload") or {}
                if payload.get("cookies"):
                    cookies = [
                        AgentCookie.model_validate(cookie)
                        for cookie in payload.get("cookies", [])
                    ]
                    sync_javdb_cookies(cookies)
                    agent.last_cookie_sync_at = datetime.now(UTC)
                snapshot = AgentPageSnapshot.model_validate(payload["snapshot"])
                agent_task_id = str(payload["agent_task_id"])
                existing_item = db.get(CrawlerAgentWorkItem, uuid.UUID(agent_task_id))
                ignored = existing_item is None or existing_item.status not in {"pending", "assigned", "running"}
                try:
                    item = complete_work_item_from_snapshot(
                        db, work_item_id=agent_task_id, snapshot=snapshot
                    )
                except Exception as exc:
                    await websocket.send_json({
                        "id": f"err_{message.get('id')}",
                        "type": "server.error",
                        "payload": {"agent_task_id": agent_task_id, "reason": str(exc)},
                    })
                    continue
                await websocket.send_json({
                    "id": f"ack_{message.get('id')}",
                    "type": "server.ack",
                    "payload": {
                        "agent_task_id": str(item.id),
                        "ignored": ignored,
                    },
                })
                continue
    except WebSocketDisconnect:
        pass
    finally:
        await agent_registry.disconnect(str(agent.id))
        agent.status = "offline"
        db.commit()
