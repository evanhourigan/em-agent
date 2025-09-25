from collections.abc import Generator

from sqlalchemy.engine import Connection

from ..db import get_engine


def get_db_connection() -> Generator[Connection, None, None]:
    engine = get_engine()
    with engine.connect() as conn:
        yield conn
