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
