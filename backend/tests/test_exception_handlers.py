from http import HTTPStatus

from fastapi.testclient import TestClient


def test_http_exception_uses_standard_envelope(client: TestClient, admin_user) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {
        "code": 401,
        "msg": "Incorrect username or password",
        "data": None,
    }


def test_validation_error_uses_standard_envelope(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["code"] == 422
    assert body["msg"] == "请求参数错误"
    assert isinstance(body["data"], list)
    assert body["data"][0]["loc"][0] == "body"
