"""Shared pytest fixtures for tests that need the real API and a real database.

Safety rules:
- Tests use a SEPARATE database (TEST_DATABASE_URL), never your development data.
- The database name must end in "_test", or the run stops before touching anything.
- Every test starts with empty tables.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from citizen_registry_api.config import Settings, get_settings
from citizen_registry_api.db import get_session
from citizen_registry_api.main import app

TEST_API_KEY = "test-api-key"
TEST_HASH_SECRET = "test-hash-secret"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _TestEnv(BaseSettings):
    """Reads TEST_DATABASE_URL from the environment or .env (CI sets it as an env var)."""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")
    test_database_url: str | None = None


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = _TestEnv().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set, so database tests are skipped")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.exit(
            "TEST_DATABASE_URL must point to a database whose name ends in '_test'"
        )
    return url


@pytest.fixture(scope="session")
def engine(test_db_url: str) -> Iterator[Engine]:
    """Build the test schema with our REAL migrations, once per test run.

    Going down to 'base' and back up to 'head' also proves every migration
    can be rolled back and re-applied.
    """
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", test_db_url.replace("%", "%%"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    eng = create_engine(test_db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A database session for one test. Tables are emptied afterwards."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE audit_logs, consents, citizens"))


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused",  # the session override below is what's used
        api_key=TEST_API_KEY,
        id_hash_secret=TEST_HASH_SECRET,
    )


@pytest.fixture
def client(db_session: Session, test_settings: Settings) -> Iterator[TestClient]:
    """An HTTP client for the real app, wired to the test database and test settings.

    It sends a valid API key on every request by default.
    """
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app, headers={"X-API-Key": TEST_API_KEY}) as c:
        yield c
    app.dependency_overrides.clear()
