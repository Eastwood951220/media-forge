import uuid
from datetime import date
from decimal import Decimal
from http import HTTPStatus

from fastapi.testclient import TestClient

from shared.database.models.content import Movie, MovieFilter, MovieMagnet
from backend.tests.conftest import TestingSessionLocal
from backend.app.modules.content.movies import filter_config


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


TASK_ID_A = uuid.uuid4()
TASK_ID_B = uuid.uuid4()
TASK_ID_C = uuid.uuid4()


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
        source_task_ids=[TASK_ID_A],
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

    response = client.get(f"/api/content/movies?keyword=AAA&source_task_id={TASK_ID_A}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-001"
    assert str(TASK_ID_A) in body["rows"][0]["source_task_ids"]


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


def test_movie_filter_options(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_movie()
    session = TestingSessionLocal()
    session.add(Movie(
        code="BBB-002",
        source_url="https://javdb.com/v/bbb",
        source_name="第二部电影",
        release_date=date(2026, 2, 2),
        duration=90,
        rating=Decimal("3.5"),
        actors=["演员B"],
        tags=["标签B"],
        director="导演B",
        maker="片商B",
        series="系列B",
        source_task_ids=[TASK_ID_B],
    ))
    session.commit()
    session.close()

    actor_response = client.get("/api/content/movies/filters?type=actor", headers=headers)
    tag_response = client.get("/api/content/movies/filters?type=tag", headers=headers)
    director_response = client.get("/api/content/movies/filters?type=director", headers=headers)
    invalid_response = client.get("/api/content/movies/filters?type=bad", headers=headers)

    assert actor_response.json()["data"] == ["演员A", "演员B"]
    assert tag_response.json()["data"] == ["标签A", "标签B"]
    assert director_response.json()["data"] == ["导演B"]
    assert invalid_response.status_code == HTTPStatus.BAD_REQUEST


def test_movie_filter_options_prefer_movie_filters_cache(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    session.add(Movie(
        code="CACHE-001",
        source_url="https://javdb.com/v/cache001",
        source_name="缓存回退验证",
        actors=["电影演员"],
        tags=["电影标签"],
        director="电影导演",
        maker="电影片商",
        series="电影系列",
        source_task_ids=[TASK_ID_A],
    ))
    session.add(MovieFilter(type="actor", name="缓存演员", count=1))
    session.add(MovieFilter(type="tag", name="缓存标签", count=1))
    session.add(MovieFilter(type="director", name="缓存导演", count=1))
    session.add(MovieFilter(type="maker", name="缓存片商", count=1))
    session.add(MovieFilter(type="series", name="缓存系列", count=1))
    session.commit()
    session.close()

    actor_response = client.get("/api/content/movies/filters?type=actor", headers=headers)
    tag_response = client.get("/api/content/movies/filters?type=tag", headers=headers)
    director_response = client.get("/api/content/movies/filters?type=director", headers=headers)
    maker_response = client.get("/api/content/movies/filters?type=maker", headers=headers)
    series_response = client.get("/api/content/movies/filters?type=series", headers=headers)

    assert actor_response.status_code == HTTPStatus.OK
    assert actor_response.json()["data"] == ["缓存演员"]
    assert tag_response.json()["data"] == ["缓存标签"]
    assert director_response.json()["data"] == ["缓存导演"]
    assert maker_response.json()["data"] == ["缓存片商"]
    assert series_response.json()["data"] == ["缓存系列"]


def seed_filter_movies() -> None:
    session = TestingSessionLocal()
    session.add_all([
        Movie(
            code="AAA-100",
            source_url="https://javdb.com/v/aaa100",
            source_name="高分电影",
            release_date=date(2026, 1, 10),
            duration=120,
            rating=Decimal("4.8"),
            actors=["演员A", "演员C"],
            tags=["标签A"],
            director="导演A",
            maker="片商A",
            series="系列A",
            source_task_ids=[TASK_ID_A],
            storage_summary={"last_status": "completed"},
        ),
        Movie(
            code="BBB-200",
            source_url="https://javdb.com/v/bbb200",
            source_name="低分电影",
            release_date=date(2026, 2, 20),
            duration=90,
            rating=Decimal("2.2"),
            actors=["演员B"],
            tags=["标签B", "标签C"],
            director="导演B",
            maker="片商B",
            series="系列B",
            source_task_ids=[TASK_ID_B],
            storage_summary={"last_status": "missing"},
        ),
    ])
    session.commit()
    session.close()


def test_list_movies_supports_original_filter_contract(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_filter_movies()

    response = client.get(
        "/api/content/movies",
        params={
            "search": "电影",
            "source_task_id": str(TASK_ID_A),
            "actors": "演员A",
            "actors_not": "演员B",
            "tags": "标签A",
            "director": "导演A",
            "maker": "片商A",
            "series": "系列A",
            "rating_min": 4,
            "rating_max": 5,
            "actors_count_min": 2,
            "actors_count_max": 2,
            "release_date_from": "2026-01-01",
            "release_date_to": "2026-01-31",
            "storage_status": "completed",
            "page": 1,
            "limit": 20,
            "sort_by": "rating",
            "sort_order": -1,
        },
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-100"
    assert body["rows"][0]["_id"] == body["rows"][0]["id"]
    assert str(TASK_ID_A) in body["rows"][0]["source_task_ids"]


def test_list_movies_not_stored_filter(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    session.add(Movie(code="CCC-300", source_url="https://javdb.com/v/ccc300", source_name="无存储", source_task_ids=[TASK_ID_C], storage_summary={}))
    session.add(Movie(code="DDD-400", source_url="https://javdb.com/v/ddd400", source_name="已存储", source_task_ids=[TASK_ID_C], storage_summary={"last_status": "completed"}))
    session.commit()
    session.close()

    response = client.get("/api/content/movies?storage_status=not_stored", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert [row["code"] for row in response.json()["rows"]] == ["CCC-300"]
