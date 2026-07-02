from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
import shared.database.models.content  # noqa: F401
from backend.app.core.dependencies import get_db
from backend.app.core.security import get_password_hash
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
def client() -> TestClient:
    """TestClient with mocked lifespan to avoid real PostgreSQL/Redis connections."""
    with patch("backend.app.main.connect_postgres"), \
         patch("backend.app.main.close_postgres"), \
         patch("backend.app.main.close_redis"), \
         patch("backend.app.main.get_session_factory"), \
         patch("backend.app.main.cleanup_interrupted_runs"):
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
