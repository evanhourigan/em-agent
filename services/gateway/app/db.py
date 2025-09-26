import os
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def _normalize_database_url(url: str) -> str:
    """Ensure SQLAlchemy uses psycopg driver explicitly.

    docker-compose provides postgresql://...; prefer postgresql+psycopg://...
    """
    if url.startswith("postgresql://") and "+" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine

    database_url = os.getenv(
        "DATABASE_URL",
        # Sensible local default if not provided
        "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
    )
    database_url = _normalize_database_url(database_url)

    _engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        future=True,
    )
    return _engine


class Base(DeclarativeBase):
    pass


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is not None:
        return _SessionLocal

    engine = get_engine()
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return _SessionLocal


def check_database_health() -> dict:
    """Run a lightweight health check against the database."""
    engine = get_engine()
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            ok = bool(result == 1)
            return {"ok": ok, "details": "ok" if ok else "unexpected result"}
    except (
        Exception
    ) as exc:  # noqa: BLE001 - include error details for operator visibility
        return {"ok": False, "details": str(exc)}
