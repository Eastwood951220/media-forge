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
            storage_summary={"storage_status": "stored", "last_status": "stored"},
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
            "storage_status": "stored",
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
    session.add(Movie(code="DDD-400", source_url="https://javdb.com/v/ddd400", source_name="已存储", source_task_ids=[TASK_ID_C], storage_summary={"storage_status": "stored", "last_status": "stored"}))
    session.commit()
    session.close()

    response = client.get("/api/content/movies?storage_status=not_stored", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert [row["code"] for row in response.json()["rows"]] == ["CCC-300"]


def test_sync_movie_storage_status_scans_target_folders_and_records_locations(db_session, admin_user):
    from dataclasses import dataclass

    from backend.app.models.crawl_task import CrawlTask
    from backend.app.modules.content.movies.storage_status import sync_movie_storage_status
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ABC-001":
                return [
                    RemoteFile("ABC-001-C.mp4", "/Movies/A/ABC-001/ABC-001-C.mp4", 500 * 1024 * 1024),
                ]
            return []

    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    movie = Movie(
        code="abc-001",
        source_name="sync movie",
        source_task_ids=[],
        storage_summary={},
    )
    db_session.add_all([crawl_task, movie])
    db_session.flush()
    movie.source_task_ids = [crawl_task.id]
    db_session.commit()

    result = sync_movie_storage_status(
        db=db_session,
        movie=movie,
        provider=Provider(),
        config={
            "target_folder": "/Movies",
            "video_extensions": [".mp4", ".mkv"],
            "minimum_video_size_mb": 100,
        },
        source="manual_sync",
    )

    assert result.status == "stored"
    assert result.found_count == 1
    assert movie.storage_summary["storage_status"] == "stored"
    assert movie.storage_summary["last_status"] == "stored"
    assert movie.storage_summary["locations"] == [
        {
            "path": "/Movies/A/ABC-001/ABC-001-C.mp4",
            "target_folder": "/Movies/A/ABC-001",
            "storage_location": "A",
            "file_name": "ABC-001-C.mp4",
            "size": 500 * 1024 * 1024,
            "exists": True,
            "source": "manual_sync",
        }
    ]


def test_movie_payload_and_filter_use_three_storage_statuses(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    session.add_all([
        Movie(code="SYNC-100", source_url="https://example.test/1", source_name="默认未存储", storage_summary={}),
        Movie(code="SYNC-200", source_url="https://example.test/2", source_name="入库中", storage_summary={"storage_status": "storing"}),
        Movie(code="SYNC-300", source_url="https://example.test/3", source_name="已存储", storage_summary={"storage_status": "stored"}),
    ])
    session.commit()
    session.close()

    not_stored = client.get("/api/content/movies?storage_status=not_stored", headers=headers)
    storing = client.get("/api/content/movies?storage_status=storing", headers=headers)
    stored = client.get("/api/content/movies?storage_status=stored", headers=headers)

    assert [row["code"] for row in not_stored.json()["rows"]] == ["SYNC-100"]
    assert not_stored.json()["rows"][0]["storage_status"] == "not_stored"
    assert [row["code"] for row in storing.json()["rows"]] == ["SYNC-200"]
    assert storing.json()["rows"][0]["storage_status"] == "storing"
    assert [row["code"] for row in stored.json()["rows"]] == ["SYNC-300"]
    assert stored.json()["rows"][0]["storage_status"] == "stored"


def test_sync_movie_storage_status_api_syncs_selected_movies(client: TestClient, admin_user, monkeypatch):
    from dataclasses import dataclass

    from backend.app.models.crawl_task import CrawlTask
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/SYNC-API-001":
                return [RemoteFile("SYNC-API-001.mp4", "/Movies/A/SYNC-API-001/SYNC-API-001.mp4", 500 * 1024 * 1024)]
            return []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            self.provider = Provider()

        def list_files(self, path, force_refresh=False):
            return self.provider.list_files(path, force_refresh)

    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    movie = Movie(code="SYNC-API-001", source_name="selected sync", source_task_ids=[], storage_summary={})
    session.add_all([crawl_task, movie])
    session.flush()
    movie.source_task_ids = [crawl_task.id]
    movie_id = str(movie.id)
    session.commit()
    session.close()

    monkeypatch.setattr(
        "backend.app.modules.storage.config.service.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {
                "target_folder": "/Movies",
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            },
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.post(
        "/api/content/movies/storage-sync",
        json={"movie_ids": [movie_id]},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["stored_count"] == 1
    assert payload["not_stored_count"] == 0
    assert payload["results"][0]["movie_id"] == movie_id
    assert payload["results"][0]["status"] == "stored"

    detail = client.get(f"/api/content/movies/{movie_id}", headers=headers).json()["data"]
    assert detail["storage_status"] == "stored"
    assert detail["storage_summary"]["locations"][0]["path"] == "/Movies/A/SYNC-API-001/SYNC-API-001.mp4"


def test_sync_movie_storage_status_api_uses_filters_when_no_selection(client: TestClient, admin_user, monkeypatch):
    from dataclasses import dataclass

    from backend.app.models.crawl_task import CrawlTask
    from shared.database.models.content import Movie

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/SYNC-FILTER-001":
                return [RemoteFile("SYNC-FILTER-001.mp4", "/Movies/A/SYNC-FILTER-001/SYNC-FILTER-001.mp4", 500 * 1024 * 1024)]
            return []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            self.provider = Provider()

        def list_files(self, path, force_refresh=False):
            return self.provider.list_files(path, force_refresh)

    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    crawl_task = CrawlTask(name="source-A", storage_location="A", owner_id=admin_user.id)
    matched = Movie(code="SYNC-FILTER-001", source_name="matched selected name", source_task_ids=[], storage_summary={})
    ignored = Movie(code="SYNC-FILTER-002", source_name="ignored name", source_task_ids=[], storage_summary={})
    session.add_all([crawl_task, matched, ignored])
    session.flush()
    matched.source_task_ids = [crawl_task.id]
    ignored.source_task_ids = [crawl_task.id]
    matched_id = str(matched.id)
    ignored_id = str(ignored.id)
    session.commit()
    session.close()

    monkeypatch.setattr(
        "backend.app.modules.storage.config.service.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {
                "target_folder": "/Movies",
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            },
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.post(
        "/api/content/movies/storage-sync",
        json={"filters": {"search": "matched"}},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["results"][0]["movie_id"] == matched_id
    assert client.get(f"/api/content/movies/{matched_id}", headers=headers).json()["data"]["storage_status"] == "stored"
    assert client.get(f"/api/content/movies/{ignored_id}", headers=headers).json()["data"]["storage_status"] == "not_stored"


def test_delete_movies_database_only_api_deletes_selected_movies(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    movie = Movie(code="DEL-DB-001", source_url="https://example.test/delete-db", source_name="delete db")
    session.add(movie)
    session.commit()
    movie_id = str(movie.id)
    session.close()

    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [movie_id], "mode": "database_only"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["deleted_movies"] == 1
    assert client.get(f"/api/content/movies/{movie_id}", headers=headers).status_code == HTTPStatus.NOT_FOUND


def test_delete_movies_cloud_only_api_deletes_cloud_folders_and_keeps_movie(client: TestClient, admin_user, monkeypatch) -> None:
    headers = auth_headers(client, admin_user)
    session = TestingSessionLocal()
    movie = Movie(
        code="DEL-CLOUD-001",
        source_url="https://example.test/delete-cloud",
        source_name="delete cloud",
        storage_summary={
            "storage_status": "stored",
            "last_status": "stored",
            "locations": [
                {
                    "path": "/Movies/A/DEL-CLOUD-001/DEL-CLOUD-001.mp4",
                    "target_folder": "/Movies/A/DEL-CLOUD-001",
                    "storage_location": "A",
                }
            ],
        },
    )
    session.add(movie)
    session.commit()
    movie_id = str(movie.id)
    session.close()

    deleted: list[str] = []

    class Factory:
        def create(self, config):
            return object()

    class Gateway:
        def __init__(self, client):
            return None

        def delete_file(self, path):
            deleted.append(path)

    monkeypatch.setattr(
        "backend.app.modules.storage.config.service.StorageConfigService",
        lambda: type("ConfigService", (), {
            "get_raw_config": lambda self: {"target_folder": "/Movies"},
            "provider_factory": Factory(),
            "gateway_class": Gateway,
        })(),
    )

    response = client.post(
        "/api/content/movies/delete",
        json={"movie_ids": [movie_id], "mode": "cloud_only"},
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    assert deleted == ["/Movies/A/DEL-CLOUD-001"]
    detail = client.get(f"/api/content/movies/{movie_id}", headers=headers).json()["data"]
    assert detail["storage_status"] == "not_stored"
    assert detail["storage_summary"]["locations"] == []


def test_movie_list_query_helpers_preserve_sort_and_storage_filter(client: TestClient, admin_user) -> None:
    headers = auth_headers(client, admin_user)
    seed_filter_movies()

    response = client.get(
        "/api/content/movies?storage_status=stored&sort_by=rating&sort_order=-1&page=1&limit=10",
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "AAA-100"
