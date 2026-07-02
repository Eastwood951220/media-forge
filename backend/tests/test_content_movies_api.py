from datetime import date
from decimal import Decimal
from http import HTTPStatus

from fastapi.testclient import TestClient

from shared.database.models.content import Movie, MovieMagnet
from backend.tests.conftest import TestingSessionLocal
from backend.app.modules.content.movies import filter_config


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def seed_movie() -> str:
    session = TestingSessionLocal()
    movie = Movie(
        code="AAA-001",
        source_url="https://javdb.com/v/aaa",
        source_name="测试电影",
        release_date=date(2026, 1, 1),
        duration=120,
        rating=Decimal("4.5"),
        actors=["演员A"],
        tags=["标签A"],
        source_task_names=["任务A"],
        cover="https://example.com/cover.jpg",
    )
    session.add(movie)
    session.flush()
    session.add(MovieMagnet(movie_id=movie.id, magnet_url="magnet:?xt=urn:btih:abc", dedupe_key="abc", name="磁力A"))
    session.commit()
    movie_id = str(movie.id)
    session.close()
    return movie_id


def test_list_movies_search_and_source_task(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_movie()

    response = client.get("/api/content/movies?keyword=AAA&source_task_name=任务A", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-001"
    assert body["rows"][0]["source_task_names"] == ["任务A"]


def test_get_movie_detail_includes_magnets(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    movie_id = seed_movie()

    response = client.get(f"/api/content/movies/{movie_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["id"] == movie_id
    assert data["magnets"][0]["magnet_url"].startswith("magnet:")


def test_movie_filter_config_persists_to_json_file(client: TestClient, admin_user, monkeypatch, tmp_path) -> None:
    headers = auth_headers(client, admin_user)
    config_path = tmp_path / "movie_filter_config.json"
    monkeypatch.setattr(filter_config, "FILTER_CONFIG_PATH", config_path)

    initial = client.get("/api/content/movies/filter-config", headers=headers)
    assert initial.status_code == HTTPStatus.OK
    assert initial.json()["data"]["_key"] == "default"
    assert initial.json()["data"]["filters"] == {}

    payload = {
        "filters": {
            "actors": {"visible": True, "order": 0, "defaultValue": "演员A"},
            "sortBy": {"visible": True, "order": 19, "defaultValue": "rating:-1"},
        }
    }
    update = client.put("/api/content/movies/filter-config", json=payload, headers=headers)
    assert update.status_code == HTTPStatus.OK
    assert update.json()["data"]["success"] is True

    loaded = client.get("/api/content/movies/filter-config", headers=headers)
    assert loaded.json()["data"]["filters"] == payload["filters"]
    assert config_path.exists()
