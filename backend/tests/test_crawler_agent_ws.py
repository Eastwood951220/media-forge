import uuid
from datetime import datetime

from backend.app.models.crawler_agent import CrawlerAgent, CrawlerAgentWorkItem
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
        from backend.app.models.crawler_agent import CrawlerAgent
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
        from backend.app.models.crawler_agent import CrawlerAgent
        agent_id = client.get("/api/crawler/agent/status", headers=auth_headers).json()["data"]["agent_id"]
        owner_id = db.get(CrawlerAgent, uuid.UUID(agent_id)).owner_id
        item = CrawlerAgentWorkItem(
            owner_id=owner_id,
            run_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            page_kind="detail",
            url="https://javdb.com/v/abc",
            status="assigned",
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
                "snapshot": {
                    "page_kind": "detail",
                    "url": "https://javdb.com/v/abc",
                    "fragments": {"title": "<h1>ABC</h1>"},
                },
            },
        })
        message = websocket.receive_json()

    assert message["type"] == "server.error"
    assert message["payload"]["agent_task_id"] == item_id
    assert "missing_required_fragments" in message["payload"]["reason"]
    db = TestingSessionLocal()
    try:
        refreshed = db.get(CrawlerAgentWorkItem, uuid.UUID(item_id))
        assert refreshed.status == "failed"
        assert "missing_required_fragments" in refreshed.error_reason
    finally:
        db.close()


def _make_agent_session(client, auth_headers) -> str:
    """Helper: rotate token, create session, return session string."""
    token_resp = client.post("/api/crawler/agent/token/rotate", headers=auth_headers)
    token = token_resp.json()["data"]["token"]
    session_resp = client.post("/api/crawler/agent/sessions", json={"token": token})
    return session_resp.json()["data"]["session"]


def test_agent_stays_offline_before_hello(client, auth_headers) -> None:
    """Agent DB status remains offline until the extension sends agent.hello.

    This test will fail under the current implementation (which sets status
    to 'online' immediately) and should pass after the protocol handshake
    gate is added in Task 4, Step 5.
    """
    session = _make_agent_session(client, auth_headers)

    with client.websocket_connect(f"/api/crawler/agent/ws?session={session}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "server.hello"
        # Assert the agent is still offline in the DB
        status_resp = client.get("/api/crawler/agent/status", headers=auth_headers)
        assert status_resp.json()["data"]["status"] == "offline"
        # Do NOT send agent.hello — just disconnect
        # (connection close implicitly tests cleanup)


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
