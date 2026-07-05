"""Tests for source task ID helpers."""

import uuid

from backend.app.modules.crawler.runtime.source_task_names import (
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
