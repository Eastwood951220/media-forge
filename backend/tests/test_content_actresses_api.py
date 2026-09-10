import uuid
from datetime import date, datetime
from urllib.error import HTTPError

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.content.actresses import service as actress_service
from backend.app.modules.content.actresses.avjoho_parser import AvjohoProfilePayload
from shared.database.models.content import ActressProfile, Movie


def _seed_actor_task(db_session, admin_user, *, url_name: str = "宮上唯依花") -> tuple[CrawlTask, CrawlTaskUrl]:
    task = CrawlTask(name="宮上唯依花 任务", storage_location="宮上唯依花", owner_id=admin_user.id)
    db_session.add(task)
    db_session.flush()
    task_url = CrawlTaskUrl(
        task_id=task.id,
        position=0,
        url="https://javdb.com/actors/yuika",
        url_type="actors",
        source="javdb",
        final_url="https://javdb.com/actors/yuika",
        url_name=url_name,
    )
    db_session.add(task_url)
    db_session.flush()
    return task, task_url


def test_list_actresses_returns_cards_with_page_size_multiple_of_8(client, auth_headers, db_session) -> None:
    for index in range(9):
        db_session.add(ActressProfile(
            display_name=f"女优 {index}",
            reading="",
            canonical_names=[f"女优 {index}"],
            source_url=f"https://db.avjoho.com/actress-{index}/",
            image_url=f"https://example.test/{index}.jpg",
            last_fetched_at=datetime.now(),
        ))
    db_session.commit()

    response = client.get("/api/content/actresses?page=1&limit=8", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 9
    assert len(payload["rows"]) == 8
    returned_names = {row["display_name"] for row in payload["rows"]}
    assert returned_names.issubset({f"女优 {index}" for index in range(9)})
    assert all(row["image_url"].startswith("https://example.test/") for row in payload["rows"])


def test_get_actress_detail_returns_recent_movies_by_task_url_id(client, auth_headers, db_session, admin_user) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user)
    other_task_url_id = uuid.uuid4()
    profile = ActressProfile(
        display_name="宮上唯依花",
        reading="みやうえゆいか",
        aliases=["Miyaue Yuika"],
        canonical_names=["宮上唯依花", "Miyaue Yuika"],
        source_url="https://db.avjoho.com/宮上唯依花/",
        source_task_ids=[task.id],
        source_task_url_ids=[task_url.id],
        image_url="https://example.test/cover.jpg",
        debut_date=date(2026, 9, 3),
        last_fetched_at=datetime.now(),
    )
    db_session.add(profile)
    db_session.add_all([
        Movie(
            code="RECENT-OLD",
            source_name="Old Movie",
            cover="https://example.test/old.jpg",
            release_date=date(2026, 1, 1),
            source_task_ids=[task.id],
            source_task_url_ids=[task_url.id],
        ),
        Movie(
            code="RECENT-NEW",
            source_name="New Movie",
            cover="https://example.test/new.jpg",
            release_date=date(2026, 9, 1),
            source_task_ids=[task.id],
            source_task_url_ids=[task_url.id],
        ),
        Movie(
            code="NAME-MATCH-ONLY",
            source_name="宮上唯依花 Name Match",
            release_date=date(2026, 10, 1),
            source_task_ids=[task.id],
            source_task_url_ids=[other_task_url_id],
        ),
    ])
    db_session.commit()

    response = client.get(f"/api/content/actresses/{profile.id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["display_name"] == "宮上唯依花"
    assert [movie["code"] for movie in data["recent_movies"]] == ["RECENT-NEW", "RECENT-OLD"]


def test_get_actress_detail_returns_external_task_url_links(client, auth_headers, db_session, admin_user) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user)
    javbus_url = CrawlTaskUrl(
        task_id=task.id,
        position=1,
        url="https://www.javbus.com/star/abc",
        url_type="actors",
        source="javbus",
        final_url="https://www.javbus.com/star/abc/2",
        url_name="宮上唯依花",
    )
    db_session.add(javbus_url)
    db_session.flush()
    profile = ActressProfile(
        display_name="宮上唯依花",
        reading="みやうえゆいか",
        canonical_names=["宮上唯依花"],
        source_url="https://db.avjoho.com/宮上唯依花/",
        source_task_ids=[task.id],
        source_task_url_ids=[task_url.id, javbus_url.id],
        image_url="https://example.test/cover.jpg",
    )
    db_session.add(profile)
    db_session.commit()

    response = client.get(f"/api/content/actresses/{profile.id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["external_links"] == [
        {
            "id": str(task_url.id),
            "_id": str(task_url.id),
            "source": "javdb",
            "label": "JavDB",
            "url": "https://javdb.com/actors/yuika",
            "url_type": "actors",
            "url_name": "宮上唯依花",
        },
        {
            "id": str(javbus_url.id),
            "_id": str(javbus_url.id),
            "source": "javbus",
            "label": "JavBus",
            "url": "https://www.javbus.com/star/abc/2",
            "url_type": "actors",
            "url_name": "宮上唯依花",
        },
    ]


def test_fetch_actress_from_actor_task_uses_javdb_aliases_to_match_avjoho(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user, url_name="咲乃柑菜")

    monkeypatch.setattr(actress_service, "_fetch_javdb_actor_metadata", lambda _url: {
        "primary_names": ["咲乃柑菜"],
        "aliases": ["蘭華"],
    })
    monkeypatch.setattr(actress_service, "_build_avjoho_candidates", lambda names: [
        "https://db.avjoho.com/%E8%98%AD%E8%8F%AF/",
    ])
    monkeypatch.setattr(actress_service, "_fetch_avjoho_profile", lambda url: AvjohoProfilePayload(
        display_name="蘭華",
        reading="らんか",
        source_url=url,
        image_url="https://example.test/ranka.jpg",
        aliases=["咲乃柑菜"],
    ))

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(task.id), "task_url_id": str(task_url.id)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matched"] is True
    assert data["profiles"][0]["display_name"] == "蘭華"
    assert data["profiles"][0]["source_task_url_ids"] == [str(task_url.id)]


def test_fetch_actress_from_actor_task_falls_back_to_avjoho_search(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user, url_name="七瀨愛麗絲")
    attempted_urls: list[str] = []

    monkeypatch.setattr(actress_service, "_fetch_javdb_actor_metadata", lambda _url: {
        "primary_names": ["七瀨愛麗絲"],
        "aliases": ["七瀬アリス"],
    })
    monkeypatch.setattr(actress_service, "_find_avjoho_profile_urls_by_search", lambda name: (
        ["https://db.avjoho.com/nanase-alice/"] if name == "七瀬アリス" else []
    ))

    def fake_fetch_avjoho_profile(url: str) -> AvjohoProfilePayload:
        attempted_urls.append(url)
        if url != "https://db.avjoho.com/nanase-alice/":
            raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        return AvjohoProfilePayload(
            display_name="七瀬アリス",
            reading="ななせありす",
            source_url=url,
            image_url="https://example.test/nanase.jpg",
            aliases=["七瀨愛麗絲"],
        )

    monkeypatch.setattr(actress_service, "_fetch_avjoho_profile", fake_fetch_avjoho_profile)

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(task.id), "task_url_id": str(task_url.id)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matched"] is True
    assert data["profiles"][0]["display_name"] == "七瀬アリス"
    assert data["profiles"][0]["source_task_url_ids"] == [str(task_url.id)]
    assert attempted_urls[:2] == [
        "https://db.avjoho.com/%E4%B8%83%E7%80%A8%E6%84%9B%E9%BA%97%E7%B5%B2/",
        "https://db.avjoho.com/%E4%B8%83%E7%80%AC%E3%82%A2%E3%83%AA%E3%82%B9/",
    ]
    assert attempted_urls[-1] == "https://db.avjoho.com/nanase-alice/"


def test_fetch_actress_from_actor_task_logs_404_without_traceback(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
    caplog,
) -> None:
    task, _task_url = _seed_actor_task(db_session, admin_user, url_name="不存在")

    monkeypatch.setattr(actress_service, "_fetch_javdb_actor_metadata", lambda _url: {
        "primary_names": ["不存在"],
        "aliases": [],
    })
    monkeypatch.setattr(actress_service, "_find_avjoho_profile_urls_by_search", lambda _name: [])
    monkeypatch.setattr(actress_service, "_fetch_avjoho_profile", lambda url: (
        (_ for _ in ()).throw(HTTPError(url, 404, "Not Found", hdrs=None, fp=None))
    ))

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(task.id), "task_url_id": str(_task_url.id)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matched"] is False
    assert "Traceback" not in caplog.text
    assert "HTTPError" not in caplog.text


def test_fetch_actress_from_task_only_fetches_selected_actor_url(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
) -> None:
    task, first_url = _seed_actor_task(db_session, admin_user, url_name="演员A")
    second_url = CrawlTaskUrl(
        task_id=task.id,
        position=1,
        url="https://javdb.com/actors/b",
        url_type="actors",
        source="javdb",
        final_url="https://javdb.com/actors/b",
        url_name="演员B",
    )
    db_session.add(second_url)
    db_session.commit()
    fetched_javdb_urls: list[str] = []

    def fake_fetch_javdb_actor_metadata(url: str) -> dict[str, list[str]]:
        fetched_javdb_urls.append(url)
        return {
            "primary_names": ["演员B"],
            "aliases": [],
        }

    monkeypatch.setattr(actress_service, "_fetch_javdb_actor_metadata", fake_fetch_javdb_actor_metadata)
    monkeypatch.setattr(actress_service, "_find_avjoho_profile_urls_by_search", lambda _name: [])
    monkeypatch.setattr(actress_service, "_fetch_avjoho_profile", lambda url: AvjohoProfilePayload(
        display_name="演员B",
        reading="",
        source_url=url,
        image_url="https://example.test/b.jpg",
    ))

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(task.id), "task_url_id": str(second_url.id)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matched"] is True
    assert data["profiles"][0]["source_task_url_ids"] == [str(second_url.id)]
    assert fetched_javdb_urls == ["https://javdb.com/actors/b"]
    assert str(first_url.id) not in data["profiles"][0]["source_task_url_ids"]


def test_fetch_actress_rejects_non_actor_tasks(client, auth_headers, db_session, admin_user) -> None:
    task = CrawlTask(name="Search Task", storage_location="Search Task", owner_id=admin_user.id)
    db_session.add(task)
    db_session.flush()
    task_url = CrawlTaskUrl(
        task_id=task.id,
        position=0,
        url="https://javdb.com/search?q=test",
        url_type="search",
        source="javdb",
        final_url="https://javdb.com/search?q=test",
    )
    db_session.add(task_url)
    db_session.commit()

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(task.id), "task_url_id": str(task_url.id)},
        headers=auth_headers,
    )

    assert response.status_code == 400
