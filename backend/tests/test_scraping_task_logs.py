import json

from backend.app.modules.scraping.tasks.logs import read_scraping_item_logs, write_scraping_item_log
from backend.app.modules.scraping.tasks.service import ScrapingTaskService
from shared.database.models.content import Movie


def test_scraping_item_logs_survive_invalid_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    entry = write_scraping_item_log("item-1", "INFO", "获取元数据", step="fetch_metadata")
    path = tmp_path / "logs/scraping/tasks/item-1.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")

    assert entry["step"] == "fetch_metadata"
    assert read_scraping_item_logs("item-1") == [entry]
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0]) == entry


def test_scraping_item_detail_and_logs_are_owner_scoped(
    client, db_session, test_user, other_user, auth_headers, tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    movie = Movie(code="ADN-784", source_name="ADN-784", storage_summary={"storage_status": "stored"})
    db_session.add(movie)
    db_session.commit()
    task = ScrapingTaskService(db_session).create_task([movie.id], test_user.id, config={})
    item = task.items[0]
    write_scraping_item_log(str(item.id), "INFO", "开始刮削", step="prepare")

    detail = client.get(f"/api/scraping/tasks/items/{item.id}", headers=auth_headers)
    logs = client.get(f"/api/scraping/tasks/items/{item.id}/logs", headers=auth_headers)

    assert detail.status_code == 200
    assert detail.json()["data"]["step"] == "prepare"
    assert logs.status_code == 200
    assert logs.json()["data"][0]["message"] == "开始刮削"

    from backend.app.core.security import create_access_token

    other_headers = {"Authorization": f"Bearer {create_access_token(data={'sub': other_user.username})}"}
    assert client.get(f"/api/scraping/tasks/items/{item.id}", headers=other_headers).status_code == 404
    assert client.get(f"/api/scraping/tasks/items/{item.id}/logs", headers=other_headers).status_code == 404
