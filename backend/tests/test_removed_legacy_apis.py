from http import HTTPStatus

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_legacy_movies_route_is_removed(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)

    response = client.get("/api/movies", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND
