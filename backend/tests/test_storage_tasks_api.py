import uuid

from backend.app.models.crawl_task import CrawlTask
from shared.database.models.content import Movie, MovieMagnet


def _movie_with_source_and_magnet(db, owner_id, *, code="abc-123", location="A"):
    crawl_task = CrawlTask(name=f"task-{code}", storage_location=location, owner_id=owner_id)
    movie = Movie(code=code, source_name=f"title-{code}", source_task_ids=[crawl_task.id])
    magnet = MovieMagnet(
        movie=movie,
        magnet_url=f"magnet:?xt=urn:btih:{uuid.uuid4().hex}",
        dedupe_key=uuid.uuid4().hex,
        name=f"{code}.mp4",
        tags=["中字"],
        weight=50,
        selected=True,
    )
    db.add_all([crawl_task, movie, magnet])
    db.flush()
    movie.source_task_ids = [crawl_task.id]
    db.commit()
    return movie


def test_single_push_creates_main_and_subtask(client, db_session, auth_headers, test_user):
    movie = _movie_with_source_and_magnet(db_session, test_user.id)

    response = client.post(
        "/api/storage/tasks/push",
        json={
            "movie_id": str(movie.id),
            "storage_mode": "single",
            "selected_storage_location": "A",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source"] == "single"
    assert payload["storage_mode"] == "single"
    assert payload["total_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["alias"].startswith("云存储_")


def test_batch_push_creates_skipped_subtask_for_missing_magnet(client, db_session, auth_headers, test_user):
    crawl_task = CrawlTask(name="task-empty", storage_location="A", owner_id=test_user.id)
    movie = Movie(code="abc-999", source_name="empty", source_task_ids=[])
    db_session.add_all([crawl_task, movie])
    db_session.flush()
    movie.source_task_ids = [crawl_task.id]
    db_session.commit()

    response = client.post(
        "/api/storage/tasks/batch",
        json={"movie_ids": [str(movie.id)], "storage_mode": "single"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_count"] == 1
    assert payload["skipped_count"] == 1
