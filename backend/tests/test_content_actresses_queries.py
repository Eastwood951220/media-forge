import uuid

from sqlalchemy.dialects import postgresql

from backend.app.modules.content.actresses.queries import recent_movies_for_profile
from shared.database.models.content import ActressProfile


class _ScalarResult:
    def __iter__(self):
        return iter([])

    def all(self):
        raise AssertionError("recent movie lookup should not load every movie on PostgreSQL")


class _PostgresSession:
    def __init__(self):
        self.statement = None

    def get_bind(self):
        return type("Bind", (), {"dialect": postgresql.dialect()})()

    def scalars(self, statement):
        self.statement = statement
        return _ScalarResult()


def test_recent_movies_for_profile_uses_postgres_array_overlap_query() -> None:
    task_url_id = uuid.uuid4()
    session = _PostgresSession()
    profile = ActressProfile(source_task_url_ids=[task_url_id])

    recent_movies_for_profile(session, profile, limit=10)  # type: ignore[arg-type]

    assert session.statement is not None
    compiled = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "source_task_url_ids &&" in compiled
    assert "ORDER BY movies.release_date DESC NULLS LAST" in compiled
    assert "LIMIT" in compiled
