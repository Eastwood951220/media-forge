"""Tests for task delete cascade and source_task_id filtering."""

import uuid
from datetime import date
from decimal import Decimal
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from shared.database.models.content import Movie
from backend.tests.conftest import TestingSessionLocal


def auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def seed_task_with_movies(task_name: str, movie_codes: list[str]) -> tuple[str, list[str]]:
    """Seed a crawl task with associated movies."""
    session = TestingSessionLocal()

    # Create task
    task = CrawlTask(name=task_name, owner_id=session.query(
        # Get first user ID (admin)
        session.query(CrawlTask).first().owner_id if session.query(CrawlTask).first() else uuid.uuid4()
    ).first() or uuid.uuid4())
    session.add(task)
    session.flush()

    task_id = str(task.id)
    movie_ids = []

    # Create movies with source_task_id
    for code in movie_codes:
        movie = Movie(
            code=code,
            source_url=f"https://javdb.com/v/{code.lower()}",
            source_name=f"电影 {code}",
            release_date=date(2026, 1, 1),
            duration=120,
            rating=Decimal("4.0"),
            actors=["演员A"],
            tags=["标签A"],
            source_task_names=[task_name],
            source_task_id=task.id,
        )
        session.add(movie)
        session.flush()
        movie_ids.append(str(movie.id))

    session.commit()
    session.close()
    return task_id, movie_ids


def test_delete_task_cascades_movies(client: TestClient, admin_user) -> None:
    """Test that deleting a task also deletes associated movies."""
    headers = auth_headers(client, admin_user)

    # First create a user to own the task
    session = TestingSessionLocal()
    from backend.app.models.user import User
    user = session.query(User).first()
    user_id = user.id if user else uuid.uuid4()
    session.close()

    # Seed task with movies
    session = TestingSessionLocal()
    task = CrawlTask(name="测试任务", owner_id=user_id)
    session.add(task)
    session.flush()
    task_id = str(task.id)

    movie1 = Movie(
        code="TEST-001",
        source_url="https://javdb.com/v/test001",
        source_name="测试电影1",
        source_task_id=task.id,
        source_task_names=["测试任务"],
    )
    movie2 = Movie(
        code="TEST-002",
        source_url="https://javdb.com/v/test002",
        source_name="测试电影2",
        source_task_id=task.id,
        source_task_names=["测试任务"],
    )
    # Movie without source_task_id (should not be deleted)
    movie3 = Movie(
        code="OTHER-001",
        source_url="https://javdb.com/v/other001",
        source_name="其他电影",
        source_task_names=["其他任务"],
    )
    session.add_all([movie1, movie2, movie3])
    session.commit()
    session.close()

    # Delete the task
    response = client.delete(f"/api/crawler/tasks/{task_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["msg"] == "删除成功"
    assert body["data"]["deleted_movies"] == 2

    # Verify movies are deleted
    session = TestingSessionLocal()
    remaining = session.query(Movie).all()
    assert len(remaining) == 1
    assert remaining[0].code == "OTHER-001"
    session.close()


def test_list_movies_filter_by_source_task_id(client: TestClient, admin_user) -> None:
    """Test filtering movies by source_task_id."""
    headers = auth_headers(client, admin_user)

    # Create movies with different source_task_ids
    session = TestingSessionLocal()
    task_id_1 = uuid.uuid4()
    task_id_2 = uuid.uuid4()

    movie1 = Movie(
        code="TASK1-001",
        source_url="https://javdb.com/v/task1-001",
        source_name="任务1电影",
        source_task_id=task_id_1,
        source_task_names=["任务1"],
    )
    movie2 = Movie(
        code="TASK2-001",
        source_url="https://javdb.com/v/task2-001",
        source_name="任务2电影",
        source_task_id=task_id_2,
        source_task_names=["任务2"],
    )
    session.add_all([movie1, movie2])
    session.commit()
    session.close()

    # Filter by source_task_id
    response = client.get(
        f"/api/content/movies?source_task_id={task_id_1}",
        headers=headers,
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["code"] == "TASK1-001"
    assert body["rows"][0]["source_task_id"] == str(task_id_1)


def test_movie_payload_includes_source_task_id(client: TestClient, admin_user) -> None:
    """Test that movie payload includes source_task_id field."""
    headers = auth_headers(client, admin_user)

    session = TestingSessionLocal()
    task_id = uuid.uuid4()
    movie = Movie(
        code="PAYLOAD-001",
        source_url="https://javdb.com/v/payload001",
        source_name="Payload测试",
        source_task_id=task_id,
        source_task_names=["测试任务"],
    )
    session.add(movie)
    session.commit()
    movie_id = str(movie.id)
    session.close()

    response = client.get(f"/api/content/movies/{movie_id}", headers=headers)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["source_task_id"] == str(task_id)
