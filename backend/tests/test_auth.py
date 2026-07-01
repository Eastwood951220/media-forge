from http import HTTPStatus

from fastapi.testclient import TestClient


class TestAuthLogin:
    def test_login_success(self, client: TestClient, admin_user) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient, admin_user) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "secret"},
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_login_missing_fields(self, client: TestClient) -> None:
        response = client.post("/api/auth/login", json={})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestHealth:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["status"] == "ok"
