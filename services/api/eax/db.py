"""Database engine (SQLAlchemy 2, psycopg 3)."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from . import permissions
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

    @event.listens_for(engine, "checkout")
    def _who_is_asking(dbapi_connection, _record, _proxy):
        """Tell the database who is asking (phase 3.1): the signed-in user and their EA Explorer roles.
        Row-level security and the permission triggers use these (migrations/sql/0006_roles.sql).
        With nobody signed in (the job runner, the seed) both are empty and nothing is restricted:
        every route that serves people requires sign-in first."""
        who = permissions.current.get()
        with dbapi_connection.cursor() as cur:
            cur.execute("SELECT set_config('eax.actor', %s, false), set_config('eax.user_roles', %s, false)",
                        (who.username if who else "",
                         # a signed-in person with no EA Explorer role gets "none", never "" (which means no user)
                         (",".join(who.roles) or "none") if who else ""))
        dbapi_connection.commit()

    @event.listens_for(engine, "checkin")
    def _discard_temp(dbapi_connection, _record):
        """A pooled connection goes back clean: no temporary tables (eax.get_entity) and no user carry over."""
        try:
            dbapi_connection.rollback()
            with dbapi_connection.cursor() as cur:
                cur.execute("DISCARD TEMP")
                cur.execute("SELECT set_config('eax.actor', '', false), set_config('eax.user_roles', '', false)")
            dbapi_connection.commit()
        except Exception:  # a broken connection is replaced by the pool anyway
            pass

    return engine


@lru_cache(maxsize=1)
def get_changelog_engine() -> Engine:
    """The change log's own database (phase 9, D180): EAX_CHANGELOG_DB_URL, or the repository's database when it is
    empty. No user identity is set on it: who sees which rows is decided in eax/change_log.py."""
    settings = get_settings()
    return create_engine(settings.changelog_sqlalchemy_url, pool_pre_ping=True, pool_size=2, max_overflow=3,
                         connect_args={"connect_timeout": 5, "application_name": "eaexplorer-changelog"})
