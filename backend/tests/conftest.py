from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
import shared.database.models.content  # noqa: F401
from backend.app.core.dependencies import get_db
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.main import app
from backend.app.models.user import User
from shared.database.models.base import Base

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db() -> None:
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a transactional database session for test data setup."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db_session) -> User:
    """Seed a test user in the database."""
    user = User(
        username="testuser",
        hashed_password=get_password_hash("test123"),
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user) -> dict[str, str]:
    """Return authorization headers with a valid JWT token."""
    token = create_access_token(data={"sub": test_user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    """TestClient with mocked lifespan to avoid real PostgreSQL/Redis connections."""
    with patch("backend.app.main.connect_or_repair_postgres"), \
         patch("backend.app.main.close_postgres"), \
         patch("backend.app.main.close_redis"), \
         patch("backend.app.main.get_session_factory"), \
         patch("backend.app.main.cleanup_interrupted_runs"), \
         patch("backend.app.main.cleanup_interrupted_storage_tasks"), \
         patch("backend.app.main.finalize_stalled_schedule_runs"), \
         patch("backend.app.main.crawler_schedule_scheduler.start"), \
         patch("backend.app.main.crawler_schedule_scheduler.load_enabled_schedules"), \
         patch("backend.app.main.crawler_schedule_scheduler.shutdown"), \
         patch("backend.app.main.backup_scheduler.start"), \
         patch("backend.app.main.backup_scheduler.shutdown"), \
         patch("backend.app.main.ensure_scraping_worker_started"), \
         patch("backend.app.modules.storage.tasks.service.ensure_storage_worker_started"):
        with TestClient(app) as tc:
            yield tc


@pytest.fixture
def admin_user() -> User:
    """Seed a test admin user in the database."""
    session = TestingSessionLocal()
    user = User(
        username="admin",
        hashed_password=get_password_hash("admin123"),
        role="admin",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


@pytest.fixture
def other_user(db_session):
    from backend.app.models.user import User
    from backend.app.core.security import get_password_hash

    user = User(username="other", hashed_password=get_password_hash("other123"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class InMemoryRedis:
    """Minimal Redis stand-in for cache-backed code paths.

    The real cache client talks to a shared Redis database, so without this
    every test would read and write the same keys as its neighbours.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):  # noqa: A003 - mirrors the redis-py API
        self.store[key] = value
        return True

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed

    def scan_iter(self, match=None, count=None):
        prefix = (match or "").rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch) -> None:
    """Give each test a private cache instead of the shared Redis database."""
    client = InMemoryRedis()
    monkeypatch.setattr("backend.app.core.cache.get_redis", lambda: client)
