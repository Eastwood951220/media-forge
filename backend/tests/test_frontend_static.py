from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import configure_frontend


def write_frontend_dist(tmp_path):
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><title>Media Forge</title></head><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('media-forge')\n", encoding="utf-8")
    return tmp_path


def test_configure_frontend_serves_spa_root(tmp_path) -> None:
    static_dir = write_frontend_dist(tmp_path)
    app = FastAPI()

    configure_frontend(app, static_dir=static_dir)

    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Media Forge" in response.text


def test_configure_frontend_serves_spa_deep_routes(tmp_path) -> None:
    static_dir = write_frontend_dist(tmp_path)
    app = FastAPI()

    configure_frontend(app, static_dir=static_dir)

    response = TestClient(app).get("/content/movies")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Media Forge" in response.text


def test_configure_frontend_serves_vite_assets(tmp_path) -> None:
    static_dir = write_frontend_dist(tmp_path)
    app = FastAPI()

    configure_frontend(app, static_dir=static_dir)

    response = TestClient(app).get("/assets/app.js")
    assert response.status_code == 200
    assert "media-forge" in response.text


def test_configure_frontend_preserves_api_route_precedence(tmp_path) -> None:
    static_dir = write_frontend_dist(tmp_path)
    app = FastAPI()

    @app.get("/api/init/config")
    def init_config() -> dict[str, bool]:
        return {"initialized": False}

    configure_frontend(app, static_dir=static_dir)

    response = TestClient(app).get("/api/init/config")
    assert response.status_code == 200
    assert response.json() == {"initialized": False}


def test_configure_frontend_does_not_swallow_unknown_api_routes(tmp_path) -> None:
    static_dir = write_frontend_dist(tmp_path)
    app = FastAPI()

    configure_frontend(app, static_dir=static_dir)

    response = TestClient(app).get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_configure_frontend_is_noop_when_dist_missing(tmp_path) -> None:
    app = FastAPI()

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": "api"}

    configure_frontend(app, static_dir=tmp_path / "missing")

    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "api"}
