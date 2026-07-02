"""Tests for source task ID helpers."""

import uuid

from sqlalchemy import select

from backend.app.modules.crawler.runtime.source_task_names import (
    add_source_task_id_for_code,
    find_existing_movie_codes,
    movie_code_exists,
)
from backend.tests.conftest import TestingSessionLocal
from shared.database.models.content import Movie


def test_find_existing_movie_codes_returns_only_existing_codes() -> None:
    session = TestingSessionLocal()
    session.add(Movie(code="AAA-001", source_url="https://example.test/aaa", source_task_ids=[uuid.uuid4()]))
    session.add(Movie(code="BBB-002", source_url="https://example.test/bbb", source_task_ids=[]))
    session.commit()

    existing = find_existing_movie_codes(session, ["AAA-001", "AAA-001", "CCC-003", None, ""])

    assert existing == {"AAA-001"}
    assert movie_code_exists(session, "BBB-002") is True
    assert movie_code_exists(session, "CCC-003") is False
    assert movie_code_exists(session, None) is False


def test_add_source_task_id_for_code_appends_once() -> None:
    session = TestingSessionLocal()
    old_task_id = uuid.uuid4()
    movie = Movie(code="AAA-010", source_url="https://example.test/aaa010", source_task_ids=[old_task_id])
    session.add(movie)
    session.commit()

    new_task_id = uuid.uuid4()
    assert add_source_task_id_for_code(session, "AAA-010", new_task_id) is True
    assert add_source_task_id_for_code(session, "AAA-010", new_task_id) is False
    assert add_source_task_id_for_code(session, "MISSING", new_task_id) is False
    session.commit()

    refreshed = session.scalar(select(Movie).where(Movie.code == "AAA-010"))
    # Compare as strings since SQLite may return strings instead of UUIDs
    task_ids_as_str = [str(tid) for tid in refreshed.source_task_ids]
    assert str(old_task_id) in task_ids_as_str
    assert str(new_task_id) in task_ids_as_str
    assert len(refreshed.source_task_ids) == 2
