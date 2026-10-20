from http import HTTPStatus

from backend.app.modules.scraping.scan import ScanSummary


def _auth_headers(client) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_scan_requires_scrape_root(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client)

    response = client.post("/api/scraping/scan", headers=headers)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "刮削目录" in response.json()["msg"]


def test_scan_returns_summary(client, admin_user, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    headers = _auth_headers(client)
    client.put(
        "/api/scraping/config",
        headers=headers,
        json={
            "scrape_root": str(tmp_path),
            "media_root": "/media",
            "api_key": "secret-key-1234",
        },
    )

    captured: dict = {}

    def fake_scan_directory(db, config):
        captured.update(config)
        return ScanSummary(
            folders_scanned=3,
            folders_with_strm=1,
            scraped_folders=1,
            updated_movies=1,
        )

    monkeypatch.setattr(
        "backend.app.modules.scraping.router.scan_directory",
        fake_scan_directory,
    )

    response = client.post("/api/scraping/scan", headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["scraped_folders"] == 1
    assert captured["scrape_root"] == str(tmp_path)
    # Only the raw config exposes the unmasked key; the public config masks it.
    assert captured["api_key"] == "secret-key-1234"
