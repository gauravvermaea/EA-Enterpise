"""Database engine (SQLAlchemy 2, psycopg 3)."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from .config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3, "application_name": "eaexplorer-api"},
    )

    @event.listens_for(engine, "checkin")
    def _discard_temp(dbapi_connection, _record):
        """A pooled connection goes back clean: no temporary tables (eax.get_entity) carry over."""
        try:
            dbapi_connection.rollback()
            with dbapi_connection.cursor() as cur:
                cur.execute("DISCARD TEMP")
            dbapi_connection.commit()
        except Exception:  # a broken connection is replaced by the pool anyway
            pass

    return engine
