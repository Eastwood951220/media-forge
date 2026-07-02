from sqlalchemy import select

from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_name_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie


def test_find_existing_movie_codes_returns_only_existing_codes() -> None:
    session = TestingSessionLocal()
    session.add(Movie(code="AAA-001", source_url="https://example.test/aaa", source_task_names=["旧任务"]))
    session.add(Movie(code="BBB-002", source_url="https://example.test/bbb", source_task_names=[]))
    session.commit()

    existing = find_existing_movie_codes(session, ["AAA-001", "AAA-001", "CCC-003", None, ""])

    assert existing == {"AAA-001"}
    assert movie_code_exists(session, "BBB-002") is True
    assert movie_code_exists(session, "CCC-003") is False
    assert movie_code_exists(session, None) is False


def test_add_source_task_name_for_code_appends_once() -> None:
    session = TestingSessionLocal()
    movie = Movie(code="AAA-010", source_url="https://example.test/aaa010", source_task_names=["旧任务"])
    session.add(movie)
    session.commit()

    assert add_source_task_name_for_code(session, "AAA-010", "新任务") is True
    assert add_source_task_name_for_code(session, "AAA-010", "新任务") is False
    assert add_source_task_name_for_code(session, "MISSING", "新任务") is False
    session.commit()

    refreshed = session.scalar(select(Movie).where(Movie.code == "AAA-010"))
    assert refreshed.source_task_names == ["旧任务", "新任务"]
