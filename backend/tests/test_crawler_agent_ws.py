import uuid
from datetime import datetime

import pytest
from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentEvent, CrawlerAgentSession, CrawlerAgentWorkItem
from backend.tests.conftest import TestingSessionLocal


def test_agent_status_defaults_to_offline(client, auth_headers) -> None:
    response = client.get("/api/crawler/agent/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] in {"offline", "not_configured"}
    assert "raw_token" not in data


def test_agent_session_rejects_invalid_token(client) -> None:
    response = client.post("/api/crawler/agent/sessions", json={"token": "bad-token"})

    assert response.status_code == 401


def test_agent_websocket_rejects_invalid_session(client) -> None:
    with client.websocket_connect("/api/crawler/agent/ws?session=bad-session") as websocket:
        message = websocket.receive_json()

    assert message["type"] == "server.error"
    assert message["payload"]["reason"] == "invalid_session"


def test_agent_websocket_cookie_sync_updates_status(client, auth_headers, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scraper.config.settings.COOKIE_DIR", tmp_path / "cookies")
    token_response = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_response.json()["data"]["token"]
    session_response = client.post("/api/crawler/agent/sessions", json={"token": token})
    session = session_response.json()["data"]["session"]

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        assert websocket.receive_json()["type"] == "server.hello"
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 2,
                "version": "Chrome 0.1.0",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"
        websocket.send_json({
            "id": "msg_cookie_sync",
            "type": "agent.cookie_sync",
            "payload": {
                "cookies": [
                    {
                        "name": "cf_clearance",
                        "value": "ok",
                        "domain": ".javdb.com",
                        "path": "/",
                    }
                ]
            },
        })
        message = websocket.receive_json()

    assert message["type"] == "server.ack"
    assert message["payload"]["accepted"] == 1
    status_response = client.get("/api/crawler/agent/status", headers=auth_headers)
    assert status_response.json()["data"]["last_cookie_sync_at"] is not None


def test_agent_page_snapshot_ignores_late_completed_work_item(client, auth_headers) -> None:
    token_response = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_response.json()["data"]["token"]
    session_response = client.post("/api/crawler/agent/sessions", json={"token": token})
    agent_session = session_response.json()["data"]["session"]

    db = TestingSessionLocal()
    try:
        agent = db.query(CrawlerAgentWorkItem).first()
        assert agent is None
        owner_response = client.get("/api/crawler/agent/status", headers=auth_headers)
        owner_agent_id = owner_response.json()["data"]["agent_id"]
        owner_id = db.get(CrawlerAgent, uuid.UUID(owner_agent_id)).owner_id
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="completed",
            result_json={"tasks": [{"code": "OLD"}]},
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={agent_session}") as websocket:
        assert websocket.receive_json()["type"] == "server.hello"
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98615,
                "version": "Chrome 0.1.0",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"
        websocket.send_json({
            "id": "late_snapshot",
            "type": "agent.page_snapshot",
            "payload": {
                "agent_task_id": item_id,
                "attempt": 1,
                "snapshot": {
                    "page_kind": "list",
                    "url": "https://javdb.com/actors/a",
                    "source_page": 1,
                    "fragments": {"items": "<div class='item'></div>"},
                },
            },
        })
        message = websocket.receive_json()

    assert message["type"] == "server.ack"
    assert message["payload"]["agent_task_id"] == item_id
    assert message["payload"]["ignored"] is True
    db = TestingSessionLocal()
    try:
        refreshed = db.get(CrawlerAgentWorkItem, uuid.UUID(item_id))
        assert refreshed.status == "completed"
        assert refreshed.result_json == {"tasks": [{"code": "OLD"}]}
    finally:
        db.close()


def test_agent_page_snapshot_marks_parse_error_failed(client, auth_headers) -> None:
    token_response = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_response.json()["data"]["token"]
    session_response = client.post("/api/crawler/agent/sessions", json={"token": token})
    agent_session = session_response.json()["data"]["session"]

    db = TestingSessionLocal()
    try:
        agent_id = client.get("/api/crawler/agent/status", headers=auth_headers).json()["data"]["agent_id"]
        owner_id = db.get(CrawlerAgent, uuid.UUID(agent_id)).owner_id
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="detail",
            url="https://javdb.com/v/abc",
            status="assigned",
            assigned_agent_id=uuid.UUID(agent_id),
            attempt=777,
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={agent_session}") as websocket:
        assert websocket.receive_json()["type"] == "server.hello"
        websocket.send_json({
            "id": "hello1",
            "type": "agent.hello",
            "payload": {"protocol_version": 2, "version": "1.0", "capabilities": ["task_events", "attempt_guard", "execution_deadline"]},
        })
        assert websocket.receive_json()["type"] == "server.ack"
        websocket.send_json({
            "id": "bad_snapshot",
            "type": "agent.page_snapshot",
            "payload": {
                "agent_task_id": item_id,
                "attempt": 777,
                "snapshot": {
                    "page_kind": "detail",
                    "url": "https://javdb.com/v/abc",
                    "fragments": {"title": "<h1>ABC</h1>"},
                },
            },
        })
        message = websocket.receive_json()

    assert message["type"] == "server.ack"
    assert message["payload"]["agent_task_id"] == item_id
    assert message["payload"]["accepted"] is False
    assert "missing_required_fragments" in message["payload"]["error_reason"]
    db = TestingSessionLocal()
    try:
        refreshed = db.get(CrawlerAgentWorkItem, uuid.UUID(item_id))
        assert refreshed.status == "failed"
        assert "missing_required_fragments" in refreshed.error_reason
    finally:
        db.close()


def test_agent_page_snapshot_parse_error_returns_terminal_ack(client, auth_headers) -> None:
    token_response = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_response.json()["data"]["token"]
    session_response = client.post("/api/crawler/agent/sessions", json={"token": token})
    agent_session = session_response.json()["data"]["session"]

    db = TestingSessionLocal()
    try:
        agent_id = client.get("/api/crawler/agent/status", headers=auth_headers).json()["data"]["agent_id"]
        owner_id = db.get(CrawlerAgent, uuid.UUID(agent_id)).owner_id
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="detail",
            url="https://javdb.com/v/abc",
            status="assigned",
            assigned_agent_id=uuid.UUID(agent_id),
            attempt=778,
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={agent_session}") as websocket:
        assert websocket.receive_json()["type"] == "server.hello"
        websocket.send_json({
            "id": "hello1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 2,
                "version": "1.0",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"
        websocket.send_json({
            "id": "bad_snapshot_ack",
            "type": "agent.page_snapshot",
            "payload": {
                "agent_task_id": item_id,
                "attempt": 778,
                "snapshot": {
                    "page_kind": "detail",
                    "url": "https://javdb.com/v/abc",
                    "fragments": {"title": "<h1>ABC</h1>"},
                },
            },
        })
        message = websocket.receive_json()

    assert message["type"] == "server.ack"
    assert message["payload"]["agent_task_id"] == item_id
    assert message["payload"]["accepted"] is False
    assert "missing_required_fragments" in message["payload"]["error_reason"]


def _make_agent_session(client, auth_headers) -> str:
    """Helper: rotate token, create session, return session string."""
    token_resp = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_resp.json()["data"]["token"]
    session_resp = client.post("/api/crawler/agent/sessions", json={"token": token})
    return session_resp.json()["data"]["session"]


def _resolve_owner_id_and_agent(db, session):
    """Helper: resolve owner_id and agent from session."""
    sess = (
        db.query(CrawlerAgentSession)
        .filter(CrawlerAgentSession.session_id == session)
        .first()
    )
    if sess is None:
        pytest.fail("session not found")
    agent = (
        db.query(CrawlerAgent)
        .filter(CrawlerAgent.owner_id == sess.owner_id)
        .first()
    )
    return sess.owner_id, agent


def test_agent_stays_offline_before_hello(client, auth_headers) -> None:
    """Agent DB status remains offline until the extension sends agent.hello."""
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "server.hello"
        # Assert the agent is still offline in the DB
        status_resp = client.get("/api/crawler/agent/status", headers=auth_headers)
        assert status_resp.json()["data"]["status"] == "offline"


def test_agent_hello_protocol_2_sets_online(client, auth_headers) -> None:
    """A compatible protocol 2 handshake transitions the agent to online."""
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "server.hello"

        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98615,
                "version": "Chrome 0.1.0",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        ack = websocket.receive_json()
        assert ack["type"] == "server.ack"

        status_resp = client.get("/api/crawler/agent/status", headers=auth_headers)
        assert status_resp.json()["data"]["status"] == "online"


def test_agent_hello_persists_negotiated_protocol_version(client, auth_headers) -> None:
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        assert websocket.receive_json()["type"] == "server.hello"
        websocket.send_json({
            "id": "hello-persisted-protocol",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 2,
                "version": "Chrome 0.2.0",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        status_resp = client.get("/api/crawler/agent/status", headers=auth_headers)
        assert status_resp.json()["data"]["protocol_version"] == 2


def test_agent_hello_protocol_1_gets_upgrade_required(client, auth_headers) -> None:
    """A protocol 1 hello (below minimum 2) receives upgrade_required error."""
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "server.hello"

        websocket.send_json({
            "id": "hello-low",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 1,
                "version": "Old Extension 0.0.1",
                "capabilities": [],
            },
        })
        err = websocket.receive_json()
        assert err["type"] == "server.error"
        assert err["payload"]["reason"] == "upgrade_required"
        assert err["payload"]["minimum_protocol_version"] == 2

        status_resp = client.get("/api/crawler/agent/status", headers=auth_headers)
        assert status_resp.json()["data"]["status"] == "upgrade_required"


def test_agent_hello_missing_capabilities_gets_upgrade_required(client, auth_headers) -> None:
    """An agent.hello with protocol 2 but missing capabilities gets rejected."""
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "server.hello"

        websocket.send_json({
            "id": "hello-incomplete",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98615,
                "version": "Chrome 0.1.0",
                "capabilities": ["task_events"],
            },
        })
        err = websocket.receive_json()
        assert err["type"] == "server.error"
        assert err["payload"]["reason"] == "upgrade_required"


def test_agent_message_before_hello_gets_handshake_required(client, auth_headers) -> None:
    """Messages sent before the handshake completes are rejected."""
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "server.hello"

        websocket.send_json({
            "id": "premature",
            "type": "agent.page_snapshot",
            "payload": {},
        })
        err = websocket.receive_json()
        assert err["type"] == "server.error"
        assert err["payload"]["reason"] == "handshake_required"


# ── Agent protocol flow tests (Task 5) ────────────────────────────────────


def test_agent_task_request_returns_assigned_with_deadline(client, auth_headers) -> None:
    """End-to-end: hello → create pending item → task_request → assigned."""
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, _agent = _resolve_owner_id_and_agent(db, session)
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="pending",
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98615,
                "version": "Chrome 0.097",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "task_req",
            "type": "agent.task_request",
            "payload": {},
        })
        assigned = websocket.receive_json()
        assert assigned["type"] == "task.assigned"
        assert assigned["payload"]["agent_task_id"] == item_id
        assert isinstance(assigned["payload"]["attempt"], int)
        assert assigned["payload"]["attempt"] >= 1
        assert assigned["payload"]["execution_deadline_at"] is not None
        assert datetime.fromisoformat(assigned["payload"]["execution_deadline_at"])


def test_agent_task_request_records_claim_diagnostics(client, auth_headers) -> None:
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, _agent = _resolve_owner_id_and_agent(db, session)
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="pending",
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98615,
                "version": "Chrome 0.097",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"
        websocket.send_json({"id": "task_req", "type": "agent.task_request", "payload": {}})
        assert websocket.receive_json()["type"] == "task.assigned"

    db = TestingSessionLocal()
    try:
        events = (
            db.query(CrawlerAgentEvent)
            .filter(CrawlerAgentEvent.work_item_id == uuid.UUID(item_id))
            .order_by(CrawlerAgentEvent.created_at.asc())
            .all()
        )
        event_types = [event.event_type for event in events]
        assert "task_request_received" in event_types
        assert "task_claimed" in event_types
    finally:
        db.close()


def test_agent_task_event_acknowledges_progress(client, auth_headers) -> None:
    """Send task_event (NOT YET IMPLEMENTED) for an assigned item and get ack."""
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, agent = _resolve_owner_id_and_agent(db, session)
        agent_id = str(agent.id) if agent else "00000000-0000-0000-0000-000000000000"
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="assigned",
            assigned_agent_id=uuid.UUID(agent_id),
            attempt=1,
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98765,
                "version": "Chrome 097",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "progress-1",
            "type": "agent.task_event",
            "payload": {
                "agent_task_id": item_id,
                "attempt": 1,
                "phase": "page.loading",
                "level": "info",
                "code": "tab_opened",
                "message": "JavDB 页面已打开",
                "details": {"tab_id": 81, "duration_ms": 20},
            },
        })
        ack = websocket.receive_json()
        assert ack["type"] == "server.ack"


def test_agent_task_failure_sends_ack(client, auth_headers) -> None:
    """Send agent.task_failed (NOT YET IMPLEMENTED) for an assigned item and get ack."""
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, agent = _resolve_owner_id_and_agent(db, session)
        agent_id = str(agent.id) if agent else "00000000-0000-0000-0000-000000000000"
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="detail",
            url="https://javdb.com/v/abc",
            status="assigned",
            assigned_agent_id=uuid.UUID(agent_id),
            attempt=1,
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98615,
                "version": "Chrome 095",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "fail-1",
            "type": "agent.task_failed",
            "payload": {
                "agent_task_id": item_id,
                "attempt": 1,
                "phase": "page.load",
                "code": "agent_tab_create_failed",
                "message": "Tab 创建失败",
            },
        })
        ack = websocket.receive_json()
        assert ack["type"] == "server.ack"


def test_agent_task_failure_accepts_detail_dom_not_ready_code(client, auth_headers) -> None:
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, agent = _resolve_owner_id_and_agent(db, session)
        agent_id = str(agent.id) if agent else "00000000-0000-0000-0000-000000000000"
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="detail",
            url="https://javdb.com/v/abc",
            status="assigned",
            assigned_agent_id=uuid.UUID(agent_id),
            attempt=1,
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 2,
                "version": "Chrome 0.2.0",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "fail-detail-dom",
            "type": "agent.task_failed",
            "payload": {
                "agent_task_id": item_id,
                "attempt": 1,
                "phase": "snapshot.collecting",
                "code": "agent_detail_dom_not_ready",
                "message": "detail_dom_not_ready",
            },
        })
        ack = websocket.receive_json()

    assert ack["type"] == "server.ack"
    db = TestingSessionLocal()
    try:
        refreshed = db.get(CrawlerAgentWorkItem, uuid.UUID(item_id))
        assert refreshed.status == "failed"
        assert refreshed.error_reason == "详情页主体未加载完成"
    finally:
        db.close()


def test_agent_stale_attempt_gets_ignored(client, auth_headers) -> None:
    """task_event (NOT YET IMPLEMENTED) with stale attempt gets ignored: true."""
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, agent = _resolve_owner_id_and_agent(db, session)
        agent_id = str(agent.id) if agent else "00000000-0000-0000-0000-000000000000"
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="assigned",
            assigned_agent_id=uuid.UUID(agent_id),
            attempt=2,
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98765,
                "version": "Chrome 0.097",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "stale-1",
            "type": "agent.task_event",
            "payload": {
                "agent_task_id": item_id,
                "attempt": 99,
                "phase": "page.loading",
                "level": "info",
                "code": "tab_opened",
                "message": "old progress",
            },
        })
        ack = websocket.receive_json()
        assert ack["type"] == "server.ack"
        assert ack["payload"].get("ignored") is True


def test_agent_no_pending_item_returns_task_none(client, auth_headers) -> None:
    """task_request with no pending items returns task.none."""
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98765,
                "version": "Chrome 099",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "no-task",
            "type": "agent.task_request",
            "payload": {},
        })
        none_msg = websocket.receive_json()
        assert none_msg["type"] == "task.none"


def test_agent_task_request_records_task_none_diagnostic(client, auth_headers) -> None:
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98765,
                "version": "Chrome 0.097",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"
        websocket.send_json({"id": "task_req", "type": "agent.task_request", "payload": {}})
        assert websocket.receive_json()["type"] == "task.none"

    db = TestingSessionLocal()
    try:
        sess = db.query(CrawlerAgentSession).filter(CrawlerAgentSession.session_id == session).one()
        event = (
            db.query(CrawlerAgentEvent)
            .filter(CrawlerAgentEvent.owner_id == sess.owner_id)
            .filter(CrawlerAgentEvent.event_type == "task_none")
            .one()
        )
        assert event.source == "backend"
        assert event.level == "info"
    finally:
        db.close()


def test_agent_disconnect_requeues_active_items(client, auth_headers) -> None:
    """Disconnect (NOT YET IMPLEMENTED) requeues or fails active items."""
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, agent = _resolve_owner_id_and_agent(db, session)
        agent_id = str(agent.id) if agent else "00000000-0000-0000-0000-000000000000"
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="assigned",
            assigned_agent_id=uuid.UUID(agent_id),
            attempt=1,
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98765,
                "version": "Chrome 099",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

    # After disconnect, the assigned item should be requeued
    db = TestingSessionLocal()
    try:
        refreshed = db.get(CrawlerAgentWorkItem, uuid.UUID(item_id))
        assert refreshed is not None
        assert refreshed.status != "assigned"
    finally:
        db.close()


def test_agent_malformed_snapshot_returns_error(client, auth_headers) -> None:
    """A snapshot with invalid page_kind gets server.error."""
    session = _make_agent_session(client, auth_headers)
    db = TestingSessionLocal()
    try:
        owner_id, _agent = _resolve_owner_id_and_agent(db, session)
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="list",
            url="https://javdb.com/actors/a",
            status="assigned",
            claimed_until=datetime.now(),
        )
        db.add(item)
        db.commit()
        item_id = str(item.id)
    finally:
        db.close()

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98765,
                "version": "Chrome 0.097",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "bad-snap",
            "type": "agent.page_snapshot",
            "payload": {
                "agent_task_id": item_id,
                "snapshot": {"page_kind": "invalid", "url": "https://x.com"},
            },
        })
        err = websocket.receive_json()
        assert err["type"] == "server.error"
        assert err["payload"]["agent_task_id"] == item_id


def test_agent_diagnostics_batch_persists_events(client, auth_headers) -> None:
    """diagnostics_batch (NOT YET IMPLEMENTED) with valid entries gets ack."""
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        websocket.receive_json()  # server.hello
        websocket.send_json({
            "id": "hello-1",
            "type": "agent.hello",
            "payload": {
                "protocol_version": 98765,
                "version": "Chrome 099",
                "capabilities": ["task_events", "attempt_guard", "execution_deadline"],
            },
        })
        assert websocket.receive_json()["type"] == "server.ack"

        websocket.send_json({
            "id": "diag-1",
            "type": "agent.diagnostics_batch",
            "payload": {
                "events": [
                    {
                        "source": "extension",
                        "event_type": "connection.status",
                        "level": "info",
                        "message": "Connected",
                        "details": {},
                    }
                ]
            },
        })
        ack = websocket.receive_json()
        assert ack["type"] == "server.ack"
        assert ack["payload"].get("accepted") == 1
