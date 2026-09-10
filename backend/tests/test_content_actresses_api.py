import uuid
from datetime import date, datetime

from backend.app.models.crawl_task import CrawlTask, CrawlTaskTag, CrawlTaskUrl
from backend.app.modules.content.actresses import service as actress_service
from scraper.profiles.actress import ActorMetadata, ActressProfileMatch, ActressProfilePayload
from scraper.spiders.avjoho.avjoho_spider import AvjohoActressSpider, ProfileSourceNotFound
from shared.database.models.content import ActressProfile, Movie


def _seed_actor_task(
    db_session,
    admin_user,
    *,
    url_name: str = "宮上唯依花",
    tag_names: list[str] | None = None,
) -> tuple[CrawlTask, CrawlTaskUrl]:
    task = CrawlTask(name="宮上唯依花 任务", storage_location="宮上唯依花", owner_id=admin_user.id)
    if tag_names:
        task.tags = [CrawlTaskTag(owner_id=admin_user.id, name=name) for name in tag_names]
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


def test_actress_tag_metadata_contains_normalized_tables() -> None:
    from shared.database.models.base import Base

    assert "actress_tags" in Base.metadata.tables
    assert "actress_tag_links" in Base.metadata.tables


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


def test_list_actresses_filters_by_cup_height_and_measurements(client, auth_headers, db_session) -> None:
    today = date.today()
    db_session.add_all([
        ActressProfile(
            display_name="Matched",
            reading="",
            canonical_names=["Matched"],
            source_url="https://db.avjoho.com/matched/",
            image_url="https://example.test/matched.jpg",
            cup="E",
            height_cm=165,
            bust_cm=90,
            waist_cm=58,
            hip_cm=88,
            birth_date=date(today.year - 35, 1, 1),
        ),
        ActressProfile(
            display_name="Wrong Cup",
            reading="",
            canonical_names=["Wrong Cup"],
            source_url="https://db.avjoho.com/wrong-cup/",
            image_url="https://example.test/wrong-cup.jpg",
            cup="D",
            height_cm=165,
            bust_cm=90,
            waist_cm=58,
            hip_cm=88,
            birth_date=date(today.year - 35, 1, 1),
        ),
        ActressProfile(
            display_name="Wrong Measurements",
            reading="",
            canonical_names=["Wrong Measurements"],
            source_url="https://db.avjoho.com/wrong-measurements/",
            image_url="https://example.test/wrong-measurements.jpg",
            cup="E",
            height_cm=158,
            bust_cm=84,
            waist_cm=63,
            hip_cm=92,
            birth_date=date(today.year - 45, 1, 1),
        ),
    ])
    db_session.commit()

    response = client.get(
        "/api/content/actresses?cup=E&height_range=162_165&bust_range=90_94&waist_range=56_59&hip_range=85_88&age_range=30s",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [row["display_name"] for row in payload["rows"]] == ["Matched"]


def test_list_actresses_filters_by_tags(client, auth_headers, db_session) -> None:
    db_session.add_all([
        ActressProfile(
            display_name="Tagged A",
            canonical_names=["Tagged A"],
            source_url="https://db.avjoho.com/tagged-a/",
            image_url="https://example.test/tagged-a.jpg",
            tags=["清楚", "企划"],
        ),
        ActressProfile(
            display_name="Tagged B",
            canonical_names=["Tagged B"],
            source_url="https://db.avjoho.com/tagged-b/",
            image_url="https://example.test/tagged-b.jpg",
            tags=["清楚"],
        ),
    ])
    db_session.commit()

    response = client.get("/api/content/actresses?tags=清楚,企划", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["rows"][0]["display_name"] == "Tagged A"
    assert payload["rows"][0]["tags"] == ["清楚", "企划"]


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
            "task_id": str(task.id),
            "url": "https://javdb.com/actors/yuika",
            "url_type": "actors",
            "url_name": "宮上唯依花",
        },
        {
            "id": str(javbus_url.id),
            "_id": str(javbus_url.id),
            "source": "javbus",
            "label": "JavBus",
            "task_id": str(task.id),
            "url": "https://www.javbus.com/star/abc/2",
            "url_type": "actors",
            "url_name": "宮上唯依花",
        },
    ]


def test_update_actress_tags(client, auth_headers, db_session) -> None:
    profile = ActressProfile(
        display_name="Tag Editable",
        canonical_names=["Tag Editable"],
        source_url="https://db.avjoho.com/tag-editable/",
        image_url="https://example.test/tag-editable.jpg",
        tags=["旧标签"],
    )
    db_session.add(profile)
    db_session.commit()

    response = client.put(
        f"/api/content/actresses/{profile.id}/tags",
        json={"tags": ["新标签", "  新标签  ", "企划"]},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tags"] == ["新标签", "企划"]


def _stub_site_fetchers(monkeypatch) -> None:
    """Keep provider calls hermetic; these tests patch the provider functions themselves."""
    monkeypatch.setattr(
        actress_service,
        "build_site_fetcher",
        lambda source="javdb", runtime_config=None: object(),
    )


def _javdb_metadata(*, primary_names: list[str], aliases: list[str]):
    return lambda fetcher, url: ActorMetadata(
        primary_names=list(primary_names),
        aliases=list(aliases),
        source_url=url,
        source_site="javdb",
    )


def test_fetch_actress_from_actor_task_uses_javdb_aliases_to_match_avjoho(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user, url_name="咲乃柑菜", tag_names=["清楚", "单体"])
    _stub_site_fetchers(monkeypatch)
    monkeypatch.setattr(
        actress_service,
        "fetch_actor_metadata",
        _javdb_metadata(primary_names=["咲乃柑菜"], aliases=["蘭華"]),
    )
    monkeypatch.setattr(
        AvjohoActressSpider,
        "find_first_matching_profile",
        lambda self, names, manual_url=None: ActressProfileMatch(
            profile=ActressProfilePayload(
                display_name="蘭華",
                reading="らんか",
                source_url="https://db.avjoho.com/%E8%98%AD%E8%8F%AF/",
                image_url="https://example.test/ranka.jpg",
                aliases=["咲乃柑菜"],
            ),
            attempted_urls=["https://db.avjoho.com/%E8%98%AD%E8%8F%AF/"],
            candidate_names=list(names),
            matched_url="https://db.avjoho.com/%E8%98%AD%E8%8F%AF/",
        ),
    )

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
    assert data["profiles"][0]["tags"] == ["单体", "清楚"]


def test_fetch_existing_actress_only_merges_tags_and_source_links(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user, url_name="咲乃柑菜", tag_names=["新标签"])
    existing = ActressProfile(
        display_name="旧名称",
        reading="old",
        canonical_names=["咲乃柑菜"],
        source_url="https://db.avjoho.com/existing/",
        image_url="https://example.test/old.jpg",
        birth_date=date(1999, 1, 1),
        tags=["旧标签"],
    )
    db_session.add(existing)
    db_session.commit()
    _stub_site_fetchers(monkeypatch)
    monkeypatch.setattr(
        actress_service,
        "fetch_actor_metadata",
        _javdb_metadata(primary_names=["咲乃柑菜"], aliases=[]),
    )
    monkeypatch.setattr(
        AvjohoActressSpider,
        "find_first_matching_profile",
        lambda self, names, manual_url=None: ActressProfileMatch(
            profile=ActressProfilePayload(
                display_name="新名称",
                reading="new",
                source_url="https://db.avjoho.com/existing/",
                image_url="https://example.test/new.jpg",
                birth_date=date(2001, 2, 3),
            ),
            attempted_urls=["https://db.avjoho.com/existing/"],
            candidate_names=list(names),
            matched_url="https://db.avjoho.com/existing/",
        ),
    )

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(task.id), "task_url_id": str(task_url.id)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    db_session.refresh(existing)
    assert existing.display_name == "旧名称"
    assert existing.reading == "old"
    assert existing.image_url == "https://example.test/old.jpg"
    assert existing.birth_date == date(1999, 1, 1)
    assert existing.tags == ["旧标签", "新标签"]
    assert [str(value) for value in existing.source_task_url_ids] == [str(task_url.id)]


def test_fetch_existing_actress_by_task_url_only_merges_tags_without_crawling(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user, url_name="吹石玲奈", tag_names=["新增标签"])
    existing = ActressProfile(
        display_name="吹石れな",
        reading="ふきいしれな",
        canonical_names=["吹石玲奈", "吹石れな"],
        source_url="https://db.avjoho.com/%E5%90%B9%E7%9F%B3%E3%82%8C%E3%81%AA/",
        image_url="https://example.test/fukiishi.jpg",
        source_task_ids=[task.id],
        source_task_url_ids=[task_url.id],
        tags=["已有标签"],
    )
    db_session.add(existing)
    db_session.commit()

    def fail_fetch_actor_metadata(*_args, **_kwargs):
        raise AssertionError("existing actress should not refetch JavDB metadata")

    def fail_find_first_matching_profile(*_args, **_kwargs):
        raise AssertionError("existing actress should not search avjoho")

    monkeypatch.setattr(actress_service, "fetch_actor_metadata", fail_fetch_actor_metadata)
    monkeypatch.setattr(AvjohoActressSpider, "find_first_matching_profile", fail_find_first_matching_profile)

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={"task_id": str(task.id), "task_url_id": str(task_url.id)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["matched"] is True
    assert data["profiles"][0]["id"] == str(existing.id)
    assert data["profiles"][0]["tags"] == ["已有标签", "新增标签"]
    assert data["message"] == "已更新女优标签"


def test_fetch_actress_from_actor_task_passes_names_to_spider_and_returns_candidates(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
) -> None:
    task, task_url = _seed_actor_task(db_session, admin_user, url_name="七瀨愛麗絲")
    seen_names: list[list[str]] = []
    _stub_site_fetchers(monkeypatch)
    monkeypatch.setattr(
        actress_service,
        "fetch_actor_metadata",
        _javdb_metadata(primary_names=["七瀨愛麗絲"], aliases=["七瀬アリス"]),
    )

    def fake_find_first_matching_profile(self, names, manual_url=None):
        seen_names.append(list(names))
        return ActressProfileMatch(
            profile=ActressProfilePayload(
                display_name="七瀬アリス",
                reading="ななせありす",
                source_url="https://db.avjoho.com/nanase-alice/",
                image_url="https://example.test/nanase.jpg",
                aliases=["七瀨愛麗絲"],
            ),
            attempted_urls=[
                "https://db.avjoho.com/%E4%B8%83%E7%80%A8%E6%84%9B%E9%BA%97%E7%B5%B2/",
                "https://db.avjoho.com/nanase-alice/",
            ],
            candidate_names=list(names),
            matched_url="https://db.avjoho.com/nanase-alice/",
        )

    monkeypatch.setattr(AvjohoActressSpider, "find_first_matching_profile", fake_find_first_matching_profile)

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
    assert data["candidates"] == [
        "https://db.avjoho.com/%E4%B8%83%E7%80%A8%E6%84%9B%E9%BA%97%E7%B5%B2/",
        "https://db.avjoho.com/nanase-alice/",
    ]
    # JavDB primary names and aliases are plumbed into the spider as candidate names.
    assert seen_names[0][:2] == ["七瀨愛麗絲", "七瀬アリス"]


def test_fetch_actress_from_actor_task_handles_missing_candidates_without_traceback(
    client,
    auth_headers,
    db_session,
    admin_user,
    monkeypatch,
    caplog,
) -> None:
    task, _task_url = _seed_actor_task(db_session, admin_user, url_name="不存在")

    class NotFoundFetcher:
        def get(self, url: str):
            raise FileNotFoundError(url)

    monkeypatch.setattr(
        actress_service,
        "build_site_fetcher",
        lambda source="javdb", runtime_config=None: NotFoundFetcher(),
    )
    monkeypatch.setattr(
        actress_service,
        "fetch_actor_metadata",
        _javdb_metadata(primary_names=["不存在"], aliases=[]),
    )

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
    _stub_site_fetchers(monkeypatch)

    def fake_fetch_actor_metadata(fetcher, url: str) -> ActorMetadata:
        fetched_javdb_urls.append(url)
        return ActorMetadata(
            primary_names=["演员B"],
            aliases=[],
            source_url=url,
            source_site="javdb",
        )

    monkeypatch.setattr(actress_service, "fetch_actor_metadata", fake_fetch_actor_metadata)
    monkeypatch.setattr(
        AvjohoActressSpider,
        "find_first_matching_profile",
        lambda self, names, manual_url=None: ActressProfileMatch(
            profile=ActressProfilePayload(
                display_name="演员B",
                reading="",
                source_url="https://db.avjoho.com/actor-b/",
                image_url="https://example.test/b.jpg",
            ),
            attempted_urls=["https://db.avjoho.com/actor-b/"],
            candidate_names=list(names),
            matched_url="https://db.avjoho.com/actor-b/",
        ),
    )

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


def test_fetch_actress_from_task_manual_avjoho_404_is_user_visible(
    client,
    db_session,
    admin_user,
    auth_headers,
    monkeypatch,
) -> None:
    task, actor_url = _seed_actor_task(db_session, admin_user, url_name="七瀬アリス")
    _stub_site_fetchers(monkeypatch)
    monkeypatch.setattr(
        actress_service,
        "fetch_actor_metadata",
        _javdb_metadata(primary_names=["七瀬アリス"], aliases=[]),
    )

    def fake_find_first_matching_profile(self, names, manual_url=None):
        raise ProfileSourceNotFound("manual avjoho profile not found")

    monkeypatch.setattr(AvjohoActressSpider, "find_first_matching_profile", fake_find_first_matching_profile)

    response = client.post(
        "/api/content/actresses/fetch-from-task",
        json={
            "task_id": str(task.id),
            "task_url_id": str(actor_url.id),
            "avjoho_url": "https://db.avjoho.com/missing/",
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert "manual avjoho profile not found" in response.text


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
