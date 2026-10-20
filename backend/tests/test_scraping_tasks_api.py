from http import HTTPStatus

from shared.database.models.content import Movie


def _auth_headers(client) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _movie(db, code="ADN-784") -> Movie:
    movie = Movie(code=code, source_name=code, storage_summary={"storage_status": "stored", "locations": []})
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return movie


def test_create_and_list_scraping_tasks(client, admin_user, db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.scraping.router.ensure_scraping_worker_started", lambda: None)
    headers = _auth_headers(client)
    movie = _movie(db_session)

    created = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": [str(movie.id)]})

    assert created.status_code == HTTPStatus.OK
    task = created.json()["data"]
    assert task["status"] == "queued"
    assert task["total_count"] == 1

    listed = client.get("/api/scraping/tasks", headers=headers)

    assert listed.status_code == HTTPStatus.OK
    assert listed.json()["data"]["total"] == 1

    detail = client.get(f"/api/scraping/tasks/{task['id']}", headers=headers)

    assert detail.status_code == HTTPStatus.OK
    assert len(detail.json()["data"]["items"]) == 1


def test_create_rejects_empty_and_unknown_movies(client, admin_user, db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.scraping.router.ensure_scraping_worker_started", lambda: None)
    headers = _auth_headers(client)

    empty = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": []})

    assert empty.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    unknown = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": ["00000000-0000-0000-0000-000000000000"]})

    assert unknown.status_code == HTTPStatus.BAD_REQUEST


def test_cancel_and_retry_endpoints(client, admin_user, db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.scraping.router.ensure_scraping_worker_started", lambda: None)
    headers = _auth_headers(client)
    movie = _movie(db_session)
    task = client.post("/api/scraping/tasks", headers=headers, json={"movie_ids": [str(movie.id)]}).json()["data"]

    cancelled = client.post(f"/api/scraping/tasks/{task['id']}/cancel", headers=headers)

    assert cancelled.status_code == HTTPStatus.OK
    assert cancelled.json()["data"]["status"] == "cancelled"

    retried = client.post(f"/api/scraping/tasks/{task['id']}/retry", headers=headers)

    assert retried.status_code == HTTPStatus.OK
    assert retried.json()["data"]["id"] != task["id"]
