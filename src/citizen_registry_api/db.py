"""Database engine and session handling.

The engine is the connection pool to PostgreSQL (created once per app).
A session is one short "unit of work" (created per request, then closed).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from citizen_registry_api.config import get_settings

engine = create_engine(
    get_settings().database_url.get_secret_value(),
    pool_pre_ping=True,  # test each pooled connection before use; avoids "connection closed" errors
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: open a session for one request, always close it afterwards."""
    with SessionLocal() as session:
        yield session