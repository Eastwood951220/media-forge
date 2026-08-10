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
