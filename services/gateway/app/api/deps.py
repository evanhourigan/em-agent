from collections.abc import Generator

from sqlalchemy.orm import Session

from ..db import get_sessionmaker


def get_db_session() -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        yield session
