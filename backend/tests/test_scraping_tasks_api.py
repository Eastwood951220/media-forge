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


def test_sql_script_matches_alembic_migration_types() -> None:
    from pathlib import Path

    sql_path = Path(__file__).resolve().parents[2] / "sql" / "20261020_add_scraping_status_and_tasks.sql"
    sql = sql_path.read_text(encoding="utf-8")

    assert "config_snapshot JSON NOT NULL" in sql
    assert "JSONB" not in sql
    assert "TIMESTAMP WITH TIME ZONE" not in sql
    for table in ("scraping_tasks", "scraping_task_items"):
        block = sql.split(f"CREATE TABLE {table} (")[1].split(");")[0]
        assert "created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()" in block
        assert "updated_at TIMESTAMP WITHOUT TIME ZONE" in block
        assert "updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL" not in block
